"""카메라 미리보기: 축소한 프레임에서 얼굴 검출만 한다.

출석 판정(POST /lectures/{id}/photos)은 원본 해상도로 검출 → 정렬 → 인식을 하고,
여기서는 화면에 박스를 그리기 위해 긴 변 PREVIEW_MAX_SIDE 이하로 줄인 이미지로 검출만 한다.
줄인 이미지에서는 작은 얼굴이 빠질 수 있으므로 미리보기 박스 수 ≠ 출석 판정의 얼굴 수.
"""
from __future__ import annotations

import cv2
import numpy as np

from ..face_engine import BBox, FaceEngine

#: 미리보기 검출 해상도(긴 변, px). 화면(camera.js)도 이 크기로 줄여 보낸다.
#: CPU 기준 960px 한 장 약 0.75~1초 (원본 12MP 는 약 19초).
PREVIEW_MAX_SIDE = 960


def detect_preview(image: np.ndarray, engine: FaceEngine) -> list[BBox]:
    """image: RGB uint8 (H, W, 3). 반환 박스는 받은 image 의 픽셀 좌표.
    긴 변이 PREVIEW_MAX_SIDE 보다 크면 줄여서 검출하고 좌표를 되돌린다."""
    h, w = image.shape[:2]
    scale = PREVIEW_MAX_SIDE / max(h, w)
    if scale >= 1:
        return engine.detect(image)
    small = cv2.resize(image, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    boxes = []
    for x, y, bw, bh in engine.detect(small):
        x1, y1 = min(w, round(x / scale)), min(h, round(y / scale))
        x2, y2 = min(w, round((x + bw) / scale)), min(h, round((y + bh) / scale))
        boxes.append((x1, y1, x2 - x1, y2 - y1))
    return boxes
