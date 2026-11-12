"""강의실 사진 업로드(검출→인식→출석) 및 조회/삭제."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..database import get_db
from ..deps import get_engine, get_session_or_404, get_settings_dep
from ..face_engine import FaceEngine
from ..models import ClassSession, Detection, SessionPhoto
from ..schemas import AttendanceOut, PhotoOut, PhotoUploadResult
from ..services import attendance as att
from ..services import storage
from ..services.recognition import build_gallery, to_blob
from ..services.views import detection_out, photo_out

logger = logging.getLogger(__name__)
router = APIRouter(tags=["photos"])


@router.post(
    "/sessions/{session_id}/photos",
    response_model=PhotoUploadResult,
    status_code=201,
    summary="강의실 사진 업로드 → 검출 → 인식 → 출석 반영",
)
def upload_session_photo(
    photo: UploadFile = File(..., description="강의실 사진 (jpg/jpeg/png)"),
    sess: ClassSession = Depends(get_session_or_404),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    engine: FaceEngine = Depends(get_engine),
):
    data, ext = storage.read_upload(photo, settings)
    image = storage.decode_image(data)
    faces = engine.detect_and_embed(image)

    gallery = build_gallery(
        db,
        dim=engine.dim,
        use_verified_faces=settings.use_verified_faces,
        exclude_session_id=sess.session_id,
    )

    rel_path = storage.save_session_photo(settings, sess.session_id, data, ext)
    try:
        sp = SessionPhoto(session_id=sess.session_id, photo_path=rel_path)
        db.add(sp)
        db.flush()

        detections: list[Detection] = []
        for (x, y, w, h), emb in faces:
            sid, sim = gallery.match(emb, settings.threshold)
            d = Detection(
                photo_id=sp.photo_id,
                bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h,
                embedding=to_blob(emb),
                matched_student_id=sid,
                similarity=sim,
                verified=False,
            )
            db.add(d)
            detections.append(d)
        db.flush()

        result_att = att.build_attendance(db, sess.session_id)
        db.commit()
    except Exception:
        db.rollback()
        storage.delete_file(settings, rel_path)
        raise

    matched = sum(d.matched_student_id is not None for d in detections)
    logger.info(
        "세션 %d 사진 %d: 얼굴 %d개, 매칭 %d개 (비교 대상 %d개)",
        sess.session_id, sp.photo_id, len(detections), matched, len(gallery.labels),
    )
    for d in detections:
        db.refresh(d, ["matched_student"])
    return PhotoUploadResult(
        photo=photo_out(sp, len(detections)),
        detections=[detection_out(d) for d in detections],
        attendance=result_att,
    )


@router.get(
    "/sessions/{session_id}/photos",
    response_model=list[PhotoOut],
    summary="수업 사진 목록(최신순)",
)
def list_session_photos(
    sess: ClassSession = Depends(get_session_or_404), db: Session = Depends(get_db)
):
    rows = db.execute(
        select(SessionPhoto, func.count(Detection.detection_id))
        .outerjoin(Detection, Detection.photo_id == SessionPhoto.photo_id)
        .where(SessionPhoto.session_id == sess.session_id)
        .group_by(SessionPhoto.photo_id)
        .order_by(SessionPhoto.captured_at.desc(), SessionPhoto.photo_id.desc())
    ).all()
    return [photo_out(p, n) for p, n in rows]


@router.delete(
    "/sessions/{session_id}/photos",
    response_model=AttendanceOut,
    summary="수업 사진 모두 삭제(검출 결과 포함) 후 출석 재계산",
)
def delete_session_photos(
    sess: ClassSession = Depends(get_session_or_404),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    photos = list(db.scalars(select(SessionPhoto).where(SessionPhoto.session_id == sess.session_id)))
    paths = [p.photo_path for p in photos]
    for p in photos:
        db.delete(p)
    db.flush()
    result = att.build_attendance(db, sess.session_id)
    db.commit()
    for path in paths:
        storage.delete_file(settings, path)
    return result


@router.get("/photos/{photo_id}/image", summary="강의실 사진 이미지", response_class=FileResponse)
def get_photo_image(
    photo_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    p = db.get(SessionPhoto, photo_id)
    if p is None:
        raise HTTPException(404, f"사진 {photo_id}를 찾을 수 없습니다.")
    path = storage.abs_path(settings, p.photo_path)
    if not path.is_file():
        raise HTTPException(404, "사진 파일이 없습니다.")
    return FileResponse(path, media_type=storage.media_type_of(p.photo_path))

