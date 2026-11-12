"""요청/응답 스키마 (Pydantic v2). 임베딩은 어떤 응답에도 포함하지 않는다."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field


def _as_utc(v: datetime) -> datetime:
    # SQLite 는 tz 정보를 잃으므로 naive 값은 UTC 로 간주한다.
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]
Status = Literal["present", "absent"]


# ---------- 학생 ----------
class StudentOut(BaseModel):
    student_id: str
    name: str
    has_embedding: bool
    embedding_dim: int | None
    photo_url: str
    created_at: UtcDatetime


# ---------- 수업 회차 ----------
class SessionCreate(BaseModel):
    course_name: str | None = Field(default=None, max_length=100, examples=["캡스톤디자인"])
    room: str = Field(min_length=1, max_length=100, examples=["공학관 3층 301호"])


class SessionOut(BaseModel):
    session_id: int
    course_name: str
    room: str
    started_at: UtcDatetime
    photo_count: int


# ---------- 사진 / 검출 ----------
class BBoxOut(BaseModel):
    x: int
    y: int
    w: int
    h: int


class PhotoOut(BaseModel):
    photo_id: int
    session_id: int
    captured_at: UtcDatetime
    image_url: str
    face_count: int


class DetectionOut(BaseModel):
    detection_id: int
    photo_id: int
    bbox: BBoxOut
    matched_student_id: str | None
    matched_name: str | None
    similarity: float | None
    verified: bool
    face_url: str


class DetectionUpdate(BaseModel):
    """교수가 매칭 결과를 수정. null 이면 '등록된 학생 아님'."""

    matched_student_id: str | None = Field(examples=["20231001"])


# ---------- 출석 ----------
class AttendanceStudentOut(BaseModel):
    student_id: str
    name: str
    status: Status
    source: Literal["auto", "manual"]
    best_similarity: float | None


class AttendanceSummary(BaseModel):
    total: int
    present: int
    absent: int


class AttendanceOut(BaseModel):
    session_id: int
    summary: AttendanceSummary
    students: list[AttendanceStudentOut]


class AttendanceUpdate(BaseModel):
    """present/absent: 수동 지정(재계산해도 유지) / auto: 수동 지정 해제."""

    status: Literal["present", "absent", "auto"]


class PhotoUploadResult(BaseModel):
    photo: PhotoOut
    detections: list[DetectionOut]
    attendance: AttendanceOut
