"""얼굴 엔진 인터페이스 / 더미 구현 / 재계산 스크립트 테스트."""
from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.face_engine import (
    DummyDetector,
    DummyEmbedder,
    FaceDetector,
    FaceEmbedder,
    FaceEngine,
    create_face_engine,
    register_engine,
)
from backend.factory import create_app
from backend.scripts.recompute_embeddings import recompute

from .conftest import classroom, face_array, make_settings, register, upload


def test_dummy_embedding_is_deterministic_and_normalized():
    eng = create_face_engine("dummy")
    img = face_array(1)
    (box1, e1), = eng.detect_and_embed(img)
    (_, e2), = eng.detect_and_embed(img.copy())
    assert e1.dtype == np.float32 and e1.shape == (128,)
    assert abs(np.linalg.norm(e1) - 1) < 1e-5
    assert np.array_equal(e1, e2)
    other = eng.detect_and_embed(face_array(2))[0][1]
    assert float(e1 @ other) < 0.5


def test_dummy_detector_rules():
    det = DummyDetector()
    assert det.detect(np.full((100, 100, 3), 7, np.uint8)) == []
    assert len(det.detect(face_array(1, 100))) == 1
    wide = np.hstack([face_array(1, 100)] * 3)
    assert len(det.detect(wide)) == 3


def test_unknown_engine():
    with pytest.raises(ValueError, match="dummy"):
        create_face_engine("nope")


def test_engine_rejects_bad_embedder_output():
    class BadEmbedder(FaceEmbedder):
        dim = 128

        def embed(self, face_image):
            return np.ones(64, np.float32)

    eng = FaceEngine("bad", DummyDetector(), BadEmbedder())
    with pytest.raises(ValueError, match="차원"):
        eng.detect_and_embed(face_array(1))


def test_engine_clips_bbox_and_normalizes():
    class OffDetector(FaceDetector):
        def detect(self, image):
            return [(-10, -10, 50.4, 50.6), (500, 500, 10, 10)]  # 하나는 일부 밖, 하나는 완전히 밖

    class Unnormalized(FaceEmbedder):
        dim = 4

        def embed(self, face_image):
            return np.array([3, 4, 0, 0], np.float64)

    eng = FaceEngine("t", OffDetector(), Unnormalized())
    out = eng.detect_and_embed(face_array(1))
    assert [b for b, _ in out] == [(0, 0, 40, 41)]
    assert out[0][1].dtype == np.float32 and np.allclose(out[0][1], [0.6, 0.8, 0, 0])


def test_recompute_after_dimension_change(tmp_path):
    """차원이 바뀐 엔진으로 교체 → 기존 임베딩은 비교에서 제외 → 재계산 후 다시 매칭."""

    class Embedder64(FaceEmbedder):
        dim = 64

        def embed(self, face_image):
            return DummyEmbedder().embed(face_image)[:64]

    register_engine("dummy64", lambda: FaceEngine("dummy64", DummyDetector(), Embedder64()))

    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as c:
        register(c, "1", "a", 1)

    s64 = make_settings(tmp_path, face_engine="dummy64")
    with TestClient(create_app(s64)) as c:
        sid = c.post("/sessions", json={"room": "r"}).json()["session_id"]
        assert upload(c, sid, classroom(1)).json()["detections"][0]["matched_student_id"] is None

        report = recompute(s64, create_face_engine("dummy64"))
        assert report.students_ok == 1 and not report.students_failed
        assert c.get("/students").json()[0]["embedding_dim"] == 64
        assert upload(c, sid, classroom(1)).json()["detections"][0]["matched_student_id"] == "1"
