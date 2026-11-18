"""얼굴 엔진(인터페이스·더미·랜드마크 정렬)과 1:1 매칭 로직 단위 테스트."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from backend.face_engine import (
    ALIGN_SIZE,
    ARCFACE_TEMPLATE,
    DummyDetector,
    DummyEmbedder,
    FaceDetection,
    FaceDetector,
    FaceEmbedder,
    FaceEngine,
    align_face,
    create_face_engine,
    similarity_transform,
)
from backend.services.recognition import Gallery, build_gallery, match_one_to_one, to_blob

from .conftest import face_array


# ---------- 더미 엔진 ----------
def test_dummy_embedding_is_deterministic_and_normalized():
    eng = create_face_engine("dummy")
    img = face_array(1)
    (det, e1), = eng.detect_and_embed(img)
    (_, e2), = eng.detect_and_embed(img.copy())
    assert isinstance(det, FaceDetection) and det.landmarks is None
    assert e1.dtype == np.float32 and e1.shape == (128,)
    assert abs(np.linalg.norm(e1) - 1) < 1e-5
    assert np.array_equal(e1, e2)
    other = eng.detect_and_embed(face_array(2))[0][1]
    assert float(e1 @ other) < 0.5


def test_dummy_detector_rules():
    det = DummyDetector()
    assert det.detect(np.full((100, 100, 3), 7, np.uint8)) == []
    assert len(det.detect(face_array(1, 100))) == 1
    assert len(det.detect(np.hstack([face_array(1, 100)] * 3))) == 3


def test_unknown_engine():
    with pytest.raises(ValueError, match="dummy"):
        create_face_engine("nope")


def test_engine_rejects_bad_embedder_output():
    class BadEmbedder(FaceEmbedder):
        dim = 128

        def embed(self, face_image):
            return np.ones(64, np.float32)

    with pytest.raises(ValueError, match="차원"):
        FaceEngine("bad", DummyDetector(), BadEmbedder()).detect_and_embed(face_array(1))


def test_engine_accepts_tuples_clips_bbox_and_normalizes():
    class TupleDetector(FaceDetector):
        def detect(self, image):
            return [(-10, -10, 50.4, 50.6), (500, 500, 10, 10)]  # 하나는 일부 밖, 하나는 완전히 밖

    class Unnormalized(FaceEmbedder):
        dim = 4

        def embed(self, face_image):
            return np.array([3, 4, 0, 0], np.float64)

    out = FaceEngine("t", TupleDetector(), Unnormalized()).detect_and_embed(face_array(1))
    assert [d.bbox for d, _ in out] == [(0, 0, 40, 41)]
    assert out[0][1].dtype == np.float32 and np.allclose(out[0][1], [0.6, 0.8, 0, 0])


# ---------- 랜드마크 정렬 ----------
class _RecordingEmbedder(FaceEmbedder):
    dim = 4

    def __init__(self):
        self.shapes = []

    def embed(self, face_image):
        self.shapes.append(face_image.shape)
        return np.ones(4, np.float32)


class _FixedDetector(FaceDetector):
    def __init__(self, dets):
        self.dets = dets

    def detect(self, image):
        return self.dets


def test_landmarks_use_alignment_otherwise_bbox_crop():
    lm = tuple(map(tuple, ARCFACE_TEMPLATE * 2 + [40, 30]))
    emb = _RecordingEmbedder()
    eng = FaceEngine(
        "t",
        _FixedDetector([FaceDetection(bbox=(40, 30, 224, 224), landmarks=lm), FaceDetection(bbox=(0, 0, 50, 60))]),
        emb,
    )
    eng.detect_and_embed(face_array(1, 300))
    assert emb.shapes == [(ALIGN_SIZE, ALIGN_SIZE, 3), (60, 50, 3)]


def test_invalid_landmarks_rejected():
    eng = FaceEngine("t", _FixedDetector([FaceDetection(bbox=(0, 0, 50, 50), landmarks=((1, 2),) * 4)]), _RecordingEmbedder())
    with pytest.raises(ValueError, match="5점"):
        eng.detect(face_array(1))


def test_similarity_transform_recovers_known_transform():
    theta, scale, t = np.deg2rad(20), 1.7, np.array([12.0, -5.0])
    rot = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    src = ARCFACE_TEMPLATE
    dst = (scale * (rot @ src.T)).T + t
    m = similarity_transform(src, dst)
    assert np.allclose(m[:, :2], scale * rot, atol=1e-9)
    assert np.allclose(m[:, 2], t, atol=1e-9)


def test_align_face_matches_crop_and_resize():
    # 랜드마크가 표준 위치를 2배 확대 + (40, 30) 이동한 곳에 있으면,
    # 정렬 결과는 (40, 30)에서 224x224 를 잘라 112 로 줄인 것과 같아야 한다.
    img = face_array(7, 300)
    lm = ARCFACE_TEMPLATE * 2 + [40, 30]
    aligned = align_face(img, lm)
    expected = np.asarray(Image.fromarray(img).crop((40, 30, 264, 254)).resize((112, 112), Image.BILINEAR))
    assert aligned.shape == (112, 112, 3) and aligned.dtype == np.uint8
    assert np.abs(aligned.astype(int) - expected.astype(int)).mean() < 6


def test_alignment_undoes_rotation():
    # 이미지를 돌려도 랜드마크로 정렬하면 비슷한 얼굴 이미지가 나온다
    img = face_array(3, 300)
    lm = ARCFACE_TEMPLATE * 2 + [40, 30]
    base = align_face(img, lm).astype(int)
    rotated = np.asarray(Image.fromarray(img).rotate(15, resample=Image.BILINEAR, center=(150, 150)))
    theta = np.deg2rad(-15)  # PIL 은 반시계(+)로 돌림 → 이미지 좌표(y 아래)에서는 -15도
    rot = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    lm_rot = ((rot @ (lm - 150).T).T) + 150
    again = align_face(rotated, lm_rot).astype(int)
    inner = (slice(20, 92), slice(20, 92))  # 회전으로 생긴 가장자리 빈 영역 제외
    assert np.abs(base[inner] - again[inner]).mean() < 12


# ---------- 1:1 매칭 ----------
def _gallery(ids, vecs, dim=4):
    return build_gallery([(i, to_blob(np.asarray(v, np.float32))) for i, v in zip(ids, vecs)], dim)


def test_greedy_one_to_one_prefers_best_pair():
    e0, e1 = np.eye(4)[0], np.eye(4)[1]
    f1 = 0.95 * e0 + 0.31 * e1  # a 와 0.95, b 와 0.31
    g = _gallery(["a", "b"], [e0, e1])
    # f0 와 f1 모두 a 에 가깝지만 a 는 한 얼굴에만 배정, f1-b 는 임계값 미만 → f1 은 미매칭
    matches = match_one_to_one([e0, f1], g, threshold=0.5)
    assert [(m.face_index, m.student_id) for m in matches] == [(0, "a")]


def test_matching_threshold_is_strict():
    e0 = np.eye(4)[0]
    g = _gallery(["a"], [e0])
    v = np.array([0.5, np.sqrt(0.75), 0, 0])  # 유사도 정확히 0.5
    assert match_one_to_one([v], g, threshold=0.5) == []
    assert len(match_one_to_one([v], g, threshold=0.49)) == 1


def test_matching_is_one_to_one_on_random_data():
    rng = np.random.default_rng(0)
    faces = rng.normal(size=(6, 8))
    studs = rng.normal(size=(5, 8))
    g = _gallery([f"s{i}" for i in range(5)], studs, dim=8)
    ms = match_one_to_one(list(faces), g, threshold=-1.0)
    assert len({m.face_index for m in ms}) == len(ms) == len({m.student_id for m in ms}) == 5


def test_build_gallery_skips_wrong_dimension_and_empty():
    g = build_gallery([("a", to_blob(np.ones(4))), ("b", to_blob(np.ones(8))), ("c", to_blob(np.zeros(4)))], 4)
    assert g.student_ids == ["a"] and g.skipped == 2
    assert match_one_to_one([np.ones(4)], Gallery([], np.zeros((0, 4), np.float32), 0), 0.5) == []
