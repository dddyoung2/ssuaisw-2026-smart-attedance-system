"""정렬·크롭(align.py) 테스트. 가중치·사진 없이 코드로 만든 이미지로 확인한다(CI에서도 실행)."""
import numpy as np
import pytest

from backend.engines.align import align_face, to_xywh


def make_landmarks(cx, cy, eye_dist, angle_deg=0.0):
    """두 눈 중점이 (cx, cy)이고 angle_deg만큼 기울어진 좌우 대칭 얼굴의 5점."""
    base = np.array([[-0.5, 0.0], [0.5, 0.0], [0.0, 0.45], [-0.4, 0.9], [0.4, 0.9]]) * eye_dist
    t = np.radians(angle_deg)
    rot = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    return base @ rot.T + [cx, cy]


@pytest.mark.parametrize("angle", [0.0, 15.0, -30.0])
def test_square_uint8_and_size(angle):
    photo = np.zeros((800, 800, 3), np.uint8)
    img = align_face(photo, make_landmarks(400, 400, 100, angle))
    # 한 변 = round(max(눈 사이 × 4, 눈–입 × 3.6)) = round(max(400, 324)) = 400
    assert img.shape == (400, 400, 3)
    assert img.dtype == np.uint8


def test_no_resize_and_center():
    # 기울기 0: 중심 c = 눈 중점 + 눈–입 × 0.1 = (400, 409). c 둘레 40×40 흰 사각형이
    # 결과 정중앙(200, 200) 둘레에 크기 그대로 40×40으로 나와야 한다.
    photo = np.zeros((800, 800, 3), np.uint8)
    photo[409 - 20:409 + 20, 400 - 20:400 + 20] = 255
    img = align_face(photo, make_landmarks(400, 400, 100))
    white = np.argwhere(img[:, :, 0] == 255)
    assert len(white) == 40 * 40
    assert white.min(0).tolist() == [180, 180]
    assert white.max(0).tolist() == [219, 219]


def test_rotation_levels_eyes_without_scaling():
    # 30도 기울어진 얼굴의 두 눈 위치에 점을 찍고, 정렬 후 두 점이 수평이며 거리가 그대로인지 본다.
    lm = make_landmarks(400, 400, 100, 30.0)
    photo = np.zeros((800, 800, 3), np.uint8)
    for x, y in lm[:2]:
        photo[int(round(y)) - 2:int(round(y)) + 3, int(round(x)) - 2:int(round(x)) + 3] = 255
    img = align_face(photo, lm)
    mask = img[:, :, 0] > 0
    ys, xs = np.nonzero(mask)
    left, right = xs < img.shape[1] / 2, xs >= img.shape[1] / 2
    weights = img[:, :, 0][mask].astype(float)
    ly, lx = np.average(ys[left], weights=weights[left]), np.average(xs[left], weights=weights[left])
    ry, rx = np.average(ys[right], weights=weights[right]), np.average(xs[right], weights=weights[right])
    assert abs(ly - ry) < 1.0                      # 두 눈 수평
    assert abs(np.hypot(rx - lx, ry - ly) - 100) < 1.0   # 눈 사이 거리 그대로 (배율 1)


def test_outside_photo_is_black():
    # 얼굴이 사진 왼쪽 위 모서리에 걸리면 사진 밖 영역은 검은색이어야 한다.
    photo = np.full((300, 300, 3), 200, np.uint8)
    img = align_face(photo, make_landmarks(20, 20, 40))
    assert img[0, 0].tolist() == [0, 0, 0]
    assert img[img.shape[0] // 2, img.shape[1] // 2].tolist() == [200, 200, 200]


def test_to_xywh_int_and_clipped():
    assert to_xywh([10.4, 20.6, 110.2, 140.9, 0.99], 400, 300) == (10, 21, 100, 120)
    assert to_xywh([-3.4, -1.0, 50.2, 70.7], 400, 300) == (0, 0, 50, 71)
    assert to_xywh([390.0, 290.0, 420.0, 330.0], 400, 300) == (390, 290, 10, 10)
    assert all(type(v) is int for v in to_xywh(np.float32([1.5, 2.5, 3.5, 4.5]), 10, 10))