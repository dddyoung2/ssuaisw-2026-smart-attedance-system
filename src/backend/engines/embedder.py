"""인식: 정렬 얼굴(fd_pipeline 출력) → AdaFace 512차원 임베딩.

전처리는 FR 쪽 FR_draft 실사용 코드(fr_draft/attendance.py)와 같다.
  - 모델 입력: 정렬 얼굴 크롭 전체를 Bicubic 으로 112×112 (정사각형이 아니면 가로·세로를 각각 맞춤)
  - 학생 등록(증명사진): 원본 크롭 1장 + 크롭보다 크지 않은 ANCHOR_LEVELS 크기로 AREA 축소한 뷰들을
    각각 임베딩한 뒤 평균 내고 다시 L2 정규화 (여러 크기 평균)
"""
import threading

import cv2
import numpy as np

from ..face_engine import FaceEmbedder

INPUT_SIZE = 112           # AdaFace 입력 한 변
ANCHOR_LEVELS = (16, 24, 32, 48, 64, 96, 128, 256, 512)  # 등록 사진 축소 뷰 크기
BATCH_SIZE = 32            # 한 번에 모델에 넣는 얼굴 수

_recognizer = None
_lock = threading.Lock()

# load face-recognizer with its weight (처음 쓸 때 한 번만, torch 도 이때 불러온다)
def get_recognizer():
    global _recognizer
    with _lock:
        if _recognizer is None:
            from .adaface.model import AdaFaceRecognizer
            _recognizer = AdaFaceRecognizer()
    return _recognizer

def to_input(face_rgb):
    """(H, W, 3) uint8 RGB 정렬 얼굴 → (112, 112, 3) uint8 RGB. 크롭 전체를 Bicubic 으로 맞춘다."""
    return cv2.resize(face_rgb, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_CUBIC)

def anchor_views(face_rgb):
    """등록용 뷰: 원본 1장 + min(H, W) 이하인 ANCHOR_LEVELS 크기로 AREA 축소한 정사각형.
    반환: (뷰 이름 목록, (N, 112, 112, 3) uint8) — 뷰 이름은 "native", "16", "24", ..."""
    limit = min(face_rgb.shape[:2])
    labels = ["native"] + [str(level) for level in ANCHOR_LEVELS if level <= limit]
    views = [to_input(face_rgb)]
    for level in ANCHOR_LEVELS:
        if level <= limit:
            small = cv2.resize(face_rgb, (level, level), interpolation=cv2.INTER_AREA)
            views.append(to_input(small))
    return labels, np.stack(views)

def _unit_rows(vecs):
    vecs = np.asarray(vecs, dtype=np.float32)
    norms = np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-12)
    return (vecs / norms).astype(np.float32)

class AdaFaceEmbedder(FaceEmbedder):
    """AdaFace IR101 (파인튜닝 가중치 adaface_weight.pt). 입력 RGB, pixel / 127.5 - 1 은 로더가 한다."""

    dim = 512

    def embed(self, face_image):
        return self.embed_batch([face_image])[0]

    def embed_batch(self, face_images):
        """한 사진의 얼굴들을 BATCH_SIZE 개씩 묶어 한 번에 임베딩 → (N, 512)."""
        if not len(face_images):
            return np.zeros((0, self.dim), np.float32)
        inputs = np.stack([to_input(f) for f in face_images])
        return _unit_rows(get_recognizer().encode_rgb(inputs, BATCH_SIZE))

    def embed_anchor(self, face_image):
        """학생 등록(증명사진)용: 여러 크기 뷰의 임베딩 평균 → L2 정규화."""
        _, views = anchor_views(face_image)
        mean = _unit_rows(get_recognizer().encode_rgb(views, BATCH_SIZE)).mean(axis=0)
        return (mean / max(float(np.linalg.norm(mean)), 1e-12)).astype(np.float32)
