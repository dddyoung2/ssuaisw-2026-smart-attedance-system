"""ORM 객체 → 응답 스키마 변환. (임베딩은 여기서 걸러진다)"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ClassSession, Detection, SessionPhoto, Student
from ..schemas import BBoxOut, DetectionOut, PhotoOut, SessionOut, StudentOut


def student_out(s: Student) -> StudentOut:
    return StudentOut(
        student_id=s.student_id,
        name=s.name,
        has_embedding=s.embedding is not None,
        embedding_dim=len(s.embedding) // 4 if s.embedding is not None else None,
        photo_url=f"/students/{s.student_id}/photo",
        created_at=s.created_at,
    )


def session_out(db: Session, s: ClassSession) -> SessionOut:
    count = db.scalar(
        select(func.count()).select_from(SessionPhoto).where(SessionPhoto.session_id == s.session_id)
    )
    return SessionOut(
        session_id=s.session_id,
        course_name=s.course_name,
        room=s.room,
        started_at=s.started_at,
        photo_count=count or 0,
    )


def photo_out(p: SessionPhoto, face_count: int) -> PhotoOut:
    return PhotoOut(
        photo_id=p.photo_id,
        session_id=p.session_id,
        captured_at=p.captured_at,
        image_url=f"/photos/{p.photo_id}/image",
        face_count=face_count,
    )


def detection_out(d: Detection) -> DetectionOut:
    return DetectionOut(
        detection_id=d.detection_id,
        photo_id=d.photo_id,
        bbox=BBoxOut(x=d.bbox_x, y=d.bbox_y, w=d.bbox_w, h=d.bbox_h),
        matched_student_id=d.matched_student_id,
        matched_name=d.matched_student.name if d.matched_student else None,
        similarity=None if d.similarity is None else round(float(d.similarity), 4),
        verified=d.verified,
        face_url=f"/detections/{d.detection_id}/face",
    )
