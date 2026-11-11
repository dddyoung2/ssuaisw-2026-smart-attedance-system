"""얼굴 검출/임베딩 연결부.

팀원이 실제 모델을 끼워 넣는 곳. 규칙은 docs/face_engine_guide.md 참고.

  입력 이미지 : numpy.ndarray, shape (H, W, 3), dtype uint8, **RGB** 순서
  detect()    : [(x, y, w, h), ...]  (정수 픽셀, 좌상단 기준)
  embed()     : shape (D,) float32, L2 정규화된 벡터

새 구현은 register_engine("이름", 팩토리)로 등록하고 환경변수 FACE_ENGINE=이름 으로 고른다.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

BBox = tuple[int, int, int, int]  # (x, y, w, h)


# ---------------------------------------------------------------------------
# 인터페이스
# ---------------------------------------------------------------------------
class FaceDetector(ABC):
    @abstractmethod
    def detect(self, image: np.ndarray) -> list[BBox]:
        """RGB uint8 (H, W, 3) 이미지 → 얼굴 bbox 리스트 [(x, y, w, h), ...]."""


class FaceEmbedder(ABC):
    #: 임베딩 차원. 바뀌면 기존 임베딩을 재계산해야 한다.
    dim: int

    @abstractmethod
    def embed(self, face_image: np.ndarray) -> np.ndarray:
        """잘라낸 얼굴 RGB uint8 (h, w, 3) → L2 정규화된 (dim,) float32 벡터."""


# ---------------------------------------------------------------------------
# 엔진: 검출기 + 임베더를 묶고, 출력 형식을 검증한다.
# ---------------------------------------------------------------------------
class FaceEngine:
    def __init__(self, name: str, detector: FaceDetector, embedder: FaceEmbedder):
        self.name = name
        self.detector = detector
        self.embedder = embedder

    @property
    def dim(self) -> int:
        return int(self.embedder.dim)

    def detect(self, image: np.ndarray) -> list[BBox]:
        _check_image(image)
        h, w = image.shape[:2]
        boxes: list[BBox] = []
        for box in self.detector.detect(image):
            clipped = clip_bbox(box, w, h)
            if clipped is not None:
                boxes.append(clipped)
        return boxes

    def embed(self, face_image: np.ndarray) -> np.ndarray:
        _check_image(face_image)
        vec = np.asarray(self.embedder.embed(face_image), dtype=np.float32).reshape(-1)
        if vec.shape[0] != self.dim:
            raise ValueError(
                f"임베딩 차원 불일치: embedder.dim={self.dim}, 실제={vec.shape[0]}"
            )
        if not np.all(np.isfinite(vec)):
            raise ValueError("임베딩에 NaN/inf 값이 있습니다.")
        # 구현이 정규화를 빠뜨려도 안전하도록 한 번 더 정규화
        norm = float(np.linalg.norm(vec))
        if norm < 1e-12:
            raise ValueError("임베딩 벡터의 크기가 0입니다.")
        return (vec / norm).astype(np.float32)

    def detect_and_embed(self, image: np.ndarray) -> list[tuple[BBox, np.ndarray]]:
        return [(box, self.embed(crop(image, box))) for box in self.detect(image)]


def _check_image(image: np.ndarray) -> None:
    if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("이미지는 (H, W, 3) numpy 배열이어야 합니다.")
    if image.dtype != np.uint8:
        raise ValueError("이미지 dtype 은 uint8 이어야 합니다.")


def clip_bbox(box, img_w: int, img_h: int) -> BBox | None:
    """bbox 를 정수로 바꾸고 이미지 범위 안으로 자른다. 면적이 0이면 None."""
    x, y, w, h = (int(round(float(v))) for v in box)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(img_w, x + w), min(img_h, y + h)
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


def crop(image: np.ndarray, box: BBox) -> np.ndarray:
    x, y, w, h = box
    return np.ascontiguousarray(image[y : y + h, x : x + w])


# ---------------------------------------------------------------------------
# 더미 구현 (모델 확정 전 데모/테스트용)
# ---------------------------------------------------------------------------
class DummyDetector(FaceDetector):
    """규칙 기반 가짜 검출기.

    - 거의 단색인 이미지(표준편차 < 2)  → 얼굴 0개
    - 가로가 세로의 2배 이상인 이미지     → 세로 길이의 정사각형 칸으로 나눠 칸마다 얼굴 1개
    - 그 외                                → 이미지 중앙에 얼굴 1개
    각 칸(또는 이미지)의 가운데 절반 영역을 얼굴 bbox 로 본다.
    """

    def detect(self, image: np.ndarray) -> list[BBox]:
        h, w = image.shape[:2]
        if float(image.std()) < 2.0:
            return []
        cells = w // h if w >= 2 * h else 1
        cell_w = w // cells
        return [
            (i * cell_w + cell_w // 4, h // 4, cell_w // 2, h // 2) for i in range(cells)
        ]


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

# 실제 모델 예시 (팀원이 구현 후 주석 해제). 무거운 import 는 팩토리 안에서 해야
# 다른 엔진을 쓸 때 불필요하게 로드되지 않는다.
#
# def _make_insightface() -> FaceEngine:
#     from .engines.insightface_engine import InsightDetector, InsightEmbedder
#     return FaceEngine("insightface", InsightDetector(), InsightEmbedder())
#
# register_engine("insightface", _make_insightface)
