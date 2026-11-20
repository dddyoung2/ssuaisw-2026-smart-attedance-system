"""요청/응답 스키마 (Pydantic v2). 임베딩은 어떤 응답에도 포함하지 않는다(개인정보)."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class RoomOut(BaseModel):
    room_no: str
    camera: str | None


class CourseOut(BaseModel):
    course_code: str
    course_name: str
    lecture_count: int  # 대면 수업 출결 수 (회차 수)


class CourseDetailOut(BaseModel):
    course_code: str
    course_name: str


class CourseLectureOut(BaseModel):
    """과목 홈의 회차 목록 한 줄."""

    lecture_id: int
    week: int
    session_no: int
    date: dt.date
    room_no: str


class LectureOut(BaseModel):
    lecture_id: int
    course_code: str
    course_name: str
    week: int
    session_no: int
    date: dt.date
    room_no: str


class StartOut(BaseModel):
    lecture_id: int
    student_count: int  # 수강생 수
    created: int  # 이번에 새로 만든 출석 행 수 (이미 있으면 0)


class SummaryOut(BaseModel):
    total: int
    present: int
    absent: int


class PhotoResultOut(BaseModel):
    face_count: int  # 사진에서 검출된 얼굴 수
    matched_count: int  # 수강생과 매칭된 얼굴 수 (1:1)
    summary: SummaryOut


class AttendanceStudentOut(BaseModel):
    student_id: str
    name: str
    present: bool


class AttendanceOut(BaseModel):
    lecture: LectureOut
    summary: SummaryOut
    students: list[AttendanceStudentOut]
