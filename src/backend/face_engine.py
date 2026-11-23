"""얼굴 엔진: 백엔드가 얼굴 모델을 부르는 입구.

검출과 정렬은 engines/ 가 맡는다(engines/fd_pipeline.py 의 detect_and_align).
실제 인식 모델(AdaFace)은 engines/embedder.py 에 있다.
이 파일은 그 결과를 받아
  - FACE_ENGINE 값으로 엔진 고르기 (레지스트리)
  - 정렬된 얼굴 → 임베더(인식 모델) → 임베딩 형식 검사
만 한다. DB 조회·비교·저장은 백엔드 서비스(services/)가 한다. 규칙은 docs/face_engine_guide.md 참고.

  입력 사진 : numpy.ndarray, shape (H, W, 3), dtype uint8, RGB, 원본 크기
  검출기    : detect(photo) → (dets (N, 5) [x1, y1, x2, y2, score], landms (N, 5, 2))
              engines/detector.py 의 RetinaFaceDetector 와 같은 형식
  정렬 얼굴 : (S, S, 3) uint8 RGB 정사각형, CelebA-HQ 방식, 리사이즈 없음 (engines/align.py)
  embed()   : 정렬 얼굴 → shape (D,) float32, L2 정규화된 벡터.
              모델 입력 크기에 맞춘 리사이즈 등 전처리는 임베더 안에서 한다.

새 구현은 register_engine("이름", 팩토리)로 등록하고 환경변수 FACE_ENGINE=이름 으로 고른다.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

BBox = tuple[int, int, int, int]  # (x, y, w, h), 원본 픽셀 정수


# ---------------------------------------------------------------------------
# 인식 모델 인터페이스
# ---------------------------------------------------------------------------
class FaceEmbedder(ABC):
    #: 임베딩 차원. 바뀌면 학생 임베딩을 다시 계산해야 한다(scripts/compute_embeddings.py).
    dim: int

    @abstractmethod
    def embed(self, face_image: np.ndarray) -> np.ndarray:
        """정렬된 얼굴 RGB uint8 (S, S, 3), 리사이즈 전 → L2 정규화된 (dim,) float32 벡터."""


# ---------------------------------------------------------------------------
# 엔진: 검출·정렬(engines/fd_pipeline) + 임베더를 묶고, 출력 형식을 검증한다.
# ---------------------------------------------------------------------------
class FaceEngine:
    def __init__(self, name: str, detector, embedder: FaceEmbedder):
        """detector: detect(photo) → (dets, landms) 를 가진 객체.
        None 이면 fd_pipeline.get_detector() 의 RetinaFace 를 쓴다(처음 쓸 때 한 번만 로드)."""
        self.name = name
        self.detector = detector
        self.embedder = embedder

    @property
    def dim(self) -> int:
        return int(self.embedder.dim)

    def embed(self, face_image: np.ndarray) -> np.ndarray:
        _check_image(face_image)
        vec = np.asarray(self.embedder.embed(face_image), dtype=np.float32).reshape(-1)
        if vec.shape[0] != self.dim:
            raise ValueError(f"임베딩 차원 불일치: embedder.dim={self.dim}, 실제={vec.shape[0]}")
        if not np.all(np.isfinite(vec)):
            raise ValueError("임베딩에 NaN/inf 값이 있습니다.")
        norm = float(np.linalg.norm(vec))
        if norm < 1e-12:
            raise ValueError("임베딩 벡터의 크기가 0입니다.")
        # 구현이 정규화를 빠뜨려도 안전하도록 한 번 더 정규화
        return (vec / norm).astype(np.float32)

    def detect_and_embed(self, photo: np.ndarray) -> list[tuple[BBox, np.ndarray]]:
        """사진 한 장 → [(검출 박스, 임베딩), ...]. 검출·정렬은 fd_pipeline, 그 뒤 임베딩."""
        _check_image(photo)
        # torch 를 쓰는 검출 코드는 실제로 사진을 처리할 때만 불러온다.
        from .engines.fd_pipeline import detect_and_align

        boxes, images = detect_and_align(photo, detector=self.detector)
        return [(box, self.embed(img)) for box, img in zip(boxes, images)]


def _check_image(image: np.ndarray) -> None:
    if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("이미지는 (H, W, 3) numpy 배열이어야 합니다.")
    if image.dtype != np.uint8:
        raise ValueError("이미지 dtype 은 uint8 이어야 합니다.")


# ---------------------------------------------------------------------------
# 더미 구현 (가중치 없이 돌리는 테스트·CI용)
# ---------------------------------------------------------------------------
#: 박스 안의 가짜 5점 위치(박스 기준 비율). 순서: 왼눈, 오른눈, 코, 왼입꼬리, 오른입꼬리
_DUMMY_LANDMARKS = np.array([[0.3, 0.4], [0.7, 0.4], [0.5, 0.6], [0.35, 0.8], [0.65, 0.8]])


class DummyDetector:
    """규칙 기반 가짜 검출기. 반환 형식은 RetinaFaceDetector.detect() 와 같다.

    - 거의 단색인 이미지(표준편차 < 2)  → 얼굴 0개
    - 가로가 세로의 2배 이상인 이미지     → 세로 길이의 정사각형 칸으로 나눠 칸마다 얼굴 1개
    - 그 외                                → 이미지 중앙에 얼굴 1개
    각 칸(또는 이미지)의 가운데 절반 영역을 박스로, 박스 안의 고정 비율 위치를 5점으로 본다.
    """

    def detect(self, photo: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        h, w = photo.shape[:2]
        if float(photo.std()) < 2.0:
            return np.zeros((0, 5), np.float32), np.zeros((0, 5, 2), np.float32)
        cells = w // h if w >= 2 * h else 1
        cell_w = w // cells
        dets, landms = [], []
        for i in range(cells):
            x1, y1 = i * cell_w + cell_w // 4, h // 4
            bw, bh = cell_w // 2, h // 2
            dets.append([x1, y1, x1 + bw, y1 + bh, 1.0])
            landms.append(_DUMMY_LANDMARKS * [bw, bh] + [x1, y1])
        return np.asarray(dets, np.float32), np.asarray(landms, np.float32)


class DummyEmbedder(FaceEmbedder):
    """이미지 내용 기반의 결정적 가짜 임베딩.

    흑백 변환 → 16x8 축소 → 평균 제거 → L2 정규화 (128차원).
    같은 이미지는 항상 같은 벡터, 비슷한 이미지는 높은 유사도가 나온다.
    """

    dim = 128

    def embed(self, face_image: np.ndarray) -> np.ndarray:
        gray = Image.fromarray(face_image).convert("L").resize((16, 8), Image.BILINEAR)
        vec = np.asarray(gray, dtype=np.float32).reshape(-1)
        vec -= vec.mean()
        norm = float(np.linalg.norm(vec))
        if norm < 1e-6:  # 완전 단색 얼굴 → 고정 벡터
            vec = np.zeros(self.dim, dtype=np.float32)
            vec[0] = 1.0
            return vec
        return (vec / norm).astype(np.float32)


# ---------------------------------------------------------------------------
# 레지스트리: FACE_ENGINE 값 → 엔진 생성 함수
# ---------------------------------------------------------------------------
_REGISTRY: dict[str, Callable[[], FaceEngine]] = {}


def register_engine(name: str, factory: Callable[[], FaceEngine]) -> None:
    _REGISTRY[name.lower()] = factory


def available_engines() -> list[str]:
    return sorted(_REGISTRY)


def create_face_engine(name: str) -> FaceEngine:
    key = name.lower()
    if key not in _REGISTRY:
        raise ValueError(
            f"알 수 없는 FACE_ENGINE='{name}'. 사용 가능: {', '.join(available_engines())}"
        )
    engine = _REGISTRY[key]()
    logger.info("얼굴 엔진 로드: %s (임베딩 %d차원)", engine.name, engine.dim)
    return engine


register_engine("dummy", lambda: FaceEngine("dummy", DummyDetector(), DummyEmbedder()))

# 검출: RetinaFace (engines/detector.py). detector=None 이라 fd_pipeline.get_detector() 로 한 번만 로드.
# 인식: AdaFace (engines/embedder.py). 가중치는 처음 임베딩할 때 embedder.get_recognizer() 로 한 번만 로드.
# 두 가중치 모두 README "가중치 다운로드" 참고. 서버 시작 시에는 모델을 불러오지 않는다.
def _make_retinaface() -> FaceEngine:
    from .engines.embedder import AdaFaceEmbedder

    return FaceEngine("retinaface", None, AdaFaceEmbedder())


register_engine("retinaface", _make_retinaface)
