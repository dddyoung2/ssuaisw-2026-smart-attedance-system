"""수업 회차: 정보, 시작, 사진 처리, 출결 현황.

회차는 과목 홈(GET /courses/{code}/lectures)에서 먼저 고른다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from ..config import Settings
from ..database import get_db
from ..deps import get_engine, get_lecture_or_404, get_settings_dep
from ..face_engine import FaceEngine
from ..schemas import (
    AttendanceOut,
    AttendanceStudentOut,
    LectureOut,
    PhotoResultOut,
    StartOut,
    SummaryOut,
)
from ..services import attendance as att
from ..services import storage
from ..services.usaint import LectureInfo

router = APIRouter(prefix="/lectures", tags=["lectures"])


def _lecture_out(lec: LectureInfo) -> LectureOut:
    return LectureOut(
        lecture_id=lec.lecture_id,
        course_code=lec.course_code,
        course_name=lec.course_name,
        week=lec.week,
        session_no=lec.session_no,
        date=lec.date,
        room_no=lec.room_no,
    )


def _summary_out(s: att.Summary) -> SummaryOut:
    return SummaryOut(total=s.total, present=s.present, absent=s.absent)


@router.get("/{lecture_id}", response_model=LectureOut, summary="수업 회차 정보")
def get_lecture(lecture: LectureInfo = Depends(get_lecture_or_404)):
    return _lecture_out(lecture)


@router.post("/{lecture_id}/start", response_model=StartOut, summary="회차 시작: 수강생 출석 행 준비")
def start_lecture(
    lecture: LectureInfo = Depends(get_lecture_or_404), db: Session = Depends(get_db)
):
    result = att.start_lecture(db, lecture)
    db.commit()
    return StartOut(
        lecture_id=lecture.lecture_id, student_count=result.student_count, created=result.created
    )


@router.post(
    "/{lecture_id}/photos",
    response_model=PhotoResultOut,
    summary="단체 사진 → 검출·인식 → 수강생 1:1 매칭 → 출석 기록 (사진은 저장하지 않음)",
)
def upload_photo(
    photo: UploadFile = File(..., description="강의실 단체 사진 (jpg/jpeg/png)"),
    lecture: LectureInfo = Depends(get_lecture_or_404),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    engine: FaceEngine = Depends(get_engine),
):
    image = storage.decode_image(storage.read_upload(photo, settings))
    result = att.process_photo(db, lecture, image, engine, settings.threshold)
    db.commit()
    return PhotoResultOut(
        face_count=result.face_count,
        matched_count=result.matched_count,
        summary=_summary_out(result.summary),
    )


@router.get("/{lecture_id}/attendance", response_model=AttendanceOut, summary="출결 현황")
def get_attendance(
    lecture: LectureInfo = Depends(get_lecture_or_404), db: Session = Depends(get_db)
):
    rows, summary = att.attendance_list(db, lecture.lecture_id)
    return AttendanceOut(
        lecture=_lecture_out(lecture),
        summary=_summary_out(summary),
        students=[AttendanceStudentOut(student_id=s, name=n, present=p) for s, n, p in rows],
    )
