"""usaint DB 모델 (SQLAlchemy 2.0).

usaint(숭실대 학사 포털) DB 에 이미 있는 학생·과목·강의실·회차·수강 정보를 흉내 낸다.
우리 시스템은 이 DB 를 읽고, 출석 결과(attendance)만 쓴다.

    room ─1:N─ lecture ─1:N─ attendance ─N:1─ student
                  │                              │
    class ─1:N────┘                              │
      └──────1:N── enrollment ──N:1──────────────┘

- 테이블 6개, 명세에 있는 컬럼만 둔다(사진 테이블 없음: 업로드 사진은 저장하지 않음).
- 증명사진은 파일로 두고 student.photo_path 에 경로만 저장한다.
- 임베딩은 float32 numpy 배열을 tobytes() 한 BLOB.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Room(Base):
    __tablename__ = "room"

    room_no: Mapped[str] = mapped_column(String(20), primary_key=True)  # 예: "21303"
    camera: Mapped[str | None] = mapped_column(String(200), nullable=True)

    lectures: Mapped[list[Lecture]] = relationship(back_populates="room")


class Course(Base):
    """과목(분반 포함). 테이블 이름은 class, 파이썬 예약어를 피해 클래스 이름은 Course."""

    __tablename__ = "class"

    course_code: Mapped[str] = mapped_column(String(20), primary_key=True)  # 예: "2150163301"
    course_name: Mapped[str] = mapped_column(String(100))

    # 수강생 목록 바로가기 (enrollment 를 거침, 조회 전용)
    students: Mapped[list[Student]] = relationship(
        secondary="enrollment", viewonly=True, order_by="Student.student_id"
    )
    lectures: Mapped[list[Lecture]] = relationship(
        back_populates="course", passive_deletes=True
    )


class Student(Base):
    __tablename__ = "student"

    student_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    photo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class Enrollment(Base):
    """수강 정보: 과목 × 학생 한 쌍이 한 줄."""

    __tablename__ = "enrollment"

    course_code: Mapped[str] = mapped_column(
        ForeignKey("class.course_code", ondelete="CASCADE"), primary_key=True
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("student.student_id", ondelete="CASCADE"), primary_key=True
    )


class Lecture(Base):
    """수업 회차. 시간 컬럼이 없어서 같은 강의실·같은 날에 여러 회차가 있을 수 있다."""

    __tablename__ = "lecture"

    lecture_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_code: Mapped[str] = mapped_column(
        ForeignKey("class.course_code", ondelete="CASCADE"), index=True
    )
    room_no: Mapped[str] = mapped_column(ForeignKey("room.room_no"), index=True)
    week: Mapped[int] = mapped_column(Integer)  # 주차
    session_no: Mapped[int] = mapped_column(Integer)  # 그 주의 몇 번째 수업인지
    date: Mapped[dt.date] = mapped_column(Date, index=True)

    course: Mapped[Course] = relationship(back_populates="lectures")
    room: Mapped[Room] = relationship(back_populates="lectures")


class Attendance(Base):
    __tablename__ = "attendance"

    lecture_id: Mapped[int] = mapped_column(
        ForeignKey("lecture.lecture_id", ondelete="CASCADE"), primary_key=True
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("student.student_id", ondelete="CASCADE"), primary_key=True
    )
    present: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
