"""수업 회차, 출석, 검출 목록."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..deps import get_session_or_404
from ..models import ClassSession, Detection, SessionPhoto, Student
from ..schemas import (
    AttendanceOut,
    AttendanceUpdate,
    DetectionOut,
    SessionCreate,
    SessionOut,
)
from ..services import attendance as att
from ..services.views import detection_out, session_out

router = APIRouter(prefix="/sessions", tags=["sessions"])

DEFAULT_COURSE_NAME = "데모 수업"


@router.post("", response_model=SessionOut, status_code=201, summary="수업 회차 생성")
def create_session(body: SessionCreate, db: Session = Depends(get_db)):
    sess = ClassSession(
        course_name=(body.course_name or "").strip() or DEFAULT_COURSE_NAME,
        room=body.room.strip(),
    )
    db.add(sess)
    db.flush()
    att.recompute(db, sess.session_id)  # 등록 학생 전원을 absent 로 시작
    db.commit()
    return session_out(db, sess)


@router.get("", response_model=list[SessionOut], summary="수업 회차 목록(최신순)")
def list_sessions(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ClassSession).order_by(ClassSession.started_at.desc(), ClassSession.session_id.desc())
    )
    return [session_out(db, s) for s in rows]


@router.get("/{session_id}", response_model=SessionOut, summary="수업 회차 조회")
def get_session(sess: ClassSession = Depends(get_session_or_404), db: Session = Depends(get_db)):
    return session_out(db, sess)


@router.get("/{session_id}/attendance", response_model=AttendanceOut, summary="출석 결과")
def get_attendance(sess: ClassSession = Depends(get_session_or_404), db: Session = Depends(get_db)):
    result = att.build_attendance(db, sess.session_id)
    db.commit()
    return result


@router.patch(
    "/{session_id}/attendance/{student_id}",
    response_model=AttendanceOut,
    summary="출석 수동 수정 (present/absent/auto)",
)
def update_attendance(
    student_id: str,
    body: AttendanceUpdate,
    sess: ClassSession = Depends(get_session_or_404),
    db: Session = Depends(get_db),
):
    if db.get(Student, student_id) is None:
        raise HTTPException(404, f"학생을 찾을 수 없습니다: {student_id}")
    att.set_manual(db, sess.session_id, student_id, body.status)
    result = att.build_attendance(db, sess.session_id)
    db.commit()
    return result


@router.get(
    "/{session_id}/detections",
    response_model=list[DetectionOut],
    summary="검출된 얼굴 목록(교수 확인용)",
)
def list_detections(
    sess: ClassSession = Depends(get_session_or_404), db: Session = Depends(get_db)
):
    rows = db.scalars(
        select(Detection)
        .join(SessionPhoto, SessionPhoto.photo_id == Detection.photo_id)
        .where(SessionPhoto.session_id == sess.session_id)
        .options(joinedload(Detection.matched_student))
        .order_by(Detection.photo_id, Detection.detection_id)
    )
    return [detection_out(d) for d in rows]
