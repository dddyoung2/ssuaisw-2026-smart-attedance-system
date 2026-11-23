"""인식(AdaFace 임베더) 테스트.
- 입력 변환·연결 규격: 가짜 인식기로 어디서나 실행(CI 포함)
- 실제 AdaFace 테스트: 가중치가 있을 때만 실행, 없으면 건너뜀"""
import numpy as np
import pytest

from backend.engines import embedder
from backend.engines.adaface.model import WEIGHT_PATH
from backend.face_engine import DummyDetector, FaceEngine

from .conftest import face_array


class FakeRecognizer:
    """encode_rgb() 입력을 기록하고 정규화 안 된 512차원 벡터를 돌려주는 가짜 인식기."""

    def __init__(self):
        self.inputs = []

    def encode_rgb(self, images):
        self.inputs.append(images)
        out = np.zeros((len(images), 512), np.float32)
        out[:, 0], out[:, 1] = 3, 4
        return out


# ---------- 입력 변환·연결 규격 (가짜 인식기) ----------
@pytest.mark.parametrize("side", [50, 112, 300])
def test_to_input_resizes_whole_crop_to_112(side):
    crop = np.zeros((side, side, 3), np.uint8)
    h = side // 2
    crop[:h, :h] = (255, 0, 0)    # 왼쪽 위만 빨강
    x = embedder.to_input(crop)
    assert x.shape == (112, 112, 3) and x.dtype == np.uint8
    # 크롭 전체를 축소하므로(잘라내지 않음) 왼쪽 위 사분면이 그대로 남는다
    assert tuple(x[10, 10]) == (255, 0, 0) and tuple(x[100, 100]) == (0, 0, 0)


def test_embedder_feeds_112_rgb_and_returns_normalized_512(monkeypatch):
    fake = FakeRecognizer()
    monkeypatch.setattr(embedder, "_recognizer", fake)
    out = FaceEngine("t", DummyDetector(), embedder.AdaFaceEmbedder()).detect_and_embed(face_array(1))
    assert len(out) == 1
    vec = out[0][1]
    assert vec.shape == (512,) and vec.dtype == np.float32
    assert np.allclose(vec[:2], [0.6, 0.8])
    (batch,) = fake.inputs
    assert batch.shape == (1, 112, 112, 3) and batch.dtype == np.uint8


# ---------- 실제 모델 (로컬 전용) ----------
needs_weight = pytest.mark.skipif(not WEIGHT_PATH.exists(), reason="AdaFace 가중치가 없음")


@needs_weight
def test_real_adaface_embedding():
    emb = embedder.AdaFaceEmbedder()
    a = emb.embed(face_array(1, 200))
    b = emb.embed(face_array(1, 200))
    c = emb.embed(face_array(2, 200))
    assert a.shape == (512,) and a.dtype == np.float32 and np.all(np.isfinite(a))
    assert abs(np.linalg.norm(a) - 1) < 1e-5
    assert np.allclose(a, b, atol=1e-5)  # 같은 입력 → 같은 벡터
    assert float(a @ c) < 0.99
