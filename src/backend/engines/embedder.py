"""인식: 정렬 얼굴(fd_pipeline 출력) → AdaFace 512차원 임베딩."""
import threading

import cv2
import numpy as np

from ..face_engine import FaceEmbedder

INPUT_SIZE = 112           # AdaFace 입력 한 변

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
    """(S, S, 3) uint8 RGB CelebA-HQ 크롭 → (112, 112, 3) uint8 RGB. 크롭 전체를 그대로 축소한다."""
    interp = cv2.INTER_AREA if face_rgb.shape[0] > INPUT_SIZE else cv2.INTER_LINEAR
    return cv2.resize(face_rgb, (INPUT_SIZE, INPUT_SIZE), interpolation=interp)

class AdaFaceEmbedder(FaceEmbedder):
    """AdaFace IR101 / WebFace12M (CVLFace 원본 가중치). 입력 RGB, pixel / 127.5 - 1 은 로더가 한다."""

    dim = 512

    def embed(self, face_image):
        vec = get_recognizer().encode_rgb(to_input(face_image)[None])[0]
        return (vec / max(float(np.linalg.norm(vec)), 1e-12)).astype(np.float32)
