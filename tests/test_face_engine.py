"""얼굴 엔진(연결부·더미)과 1:1 매칭 로직 단위 테스트.
정렬·검출 출력 규격은 test_align.py, test_detector.py 가 맡는다."""
from __future__ import annotations

import numpy as np
import pytest

from backend.face_engine import DummyDetector, FaceEmbedder, FaceEngine, available_engines, create_face_engine
from backend.services.recognition import Gallery, build_gallery, match_one_to_one, to_blob

from .conftest import face_array


# ---------- 더미 엔진 ----------
def test_dummy_embedding_is_deterministic_and_normalized():
    eng = create_face_engine("dummy")
    img = face_array(1)
    (box, e1), = eng.detect_and_embed(img)
    (_, e2), = eng.detect_and_embed(img.copy())
    assert len(box) == 4 and all(type(v) is int for v in box)
    assert e1.dtype == np.float32 and e1.shape == (128,)
    assert abs(np.linalg.norm(e1) - 1) < 1e-5
    assert np.array_equal(e1, e2)
    other = eng.detect_and_embed(face_array(2))[0][1]
    assert float(e1 @ other) < 0.5


def test_dummy_detector_rules():
    det = DummyDetector()
    dets, landms = det.detect(np.full((100, 100, 3), 7, np.uint8))
    assert dets.shape == (0, 5) and landms.shape == (0, 5, 2)
    dets, landms = det.detect(face_array(1, 100))
    assert dets.shape == (1, 5) and landms.shape == (1, 5, 2)
    dets, landms = det.detect(np.hstack([face_array(1, 100)] * 3))
    assert dets.shape == (3, 5) and landms.shape == (3, 5, 2)
    # 반환 형식은 RetinaFaceDetector 와 같고, 5점은 박스 안에 있다
    x1, y1, x2, y2 = (dets[:, i : i + 1] for i in range(4))
    lx, ly = landms[..., 0], landms[..., 1]
    assert np.all((lx >= x1) & (lx <= x2) & (ly >= y1) & (ly <= y2))


def test_unknown_engine():
    with pytest.raises(ValueError, match="dummy"):
        create_face_engine("nope")


def test_retinaface_engine_registered_without_loading_model(monkeypatch):
    from backend.engines import embedder

    monkeypatch.setattr(embedder, "_recognizer", None)
    assert "retinaface" in available_engines()
    eng = create_face_engine("retinaface")
    assert eng.detector is None  # 실제 검출기는 fd_pipeline.get_detector() 가 처음 쓸 때 불러온다
    assert isinstance(eng.embedder, embedder.AdaFaceEmbedder) and eng.dim == 512
    assert embedder._recognizer is None  # AdaFace 도 처음 임베딩할 때 불러온다(가중치 없어도 서버는 켜짐)


def test_engine_rejects_bad_embedder_output():
    class BadEmbedder(FaceEmbedder):
        dim = 128

        def embed(self, face_image):
            return np.ones(64, np.float32)

    with pytest.raises(ValueError, match="차원"):
        FaceEngine("bad", DummyDetector(), BadEmbedder()).detect_and_embed(face_array(1))


def test_engine_normalizes_embedding_of_aligned_square_face():
    class Unnormalized(FaceEmbedder):
        dim = 4

        def __init__(self):
            self.shapes = []

        def embed(self, face_image):
            self.shapes.append(face_image.shape)
            return np.array([3, 4, 0, 0], np.float64)

    emb = Unnormalized()
    out = FaceEngine("t", DummyDetector(), emb).detect_and_embed(face_array(1))
    assert len(out) == 1
    assert out[0][1].dtype == np.float32 and np.allclose(out[0][1], [0.6, 0.8, 0, 0])
    h, w, c = emb.shapes[0]
    assert h == w and c == 3  # 임베더는 fd_pipeline 이 정렬한 정사각형 얼굴을 받는다


def test_default_batch_and_anchor_match_single_embed():
    """embed_batch·embed_anchor 를 따로 구현하지 않은 임베더(더미 등)는 embed 와 같은 결과."""
    eng = create_face_engine("dummy")
    faces = [face_array(i) for i in range(3)]
    many = eng.embed_many(faces)
    assert len(many) == 3
    for face, vec in zip(faces, many):
        assert np.array_equal(vec, eng.embed(face))
        assert np.array_equal(eng.embed_anchor(face), eng.embed(face))
    assert eng.embed_many([]) == []


def test_engine_rejects_wrong_batch_count():
    class Short(FaceEmbedder):
        dim = 4

        def embed(self, face_image):
            return np.array([1, 0, 0, 0], np.float32)

        def embed_batch(self, face_images):
            return np.zeros((len(face_images) - 1, 4), np.float32)

    photo = np.hstack([face_array(i, 100) for i in range(2)])
    with pytest.raises(ValueError, match="개수"):
        FaceEngine("t", DummyDetector(), Short()).detect_and_embed(photo)


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
