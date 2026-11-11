"""ORM 모델 (SQLAlchemy 2.0).

- 이미지는 파일로 저장하고 DB에는 data_dir 기준 상대경로(posix 형식)만 저장한다.
- 임베딩은 float32 numpy 배열을 tobytes() 한 BLOB.
- 시간은 UTC.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Student(Base):
    __tablename__ = "students"

    student_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    photo_path: Mapped[str] = mapped_column(String(255))
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ClassSession(Base):
    """수업 회차. (SQLAlchemy Session 과 이름이 겹치지 않도록 ClassSession)"""

    __tablename__ = "sessions"

    session_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_name: Mapped[str] = mapped_column(String(100))
    room: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    photos: Mapped[list[SessionPhoto]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )


class SessionPhoto(Base):
    __tablename__ = "session_photos"

    photo_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.session_id", ondelete="CASCADE"), index=True
    )
    photo_path: Mapped[str] = mapped_column(String(255))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[ClassSession] = relationship(back_populates="photos")
    detections: Mapped[list[Detection]] = relationship(
        back_populates="photo", cascade="all, delete-orphan", passive_deletes=True
    )


class Detection(Base):
    __tablename__ = "detections"

    detection_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    photo_id: Mapped[int] = mapped_column(
        ForeignKey("session_photos.photo_id", ondelete="CASCADE"), index=True
    )
    bbox_x: Mapped[int] = mapped_column(Integer)
    bbox_y: Mapped[int] = mapped_column(Integer)
    bbox_w: Mapped[int] = mapped_column(Integer)
    bbox_h: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[bytes] = mapped_column(LargeBinary)
    matched_student_id: Mapped[str | None] = mapped_column(
        ForeignKey("students.student_id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 매칭 실패여도 "가장 가까운 학생과의 유사도"는 기록해 둔다(교수 확인 참고용).
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)

    photo: Mapped[SessionPhoto] = relationship(back_populates="detections")
    matched_student: Mapped[Student | None] = relationship()

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.bbox_x, self.bbox_y, self.bbox_w, self.bbox_h)


class Attendance(Base):
    __tablename__ = "attendance"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.session_id", ondelete="CASCADE"), primary_key=True
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("students.student_id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(10))  # present / absent
    # auto: 얼굴 인식 결과로 계산 / manual: 교수가 직접 지정(재계산 시 유지)
    source: Mapped[str] = mapped_column(String(10), default="auto")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
