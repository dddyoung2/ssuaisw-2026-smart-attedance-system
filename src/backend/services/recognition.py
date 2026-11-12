"""임베딩 직렬화와 코사인 유사도 매칭.

주의: 임베딩 값 자체는 개인정보이므로 절대 로그로 남기지 않는다(개수·차원만 기록).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Detection, SessionPhoto, Student

logger = logging.getLogger(__name__)


def to_blob(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).reshape(-1).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0 or nb == 0 or a.shape != b.shape:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


@dataclass
class Gallery:
    """비교 대상 임베딩 모음. 한 학생이 여러 행을 가질 수 있다."""

    matrix: np.ndarray  # (N, D), 각 행 L2 정규화
    labels: list[str]  # 행별 student_id

    def match(self, emb: np.ndarray, threshold: float) -> tuple[str | None, float | None]:
        """가장 유사한 학생과 유사도. 유사도 > threshold 일 때만 학생을 돌려준다."""
        if not self.labels:
            return None, None
        sims = self.matrix @ emb
        i = int(np.argmax(sims))
        best = float(sims[i])
        return (self.labels[i] if best > threshold else None), best


def build_gallery(
    db: Session,
    dim: int,
    use_verified_faces: bool = False,
    exclude_session_id: int | None = None,
) -> Gallery:
    rows: list[np.ndarray] = []
    labels: list[str] = []
    skipped = 0

    def add(blob: bytes, sid: str) -> None:
        nonlocal skipped
        vec = from_blob(blob)
        if vec.shape[0] != dim:
            skipped += 1
            return
        n = float(np.linalg.norm(vec))
        if n == 0:
            skipped += 1
            return
        rows.append(vec / n)
        labels.append(sid)

    for sid, blob in db.execute(
        select(Student.student_id, Student.embedding).where(Student.embedding.is_not(None))
    ):
        add(blob, sid)

    if use_verified_faces:
        q = (
            select(Detection.matched_student_id, Detection.embedding)
            .join(SessionPhoto, SessionPhoto.photo_id == Detection.photo_id)
            .where(Detection.verified.is_(True), Detection.matched_student_id.is_not(None))
        )
        if exclude_session_id is not None:
            q = q.where(SessionPhoto.session_id != exclude_session_id)
        for sid, blob in db.execute(q):
            add(blob, sid)

    if skipped:
        logger.warning(
            "차원이 %d이 아닌 임베딩 %d개를 비교에서 제외했습니다. "
            "scripts/recompute_embeddings.py 로 재계산하세요.",
            dim,
            skipped,
        )
    matrix = np.vstack(rows).astype(np.float32) if rows else np.zeros((0, dim), np.float32)
    return Gallery(matrix=matrix, labels=labels)
