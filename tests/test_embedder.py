"""인식(AdaFace 임베더) 테스트.
- 입력 변환·연결 규격: 가짜 인식기로 어디서나 실행(CI 포함)
- 실제 AdaFace 테스트: 가중치가 있을 때만 실행, 없으면 건너뜀
전처리 규칙은 FR 쪽 FR_draft 실사용 코드(fr_draft/attendance.py)와 같다."""
import cv2
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

    def encode_rgb(self, images, batch_size=32):
        self.inputs.append(images)
        out = np.zeros((len(images), 512), np.float32)
        out[:, 0], out[:, 1] = 3, 4
        return out


class OneHotRecognizer(FakeRecognizer):
    """i 번째 입력 → i 번째 축 단위벡터 (평균이 제대로 되는지 보기 위함)."""

    def encode_rgb(self, images, batch_size=32):
        self.inputs.append(images)
        return np.eye(512, dtype=np.float32)[: len(images)]


# ---------- 입력 변환 (FR_draft model_input 과 같음) ----------
@pytest.mark.parametrize("shape", [(50, 50), (112, 112), (300, 300), (30, 80)])
def test_to_input_is_bicubic_resize_of_whole_crop(shape):
    rng = np.random.default_rng(0)
    crop = rng.integers(0, 256, (*shape, 3), dtype=np.uint8)
    x = embedder.to_input(crop)
    assert x.shape == (112, 112, 3) and x.dtype == np.uint8
    assert np.array_equal(x, cv2.resize(crop, (112, 112), interpolation=cv2.INTER_CUBIC))


@pytest.mark.parametrize("side", [50, 300])
def test_to_input_keeps_whole_crop(side):
    crop = np.zeros((side, side, 3), np.uint8)
    h = side // 2
    crop[:h, :h] = (255, 0, 0)    # 왼쪽 위만 빨강
    x = embedder.to_input(crop)
    # 크롭 전체를 맞추므로(잘라내지 않음) 왼쪽 위 사분면이 그대로 남는다
    assert tuple(x[10, 10]) == (255, 0, 0) and tuple(x[100, 100]) == (0, 0, 0)


# ---------- 등록용 여러 크기 뷰 (FR_draft anchor_views 와 같음) ----------
@pytest.mark.parametrize(
    "shape, labels",
    [
        ((32, 32), ["native", "16", "24", "32"]),            # 같은 크기 레벨도 포함
        ((20, 40), ["native", "16"]),                        # min(H, W) 기준
        ((112, 112), ["native", "16", "24", "32", "48", "64", "96"]),
        ((300, 300), ["native", "16", "24", "32", "48", "64", "96", "128", "256"]),
        ((1024, 1024), ["native", "16", "24", "32", "48", "64", "96", "128", "256", "512"]),
        ((10, 10), ["native"]),
    ],
)
def test_anchor_views_size_policy(shape, labels):
    img = np.random.default_rng(1).integers(0, 256, (*shape, 3), dtype=np.uint8)
    got, views = embedder.anchor_views(img)
    assert got == labels
    assert views.shape == (len(labels), 112, 112, 3) and views.dtype == np.uint8
    assert np.array_equal(views[0], embedder.to_input(img))  # 첫 뷰 = 원본
    if len(labels) > 1:  # 축소 뷰 = AREA 로 정사각형 축소 → Bicubic 112
        small = cv2.resize(img, (16, 16), interpolation=cv2.INTER_AREA)
        assert np.array_equal(views[1], embedder.to_input(small))


# ---------- 임베더 연결 규격 (가짜 인식기) ----------
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


def test_faces_in_one_photo_are_embedded_in_one_call(monkeypatch):
    fake = OneHotRecognizer()
    monkeypatch.setattr(embedder, "_recognizer", fake)
    photo = np.hstack([face_array(i, 100) for i in range(3)])  # 더미 검출기: 얼굴 3개
    out = FaceEngine("t", DummyDetector(), embedder.AdaFaceEmbedder()).detect_and_embed(photo)
    assert len(out) == 3 and len(fake.inputs) == 1 and fake.inputs[0].shape == (3, 112, 112, 3)
    for i, (_, vec) in enumerate(out):  # 입력 순서 = 결과 순서
        assert vec[i] == 1.0


def test_embed_anchor_is_normalized_mean_of_views(monkeypatch):
    fake = OneHotRecognizer()
    monkeypatch.setattr(embedder, "_recognizer", fake)
    face = face_array(1, 32)  # 32x32 → native·16·24·32 = 4뷰
    vec = embedder.AdaFaceEmbedder().embed_anchor(face)
    (views,) = fake.inputs
    assert views.shape == (4, 112, 112, 3)
    assert vec.dtype == np.float32 and np.allclose(vec[:4], 0.5) and np.allclose(vec[4:], 0)


def test_engine_detect_and_embed_anchor_uses_embed_anchor(monkeypatch):
    fake = OneHotRecognizer()
    monkeypatch.setattr(embedder, "_recognizer", fake)
    eng = FaceEngine("t", DummyDetector(), embedder.AdaFaceEmbedder())
    ((box, vec),) = eng.detect_and_embed_anchor(face_array(1, 200))
    assert len(box) == 4
    (views,) = fake.inputs
    assert len(views) > 1  # 여러 크기 뷰를 넣었다
    assert abs(np.linalg.norm(vec) - 1) < 1e-6


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


@needs_weight
def test_real_adaface_batch_and_anchor():
    emb = embedder.AdaFaceEmbedder()
    faces = [face_array(i, 150) for i in range(3)]
    batch = emb.embed_batch(faces)
    assert batch.shape == (3, 512)
    for face, vec in zip(faces, batch):  # 묶어서 해도 하나씩 한 것과 같다
        assert np.allclose(vec, emb.embed(face), atol=1e-4)
    anchor = emb.embed_anchor(faces[0])
    assert anchor.shape == (512,) and abs(np.linalg.norm(anchor) - 1) < 1e-5
    assert np.allclose(anchor, emb.embed_anchor(faces[0]), atol=1e-5)
