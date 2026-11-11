"""출석 계산.

출석표는 항상 '그 수업의 모든 detection' 으로부터 다시 계산한다.
그래서 사진 여러 장 합치기 / 교수 매칭 수정 / 사진 삭제가 모두 recompute() 하나로 처리된다.
- 한 번이라도 매칭된 학생 → present, 나머지 등록 학생 → absent
- source='manual' 인 행(교수가 직접 지정)은 덮어쓰지 않는다.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Attendance, Detection, SessionPhoto, Student, utcnow
from ..schemas import AttendanceOut, AttendanceStudentOut, AttendanceSummary


def matched_student_ids(db: Session, session_id: int) -> set[str]:
    q = (
        select(Detection.matched_student_id)
        .join(SessionPhoto, SessionPhoto.photo_id == Detection.photo_id)
        .where(SessionPhoto.session_id == session_id, Detection.matched_student_id.is_not(None))
        .distinct()
    )
    return set(db.scalars(q))


def recompute(db: Session, session_id: int) -> None:
    """attendance 행을 detection 기준으로 맞춘다. commit 은 호출자가 한다."""
    matched = matched_student_ids(db, session_id)
    existing = {
        a.student_id: a
        for a in db.scalars(select(Attendance).where(Attendance.session_id == session_id))
    }
    for sid in db.scalars(select(Student.student_id)):
        status = "present" if sid in matched else "absent"
        row = existing.get(sid)
        if row is None:
            db.add(Attendance(session_id=session_id, student_id=sid, status=status, source="auto"))
        elif row.source == "auto" and row.status != status:
            row.status = status
            row.updated_at = utcnow()
    db.flush()


def set_manual(db: Session, session_id: int, student_id: str, status: str) -> None:
    """status: present/absent → 수동 지정, auto → 수동 해제 후 재계산."""
    row = db.get(Attendance, (session_id, student_id))
    if row is None:
        row = Attendance(session_id=session_id, student_id=student_id, status="absent")
        db.add(row)
    if status == "auto":
        row.source = "auto"
        row.status = "present" if student_id in matched_student_ids(db, session_id) else "absent"
    else:
        row.source = "manual"
        row.status = status
    row.updated_at = utcnow()
    db.flush()


def build_attendance(db: Session, session_id: int) -> AttendanceOut:
    """출석 결과 (recompute 를 먼저 수행해 새로 등록된 학생도 포함)."""
    recompute(db, session_id)

    best = dict(
        db.execute(
            select(Detection.matched_student_id, func.max(Detection.similarity))
            .join(SessionPhoto, SessionPhoto.photo_id == Detection.photo_id)
            .where(
                SessionPhoto.session_id == session_id,
                Detection.matched_student_id.is_not(None),
            )
            .group_by(Detection.matched_student_id)
        ).all()
    )
    rows = db.execute(
        select(Student.student_id, Student.name, Attendance.status, Attendance.source)
        .join(Attendance, Attendance.student_id == Student.student_id)
        .where(Attendance.session_id == session_id)
        .order_by(Student.student_id)
    ).all()

    students = [
        AttendanceStudentOut(
            student_id=sid,
            name=name,
            status=status,
            source=source,
            best_similarity=None if best.get(sid) is None else round(float(best[sid]), 4),
        )
        for sid, name, status, source in rows
    ]
    present = sum(s.status == "present" for s in students)
    return AttendanceOut(
        session_id=session_id,
        summary=AttendanceSummary(total=len(students), present=present, absent=len(students) - present),
        students=students,
    )
