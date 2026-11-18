"""B′ 정렬: 두 눈 수평 회전 + 얼굴 중심을 정중앙에, 검출 박스 1.3배 크기로 원본에서 잘라냄. 리사이즈 없음."""
import math

import cv2
import numpy as np

MARGIN = 1.3   # 크롭 크기 = 검출 박스 × 1.3 (임시 확정)

def align_face(photo_rgb, box, landmarks, margin=MARGIN):
    """photo_rgb: (H, W, 3) uint8 RGB 원본
    box: [x1, y1, x2, y2] 원본 좌표, landmarks: (5, 2) 원본 좌표 (왼눈, 오른눈, 코, 왼입, 오른입)
    반환: (round(1.3h), round(1.3w), 3) uint8 RGB"""
    x1, y1, x2, y2 = box[:4]
    w, h = x2 - x1, y2 - y1
    le, re, _, lm, rm = np.asarray(landmarks, dtype=np.float64)

    cx, cy = ((le + re) / 2 + (lm + rm) / 2) / 2                    # 얼굴 중심: 눈 중점과 입 중점의 가운데
    angle = math.degrees(math.atan2(re[1] - le[1], re[0] - le[0]))  # 두 눈 기울기
    cw, ch = max(1, round(margin * w)), max(1, round(margin * h))

    M = cv2.getRotationMatrix2D((float(cx), float(cy)), angle, 1.0)  # 중심 기준 회전, 배율 1
    M[0, 2] += cw / 2 - cx                                          # 중심을 결과 정중앙으로
    M[1, 2] += ch / 2 - cy
    return cv2.warpAffine(photo_rgb, M, (cw, ch), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))


def to_xywh(box, img_w, img_h):
    """[x1, y1, x2, y2] 소수 → (x, y, w, h) 정수, 사진 범위 안으로 자름."""
    x1, y1 = max(0, round(float(box[0]))), max(0, round(float(box[1])))
    x2, y2 = min(img_w, round(float(box[2]))), min(img_h, round(float(box[3])))
    return (x1, y1, max(0, x2 - x1), max(0, y2 - y1))