"""얼굴 정렬·크롭: CelebA-HQ 방식(ProGAN 공개 코드)의 중심·크기·방향을 따르는 정사각형.
리사이즈 없음: 회전과 이동만 하고 배율은 정확히 1."""
import cv2
import numpy as np


def align_face(photo_rgb, landmarks):
    """photo_rgb: (H, W, 3) uint8 RGB 원본
    landmarks: (5, 2) 원본 좌표 (왼눈, 오른눈, 코, 왼입꼬리, 오른입꼬리)
    반환: (S, S, 3) uint8 RGB 정사각형. S = round(max(눈 사이 × 4, 눈–입 × 3.6))"""
    lm = np.asarray(landmarks, dtype=np.float64)
    eye_avg = (lm[0] + lm[1]) * 0.5
    mouth_avg = (lm[3] + lm[4]) * 0.5
    eye_to_eye = lm[1] - lm[0]
    eye_to_mouth = mouth_avg - eye_avg

    x = eye_to_eye - np.flipud(eye_to_mouth) * [-1, 1]      # 가로 방향
    u = x / np.hypot(*x)                                     # 가로 단위벡터
    v = np.array([-u[1], u[0]])                              # 세로 단위벡터 (u를 90도 회전)
    c = eye_avg + eye_to_mouth * 0.1                         # 중심: 눈 중점에서 입 쪽으로 10%
    side = max(1, round(max(np.hypot(*eye_to_eye) * 4.0, np.hypot(*eye_to_mouth) * 3.6)))  # 정수 한 변

    # 회전 + 이동만 (배율 1): 원본 점 p → (u·(p-c) + side/2, v·(p-c) + side/2)
    M = np.array([[u[0], u[1], side / 2 - u @ c],
                  [v[0], v[1], side / 2 - v @ c]])
    return cv2.warpAffine(photo_rgb, M, (side, side), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))


def to_xywh(box, img_w, img_h):
    """[x1, y1, x2, y2] 소수 → (x, y, w, h) 정수, 사진 범위 안으로 자름."""
    x1, y1 = max(0, round(float(box[0]))), max(0, round(float(box[1])))
    x2, y2 = min(img_w, round(float(box[2]))), min(img_h, round(float(box[3])))
    return (x1, y1, max(0, x2 - x1), max(0, y2 - y1))