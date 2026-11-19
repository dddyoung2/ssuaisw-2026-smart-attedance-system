"""과목 목록(첫 화면)과 과목 홈의 회차 목록."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Course
from ..schemas import CourseDetailOut, CourseLectureOut, CourseOut
from ..services import usaint

router = APIRouter(prefix="/courses", tags=["courses"])


def _course_or_404(course_code: str, db: Session = Depends(get_db)) -> Course:
    course = usaint.get_course(db, course_code)
    if course is None:
        raise HTTPException(404, f"과목 {course_code}를 찾을 수 없습니다.")
    return course


@router.get("", response_model=list[CourseOut], summary="과목 목록 (과목명 순, 회차 수 포함)")
def list_courses(db: Session = Depends(get_db)):
    return [
        CourseOut(course_code=c.course_code, course_name=c.course_name, lecture_count=c.lecture_count)
        for c in usaint.list_courses(db)
    ]


@router.get("/{course_code}", response_model=CourseDetailOut, summary="과목 정보")
def get_course(course: Course = Depends(_course_or_404)):
    return CourseDetailOut(course_code=course.course_code, course_name=course.course_name)


@router.get(
    "/{course_code}/lectures",
    response_model=list[CourseLectureOut],
    summary="과목의 회차 목록 (수업일·주차·차수 순)",
)
def list_course_lectures(course: Course = Depends(_course_or_404), db: Session = Depends(get_db)):
    return [
        CourseLectureOut(
            lecture_id=l.lecture_id, week=l.week, session_no=l.session_no, date=l.date, room_no=l.room_no
        )
        for l in usaint.course_lectures(db, course.course_code)
    ]
