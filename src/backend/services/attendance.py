"""출석 처리 흐름.

① 회차 시작: 수강생 전원의 attendance 행을 present=false 로 준비
② 사진 처리: 수강생 임베딩 조회 → 얼굴 엔진 → 1:1 매칭 → present=true 기록(OR)
③ 출결 현황: 학생별 출석 여부 + 요약

SQL 은 services/usaint.py 를 통해서만 실행한다. commit 은 호출자(라우터)가 한다.
업로드 사진은 메모리에서만 처리하고 디스크·DB 어디에도 저장하지 않는다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from ..face_engine import FaceEngine
from . import usaint
from .recognition import build_gallery, match_one_to_one
from .usaint import LectureInfo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Summary:
    total: int
    present: int
    absent: int


@dataclass(frozen=True)
class StartResult:
    student_count: int  # 수강생 수
    created: int  # 이번에 새로 만든 attendance 행 수


@dataclass(frozen=True)
class PhotoResult:
    face_count: int  # 사진에서 검출된 얼굴 수
    matched_count: int  # 수강생과 매칭된 얼굴 수
    summary: Summary


def start_lecture(db: Session, lecture: LectureInfo) -> StartResult:
    """수강생 attendance 행이 없으면 present=false 로 만든다(있으면 그대로, 여러 번 호출해도 안전)."""
    student_count, created = usaint.ensure_attendance_rows(db, lecture)
    return StartResult(student_count=student_count, created=created)


def process_photo(
    db: Session, lecture: LectureInfo, image: np.ndarray, engine: FaceEngine, threshold: float
) -> PhotoResult:
    # start 를 거치지 않았어도 출석이 누락되지 않도록 행을 먼저 준비한다.
    usaint.ensure_attendance_rows(db, lecture)

    # 그 회차 과목의 수강생 임베딩만 (전체 학생과 비교하지 않음)
    gallery = build_gallery(usaint.enrolled_embeddings(db, lecture.course_code), engine.dim)
    if gallery.skipped:
        logger.warning(
            "임베딩 차원이 %d이 아닌 수강생 %d명을 비교에서 제외했습니다. "
            "scripts/compute_embeddings.py 로 다시 계산하세요.",
            engine.dim,
            gallery.skipped,
        )

    faces = engine.detect_and_embed(image)
    matches = match_one_to_one([emb for _, emb in faces], gallery, threshold)
    newly = usaint.mark_present(db, lecture.lecture_id, [m.student_id for m in matches])

    summary = summarize(db, lecture.lecture_id)
    logger.info(
        "회차 %d 사진: 얼굴 %d개, 매칭 %d명(새 출석 %d명), 비교 수강생 %d명, 출석 %d/%d",
        lecture.lecture_id,
        len(faces),
        len(matches),
        newly,
        len(gallery.student_ids),
        summary.present,
        summary.total,
    )
    return PhotoResult(face_count=len(faces), matched_count=len(matches), summary=summary)


def attendance_list(db: Session, lecture_id: int) -> tuple[list[tuple[str, str, bool]], Summary]:
    rows = usaint.attendance_rows(db, lecture_id)
    return rows, _summary(rows)


def summarize(db: Session, lecture_id: int) -> Summary:
    return _summary(usaint.attendance_rows(db, lecture_id))


def _summary(rows: list[tuple[str, str, bool]]) -> Summary:
    present = sum(1 for _, _, p in rows if p)
    return Summary(total=len(rows), present=present, absent=len(rows) - present)
