"""학생 등록/조회/삭제."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..database import get_db
from ..deps import get_engine, get_settings_dep
from ..face_engine import FaceEngine, crop
from ..models import Student
from ..schemas import StudentOut
from ..services import storage
from ..services.recognition import to_blob
from ..services.views import student_out

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/students", tags=["students"])

STUDENT_ID_PATTERN = r"^[A-Za-z0-9_-]{1,20}$"


@router.post("", response_model=StudentOut, status_code=201, summary="학생 등록(증명사진)")
def create_student(
    student_id: str = Form(..., pattern=STUDENT_ID_PATTERN, description="학번 (영문/숫자/_/-)"),
    name: str = Form(..., min_length=1, max_length=50),
    photo: UploadFile = File(..., description="증명사진 (jpg/jpeg/png, 얼굴 1개)"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    engine: FaceEngine = Depends(get_engine),
):
    if db.get(Student, student_id) is not None:
        raise HTTPException(409, f"이미 등록된 학번입니다: {student_id}")

    data, ext = storage.read_upload(photo, settings)
    image = storage.decode_image(data)
    boxes = engine.detect(image)
    if len(boxes) == 0:
        raise HTTPException(400, "얼굴이 검출되지 않았습니다. 정면 증명사진을 올려 주세요.")
    if len(boxes) > 1:
        raise HTTPException(400, f"얼굴이 {len(boxes)}개 검출되었습니다. 한 사람만 나온 사진을 올려 주세요.")
    embedding = engine.embed(crop(image, boxes[0]))

    rel_path = storage.save_student_photo(settings, student_id, data, ext)
    student = Student(
        student_id=student_id, name=name.strip(), photo_path=rel_path, embedding=to_blob(embedding)
    )
    db.add(student)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete_file(settings, rel_path)
        raise
    logger.info("학생 등록: %s (임베딩 %d차원)", student_id, embedding.shape[0])
    return student_out(student)


@router.get("", response_model=list[StudentOut], summary="학생 목록")
def list_students(db: Session = Depends(get_db)):
    return [student_out(s) for s in db.scalars(select(Student).order_by(Student.student_id))]


def _get_student(db: Session, student_id: str) -> Student:
    s = db.get(Student, student_id)
    if s is None:
        raise HTTPException(404, f"학생을 찾을 수 없습니다: {student_id}")
    return s


@router.get("/{student_id}/photo", summary="증명사진 이미지", response_class=FileResponse)
def get_student_photo(
    student_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    s = _get_student(db, student_id)
    path = storage.abs_path(settings, s.photo_path)
    if not path.is_file():
        raise HTTPException(404, "사진 파일이 없습니다.")
    return FileResponse(path, media_type=storage.media_type_of(s.photo_path))


@router.delete("/{student_id}", status_code=204, summary="학생 삭제(사진 파일 포함)")
def delete_student(
    student_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    s = _get_student(db, student_id)
    photo_path = s.photo_path
    # attendance 는 CASCADE, detections.matched_student_id 는 SET NULL (DB 외래키)
    db.delete(s)
    db.commit()
    storage.delete_file(settings, photo_path)
    logger.info("학생 삭제: %s", student_id)
    return Response(status_code=204)
