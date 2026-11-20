"""얼굴 검출/임베딩 연결부.

얼굴 엔진은 "사진을 받아 얼굴 임베딩 목록을 돌려주는" 역할만 한다.
DB 조회·비교·저장은 백엔드 서비스(services/)가 한다. 규칙은 docs/face_engine_guide.md 참고.

  입력 이미지 : numpy.ndarray, shape (H, W, 3), dtype uint8, **RGB** 순서
  detect()    : [FaceDetection(bbox=(x, y, w, h), landmarks=5점 또는 None), ...]
                (편의상 (x, y, w, h) 튜플만 돌려줘도 된다)
  정렬·크롭   : 랜드마크가 있으면 ArcFace 표준 5점에 맞춰 112x112 로 정렬, 없으면 bbox 로 자름
  embed()     : shape (D,) float32, L2 정규화된 벡터

새 구현은 register_engine("이름", 팩토리)로 등록하고 환경변수 FACE_ENGINE=이름 으로 고른다.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

BBox = tuple[int, int, int, int]  # (x, y, w, h)
Point = tuple[float, float]  # (x, y), 원본 이미지 픽셀 좌표

#: 정렬 후 얼굴 이미지 크기 (ArcFace/AdaFace 계열 표준)
ALIGN_SIZE = 112

#: ArcFace 표준 5점 위치 (112x112 기준). 순서: 왼쪽 눈, 오른쪽 눈, 코, 입 왼쪽 끝, 입 오른쪽 끝
#: (왼쪽/오른쪽은 "이미지에서 보이는" 방향. RetinaFace 의 5점 출력 순서와 같다)
ARCFACE_TEMPLATE = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float64,
)


@dataclass(frozen=True)
class FaceDetection:
    """검출된 얼굴 하나.

    bbox      : (x, y, w, h) 정수 픽셀, 좌상단 기준
    landmarks : 5점 [(x, y) × 5] 또는 None. 순서는 ARCFACE_TEMPLATE 과 같다.
    score     : 검출 신뢰도 (선택, 참고용)
    """

    bbox: BBox
    landmarks: tuple[Point, ...] | None = None
    score: float | None = None


# ---------------------------------------------------------------------------
# 인터페이스
# ---------------------------------------------------------------------------
class FaceDetector(ABC):
    @abstractmethod
    def detect(self, image: np.ndarray) -> Sequence[FaceDetection | BBox]:
        """RGB uint8 (H, W, 3) 이미지 → 검출된 얼굴 목록."""


class FaceEmbedder(ABC):
    #: 임베딩 차원. 바뀌면 학생 임베딩을 다시 계산해야 한다(scripts/compute_embeddings.py).
    dim: int

    @abstractmethod
    def embed(self, face_image: np.ndarray) -> np.ndarray:
        """정렬·크롭된 얼굴 RGB uint8 (h, w, 3) → L2 정규화된 (dim,) float32 벡터."""


# ---------------------------------------------------------------------------
# 정렬 (랜드마크 → 112x112)
# ---------------------------------------------------------------------------
def similarity_transform(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """src 점들을 dst 점들로 옮기는 2x3 유사 변환(회전·균일 스케일·이동). Umeyama 방법."""
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    n = src.shape[0]
    src_mean, dst_mean = src.mean(axis=0), dst.mean(axis=0)
    src_c, dst_c = src - src_mean, dst - dst_mean
    cov = dst_c.T @ src_c / n
    u, s, vt = np.linalg.svd(cov)
    d = np.ones(2)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:  # 반사(뒤집힘) 방지
        d[-1] = -1
    rot = u @ np.diag(d) @ vt
    var_src = (src_c**2).sum() / n
    if var_src < 1e-12:
        raise ValueError("랜드마크가 한 점에 몰려 있어 정렬할 수 없습니다.")
    scale = float((s * d).sum() / var_src)
    t = dst_mean - scale * rot @ src_mean
    return np.hstack([scale * rot, t.reshape(2, 1)])


def align_face(image: np.ndarray, landmarks: Sequence[Point], size: int = ALIGN_SIZE) -> np.ndarray:
    """5점 랜드마크를 ArcFace 표준 위치에 맞춰 size x size 얼굴 이미지로 정렬한다."""
    dst = ARCFACE_TEMPLATE * (size / ALIGN_SIZE)
    m = similarity_transform(np.asarray(landmarks, dtype=np.float64), dst)
    # Pillow 의 AFFINE 은 "출력 좌표 → 입력 좌표" 역변환을 받는다.
    inv = np.linalg.inv(np.vstack([m, [0.0, 0.0, 1.0]]))[:2]
    out = Image.fromarray(image).transform(
        (size, size), Image.AFFINE, data=tuple(inv.reshape(-1)), resample=Image.BILINEAR
    )
    return np.asarray(out, dtype=np.uint8)


def crop(image: np.ndarray, box: BBox) -> np.ndarray:
    x, y, w, h = box
    return np.ascontiguousarray(image[y : y + h, x : x + w])


def clip_bbox(box, img_w: int, img_h: int) -> BBox | None:
    """bbox 를 정수로 바꾸고 이미지 범위 안으로 자른다. 면적이 0이면 None."""
    x, y, w, h = (int(round(float(v))) for v in box)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(img_w, x + w), min(img_h, y + h)
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


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

    def detect(self, image: np.ndarray) -> list[FaceDetection]:
        _check_image(image)
        h, w = image.shape[:2]
        faces: list[FaceDetection] = []
        for raw in self.detector.detect(image):
            det = raw if isinstance(raw, FaceDetection) else FaceDetection(bbox=tuple(raw))
            box = clip_bbox(det.bbox, w, h)
            if box is None:
                continue
            faces.append(
                FaceDetection(bbox=box, landmarks=_check_landmarks(det.landmarks), score=det.score)
            )
        return faces

    def face_image(self, image: np.ndarray, det: FaceDetection) -> np.ndarray:
        """랜드마크가 있으면 정렬 후 크롭, 없으면 bbox 크롭."""
        if det.landmarks is not None:
            return align_face(image, det.landmarks)
        return crop(image, det.bbox)

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

    def detect_and_embed(self, image: np.ndarray) -> list[tuple[FaceDetection, np.ndarray]]:
        """사진 한 장 → [(검출 결과, 임베딩), ...]. 검출 → 정렬·크롭 → 임베딩."""
        return [(det, self.embed(self.face_image(image, det))) for det in self.detect(image)]


def _check_image(image: np.ndarray) -> None:
    if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("이미지는 (H, W, 3) numpy 배열이어야 합니다.")
    if image.dtype != np.uint8:
        raise ValueError("이미지 dtype 은 uint8 이어야 합니다.")


def _check_landmarks(landmarks) -> tuple[Point, ...] | None:
    if landmarks is None:
        return None
    arr = np.asarray(landmarks, dtype=np.float64)
    if arr.shape != (5, 2) or not np.all(np.isfinite(arr)):
        raise ValueError("랜드마크는 (x, y) 5점이어야 합니다: 왼쪽 눈, 오른쪽 눈, 코, 입 왼쪽, 입 오른쪽")
    return tuple((float(x), float(y)) for x, y in arr)


# ---------------------------------------------------------------------------
# 더미 구현 (모델 연결 전 데모/테스트용)
# ---------------------------------------------------------------------------
class DummyDetector(FaceDetector):
    """규칙 기반 가짜 검출기 (랜드마크 없음 → bbox 크롭).

    - 거의 단색인 이미지(표준편차 < 2)  → 얼굴 0개
    - 가로가 세로의 2배 이상인 이미지     → 세로 길이의 정사각형 칸으로 나눠 칸마다 얼굴 1개
    - 그 외                                → 이미지 중앙에 얼굴 1개
    각 칸(또는 이미지)의 가운데 절반 영역을 얼굴 bbox 로 본다.
    """

    def detect(self, image: np.ndarray) -> list[FaceDetection]:
        h, w = image.shape[:2]
        if float(image.std()) < 2.0:
            return []
        cells = w // h if w >= 2 * h else 1
        cell_w = w // cells
        return [
            FaceDetection(bbox=(i * cell_w + cell_w // 4, h // 4, cell_w // 2, h // 2))
            for i in range(cells)
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

# 실제 모델 연결 예정 위치 (docs/face_engine_guide.md 참고)
#   검출: RetinaFace (확정, 박스 + 5점 랜드마크)   인식: AdaFace (후보)
# 무거운 import 는 팩토리 안에서 해야 dummy 를 쓸 때 모델이 로드되지 않는다.
#
# def _make_retinaface_adaface() -> FaceEngine:
#     from .engines.retinaface_detector import RetinaFaceDetector
#     from .engines.adaface_embedder import AdaFaceEmbedder
#     return FaceEngine("retinaface_adaface", RetinaFaceDetector(), AdaFaceEmbedder())
#
# register_engine("retinaface_adaface", _make_retinaface_adaface)
