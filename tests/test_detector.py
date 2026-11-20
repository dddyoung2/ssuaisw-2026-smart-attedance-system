"""검출·인계 출력 테스트.
- 가짜 검출기로 출력 규격을 확인하는 테스트: 어디서나 실행(CI 포함)
- 실제 RetinaFace 테스트: 가중치와 input-img 사진이 있을 때만 실행, 없으면 건너뜀"""
from pathlib import Path

import numpy as np
import pytest

from backend.engines import fd_pipeline
from backend.engines.detector import WEIGHT_PATH

IMG_DIR = Path(fd_pipeline.__file__).resolve().parent / "retinaface" / "test" / "input-img"
PHOTOS = sorted(p for p in IMG_DIR.glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"}) if IMG_DIR.exists() else []


class FakeDetector:
    """detect()가 정해 둔 박스·5점을 그대로 돌려주는 가짜 검출기."""

    def __init__(self, dets, landms):
        self.dets, self.landms = dets, landms

    def detect(self, photo_rgb):
        return self.dets, self.landms


def face_landmarks(x1, y1, x2, y2):
    """박스 안에 들어가는 좌우 대칭 5점."""
    w, h = x2 - x1, y2 - y1
    rel = np.array([[0.3, 0.4], [0.7, 0.4], [0.5, 0.6], [0.35, 0.8], [0.65, 0.8]])
    return rel * [w, h] + [x1, y1]


# ---------- 출력 규격 (가짜 검출기) ----------
def test_output_contract():
    photo = np.full((300, 400, 3), 100, np.uint8)
    dets = np.array([[10.4, 20.6, 110.2, 140.9, 0.99], [-5.0, 250.0, 60.0, 320.0, 0.95]], np.float32)
    landms = np.stack([face_landmarks(*d[:4]) for d in dets]).astype(np.float32)
    boxes, images = fd_pipeline.detect_and_align(photo, detector=FakeDetector(dets, landms))

    assert len(boxes) == len(images) == 2
    assert boxes[0] == (10, 21, 100, 120)
    for (x, y, w, h), img in zip(boxes, images):
        assert all(type(v) is int for v in (x, y, w, h))
        assert 0 <= x and 0 <= y and x + w <= 400 and y + h <= 300
        assert img.ndim == 3 and img.shape[0] == img.shape[1] and img.shape[2] == 3
        assert img.dtype == np.uint8


def test_no_face_returns_empty_lists():
    empty = FakeDetector(np.zeros((0, 5), np.float32), np.zeros((0, 5, 2), np.float32))
    assert fd_pipeline.detect_and_align(np.zeros((300, 400, 3), np.uint8), detector=empty) == ([], [])


# ---------- 실제 모델 (로컬 전용) ----------
needs_real = pytest.mark.skipif(not WEIGHT_PATH.exists() or not PHOTOS,
                                reason="가중치 또는 input-img 사진이 없음")


@pytest.fixture(scope="module")
def real_result():
    from backend.services.storage import decode_image
    photo = decode_image(PHOTOS[0].read_bytes())
    det = fd_pipeline.get_detector()
    dets, landms = det.detect(photo)
    boxes, images = fd_pipeline.detect_and_align(photo, detector=det)
    return photo, dets, landms, boxes, images


@needs_real
def test_real_detector_shapes_and_order(real_result):
    photo, dets, landms, _, _ = real_result
    assert dets.ndim == 2 and dets.shape[1] == 5
    assert landms.shape == (len(dets), 5, 2)
    assert np.all(dets[:, 4] > 0.9)                      # 운영 임계값 0.90 초과만
    assert np.all(np.diff(dets[:, 4]) <= 1e-6)            # 신뢰도 높은 순


@needs_real
def test_real_landmarks_inside_boxes(real_result):
    _, dets, landms, _, _ = real_result
    x_ok = (landms[..., 0] >= dets[:, None, 0] - 2) & (landms[..., 0] <= dets[:, None, 2] + 2)
    y_ok = (landms[..., 1] >= dets[:, None, 1] - 2) & (landms[..., 1] <= dets[:, None, 3] + 2)
    assert np.all(x_ok & y_ok)
    assert np.all(landms[:, 0, 0] < landms[:, 1, 0])     # 왼눈 x < 오른눈 x


@needs_real
def test_real_fd_pipeline_output(real_result):
    photo, dets, _, boxes, images = real_result
    h, w = photo.shape[:2]
    assert len(boxes) == len(images) == len(dets)
    for (x, y, bw, bh), img in zip(boxes, images):
        assert 0 <= x and 0 <= y and x + bw <= w and y + bh <= h
        assert img.shape[0] == img.shape[1] and img.dtype == np.uint8