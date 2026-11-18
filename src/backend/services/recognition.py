"""얼굴 임베딩 × 수강생 임베딩 1:1 매칭 (DB 접근 없음, 순수 계산).

주의: 임베딩 값은 개인정보이므로 절대 로그로 남기지 않는다(개수·차원만 기록).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


def to_blob(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).reshape(-1).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


@dataclass(frozen=True)
class Gallery:
    """비교 대상(그 회차 과목의 수강생) 임베딩."""

    student_ids: list[str]
    matrix: np.ndarray  # (S, D), 각 행 L2 정규화
    skipped: int  # 차원이 달라 제외한 학생 수


def build_gallery(rows: Sequence[tuple[str, bytes]], dim: int) -> Gallery:
    """(학번, 임베딩 BLOB) 목록 → 정규화된 행렬. 차원이 다르거나 0벡터면 제외."""
    ids: list[str] = []
    vecs: list[np.ndarray] = []
    skipped = 0
    for sid, blob in rows:
        vec = from_blob(blob)
        norm = float(np.linalg.norm(vec)) if vec.size else 0.0
        if vec.shape[0] != dim or norm == 0.0:
            skipped += 1
            continue
        ids.append(sid)
        vecs.append(vec / norm)
    matrix = np.vstack(vecs).astype(np.float32) if vecs else np.zeros((0, dim), np.float32)
    return Gallery(student_ids=ids, matrix=matrix, skipped=skipped)


@dataclass(frozen=True)
class Match:
    face_index: int
    student_id: str
    similarity: float


def match_one_to_one(
    face_embeddings: Sequence[np.ndarray], gallery: Gallery, threshold: float
) -> list[Match]:
    """한 사진 안에서 얼굴 하나 ↔ 수강생 한 명만 짝짓는다.

    모든 (얼굴, 수강생) 쌍의 코사인 유사도를 구하고, 유사도가 높은 쌍부터
    "둘 다 아직 배정되지 않았으면" 배정한다(greedy). 유사도 > threshold 인 쌍만 인정.
    """
    if not len(face_embeddings) or not gallery.student_ids:
        return []
    faces = np.vstack([np.asarray(e, dtype=np.float32).reshape(-1) for e in face_embeddings])
    faces = faces / np.linalg.norm(faces, axis=1, keepdims=True)
    sims = faces @ gallery.matrix.T  # (F, S)

    candidates = np.argwhere(sims > threshold)
    # 유사도 내림차순, 같으면 얼굴 번호·학생 순서로 (결과가 항상 같도록)
    order = sorted(
        ((float(sims[f, s]), int(f), int(s)) for f, s in candidates),
        key=lambda t: (-t[0], t[1], t[2]),
    )
    used_faces: set[int] = set()
    used_students: set[int] = set()
    matches: list[Match] = []
    for sim, f, s in order:
        if f in used_faces or s in used_students:
            continue
        used_faces.add(f)
        used_students.add(s)
        matches.append(Match(face_index=f, student_id=gallery.student_ids[s], similarity=sim))
    return sorted(matches, key=lambda m: m.face_index)
