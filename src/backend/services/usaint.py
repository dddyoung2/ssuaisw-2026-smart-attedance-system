"""usaint DB 접근 계층.

usaint DB 를 읽고 쓰는 SQL 은 모두 이 파일에만 둔다.
나중에 실제 usaint(학사 포털)와 연동할 때 이 파일만 바꾸면 된다.

- 읽기: 강의실, 회차, 수강생(+임베딩), 출석 현황
- 쓰기: 출석(attendance) 행 준비·present 기록, 학생 임베딩(사전 추출 스크립트용)

commit 은 호출자(서비스/스크립트)가 한다.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from ..models import Attendance, Enrollment, Lecture, Room, Student


@dataclass(frozen=True)
class LectureInfo:
    lecture_id: int
    course_code: str
    course_name: str
    room_no: str
    week: int
    session_no: int
    date: dt.date


def _info(lec: Lecture) -> LectureInfo:
    return LectureInfo(
        lecture_id=lec.lecture_id,
        course_code=lec.course_code,
        course_name=lec.course.course_name,
        room_no=lec.room_no,
        week=lec.week,
        session_no=lec.session_no,
        date=lec.date,
    )


# ---------------------------------------------------------------------------
# 읽기
# ---------------------------------------------------------------------------
def list_rooms(db: Session) -> list[Room]:
    return list(db.scalars(select(Room).order_by(Room.room_no)))


def find_lectures(db: Session, room_no: str, on_date: dt.date) -> list[LectureInfo]:
    """강의실 + 날짜가 일치하는 회차. 시간 정보가 없어 여러 개일 수 있다."""
    rows = db.scalars(
        select(Lecture)
        .where(Lecture.room_no == room_no, Lecture.date == on_date)
        .options(joinedload(Lecture.course))
        .order_by(Lecture.course_code, Lecture.session_no, Lecture.lecture_id)
    )
    return [_info(lec) for lec in rows]


def get_lecture(db: Session, lecture_id: int) -> LectureInfo | None:
    lec = db.scalars(
        select(Lecture)
        .where(Lecture.lecture_id == lecture_id)
        .options(joinedload(Lecture.course))
    ).first()
    return _info(lec) if lec else None


def enrolled_student_ids(db: Session, course_code: str) -> list[str]:
    return list(
        db.scalars(
            select(Enrollment.student_id)
            .where(Enrollment.course_code == course_code)
            .order_by(Enrollment.student_id)
        )
    )


def enrolled_embeddings(db: Session, course_code: str) -> list[tuple[str, bytes]]:
    """그 과목 수강생의 (학번, 임베딩). ENROLLMENT ⋈ STUDENT JOIN 한 번으로 조회.

    임베딩이 아직 없는 학생(NULL)은 비교할 수 없으므로 제외한다.
    """
    q = (
        select(Student.student_id, Student.embedding)
        .join(Enrollment, Enrollment.student_id == Student.student_id)
        .where(Enrollment.course_code == course_code, Student.embedding.is_not(None))
        .order_by(Student.student_id)
    )
    return [(sid, blob) for sid, blob in db.execute(q)]


def attendance_rows(db: Session, lecture_id: int) -> list[tuple[str, str, bool]]:
    """출결 현황: (학번, 이름, 출석 여부). ATTENDANCE ⋈ STUDENT."""
    q = (
        select(Student.student_id, Student.name, Attendance.present)
        .join(Attendance, Attendance.student_id == Student.student_id)
        .where(Attendance.lecture_id == lecture_id)
        .order_by(Student.student_id)
    )
    return [(sid, name, bool(present)) for sid, name, present in db.execute(q)]


def students_with_photo(db: Session) -> list[Student]:
    return list(
        db.scalars(
            select(Student).where(Student.photo_path.is_not(None)).order_by(Student.student_id)
        )
    )


# ---------------------------------------------------------------------------
# 쓰기
# ---------------------------------------------------------------------------
def ensure_attendance_rows(db: Session, lecture: LectureInfo) -> tuple[int, int]:
    """수강생 전원의 attendance 행이 없으면 present=false 로 만든다(있으면 그대로).

    반환: (수강생 수, 새로 만든 행 수)
    """
    enrolled = enrolled_student_ids(db, lecture.course_code)
    existing = set(
        db.scalars(
            select(Attendance.student_id).where(Attendance.lecture_id == lecture.lecture_id)
        )
    )
    missing = [sid for sid in enrolled if sid not in existing]
    db.add_all(
        Attendance(lecture_id=lecture.lecture_id, student_id=sid, present=False)
        for sid in missing
    )
    db.flush()
    return len(enrolled), len(missing)


def mark_present(db: Session, lecture_id: int, student_ids: Iterable[str]) -> int:
    """present=true 로 기록. false 로 되돌리는 경로는 없다(사진별 결과의 OR).

    반환: 이번에 새로 출석 처리된 학생 수
    """
    ids = list(student_ids)
    if not ids:
        return 0
    result = db.execute(
        update(Attendance)
        .where(
            Attendance.lecture_id == lecture_id,
            Attendance.student_id.in_(ids),
            Attendance.present.is_(False),
        )
        .values(present=True)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


def set_student_embedding(db: Session, student_id: str, embedding: bytes | None) -> None:
    db.execute(
        update(Student)
        .where(Student.student_id == student_id)
        .values(embedding=embedding)
        .execution_options(synchronize_session=False)
    )


__all__ = [
    "LectureInfo",
    "list_rooms",
    "find_lectures",
    "get_lecture",
    "enrolled_student_ids",
    "enrolled_embeddings",
    "attendance_rows",
    "students_with_photo",
    "ensure_attendance_rows",
    "mark_present",
    "set_student_embedding",
]
