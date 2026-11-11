"""검출 결과 수정(교수 확인) 및 얼굴 이미지."""
from __future__ import annotations

import logging
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Response
from PIL import Image
from sqlalchemy.orm import Session

from ..config import Settings
from ..database import get_db
from ..deps import get_settings_dep
from ..face_engine import crop
from ..models import Detection, Student
from ..schemas import DetectionOut, DetectionUpdate
from ..services import attendance as att
from ..services import storage
from ..services.recognition import cosine, from_blob
from ..services.views import detection_out

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/detections", tags=["detections"])


def _get_detection(db: Session, detection_id: int) -> Detection:
    d = db.get(Detection, detection_id)
    if d is None:
        raise HTTPException(404, f"검출 결과 {detection_id}를 찾을 수 없습니다.")
    return d


@router.patch("/{detection_id}", response_model=DetectionOut, summary="매칭 결과 수정(교수 확인)")
def update_detection(detection_id: int, body: DetectionUpdate, db: Session = Depends(get_db)):
    d = _get_detection(db, detection_id)
    sid = body.matched_student_id
    if sid is not None:
        student = db.get(Student, sid)
        if student is None:
            raise HTTPException(404, f"학생을 찾을 수 없습니다: {sid}")
        # 유사도는 '수정된 학생'의 증명사진 임베딩 기준으로 다시 계산(참고용)
        d.similarity = (
            cosine(from_blob(d.embedding), from_blob(student.embedding))
            if student.embedding is not None
            else None
        )
    else:
        d.similarity = None
    d.matched_student_id = sid
    d.verified = True
    db.flush()

    att.recompute(db, d.photo.session_id)
    db.commit()
    db.refresh(d, ["matched_student"])
    logger.info("검출 %d 수정: matched=%s (verified)", detection_id, sid)
    return detection_out(d)


@router.get("/{detection_id}/face", summary="검출된 얼굴 부분 이미지(JPEG)")
def get_detection_face(
    detection_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    d = _get_detection(db, detection_id)
    try:
        image = storage.load_image(settings, d.photo.photo_path)
    except FileNotFoundError:
        raise HTTPException(404, "사진 파일이 없습니다.") from None
    face = crop(image, d.bbox)
    buf = BytesIO()
    Image.fromarray(face).save(buf, format="JPEG", quality=90)
    return Response(content=buf.getvalue(), media_type="image/jpeg")
