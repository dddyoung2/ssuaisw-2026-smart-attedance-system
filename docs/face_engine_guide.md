# 얼굴 엔진 연결 가이드

실제 얼굴 검출·인식 모델을 백엔드에 연결하는 방법입니다.
**검출은 RetinaFace로 확정**됐고, **인식(FR)은 AdaFace가 후보**입니다(README 기준). 두 모델은 추후에 함께 연결할 예정이며, 현재 백엔드는 더미 엔진으로 동작합니다.

백엔드의 다른 부분(DB, API, 매칭, 출석 저장)은 수정할 필요가 없습니다. `src/backend/face_engine.py`의 인터페이스 두 개만 구현하면 됩니다.

---

## 1. 얼굴 엔진의 역할

```
백엔드 서비스 ── 사진(RGB numpy) ──▶ 얼굴 엔진 ── [(검출 결과, 임베딩), ...] ──▶ 백엔드 서비스
                                     ① 검출 (박스 + 5점 랜드마크)
                                     ② 정렬·크롭 (112x112)
                                     ③ 임베딩 추출
```

- 얼굴 엔진은 **DB를 읽지 않습니다.** 사진을 받아 얼굴 임베딩 목록을 돌려주는 일만 합니다.
- 수강생 임베딩 조회, 1:1 매칭, 출석 저장은 백엔드(`services/`)가 맡습니다.
- 학생 증명사진 임베딩도 같은 엔진으로 계산합니다(`scripts/compute_embeddings.py`). 그래야 같은 공간의 벡터끼리 비교됩니다.

## 2. 인터페이스

```python
@dataclass(frozen=True)
class FaceDetection:
    bbox: tuple[int, int, int, int]                 # (x, y, w, h)
    landmarks: tuple[tuple[float, float], ...] | None = None   # 5점 또는 None
    score: float | None = None                      # 검출 신뢰도 (선택)

class FaceDetector(ABC):
    def detect(self, image: np.ndarray) -> Sequence[FaceDetection | tuple[int, int, int, int]]: ...

class FaceEmbedder(ABC):
    dim: int                                        # 임베딩 차원 (클래스 속성)
    def embed(self, face_image: np.ndarray) -> np.ndarray: ...
```

`FaceEngine(name, detector, embedder)`가 둘을 묶습니다. 아래 처리는 엔진이 대신 해 주므로 구현에서 신경 쓰지 않아도 됩니다.
- bbox를 정수로 바꾸고 이미지 범위로 자르기
- 랜드마크 형식 검사
- **랜드마크가 있으면 정렬, 없으면 bbox로 크롭**
- 임베딩 차원·NaN 검사와 재정규화

## 3. 입력 규칙

| 항목 | 규칙 |
|---|---|
| 타입 | `numpy.ndarray`, shape `(H, W, 3)`, dtype `uint8` |
| 색 순서 | **RGB** ⚠️ RetinaFace·AdaFace 공식 코드는 대부분 **BGR**(OpenCV)을 기대하므로, 구현 안에서 `image[:, :, ::-1]`로 바꿔 주세요 |
| 방향 | EXIF 회전이 이미 반영된 상태 |
| 크기 | 원본 크기 그대로 들어옵니다(웹캠 640×480 JPEG, 증명사진은 제각각). 모델에 필요한 리사이즈·정규화는 구현 안에서 처리합니다 |

- `detect(image)`에는 전체 사진이 들어옵니다.
- `embed(face_image)`에는 엔진이 **정렬·크롭한 얼굴**이 들어옵니다(RGB uint8). 랜드마크가 있으면 항상 **112×112**입니다.

## 4. 출력 규칙

### `detect` → `FaceDetection` 목록
- `bbox`: 원본 이미지 기준 `(x, y, w, h)` 픽셀. `(x1, y1, x2, y2)` 형식이면 `(x1, y1, x2 - x1, y2 - y1)`로 바꿔 주세요.
- `landmarks`(선택): 원본 이미지 기준 `(x, y)` **5점**. 순서는 다음과 같아야 합니다.
  1. 왼쪽 눈 → 2. 오른쪽 눈 → 3. 코 → 4. 입 왼쪽 끝 → 5. 입 오른쪽 끝
  ("왼쪽"은 **이미지에서 보이는** 왼쪽입니다. RetinaFace 5점 출력과 같은 순서입니다.)
- 얼굴이 없으면 빈 리스트를 돌려줍니다. 신뢰도가 낮은 검출은 구현 안에서 걸러 주세요.
- 박스만 있는 검출기는 `(x, y, w, h)` 튜플만 돌려줘도 됩니다. 이때는 bbox 크롭을 씁니다.

### `embed` → `np.ndarray`
- shape `(dim,)` 1차원, dtype `float32`, **L2 정규화** 필수 (`vec / np.linalg.norm(vec)`)
- `dim`과 실제 길이가 다르면 오류가 납니다.

## 5. 정렬 방식 (랜드마크가 있을 때)

`face_engine.align_face()`가 5점 랜드마크를 **ArcFace 표준 5점 위치**(112×112 기준)에 맞추는 유사 변환(회전 + 균일 스케일 + 이동)을 구해 112×112로 잘라냅니다.

```
ARCFACE_TEMPLATE = [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
                    [41.5493, 92.3655], [70.7299, 92.2041]]
```

AdaFace·ArcFace 계열은 이 정렬 기준으로 학습되어 있으므로, 임베더에서 따로 정렬할 필요가 없습니다. numpy와 Pillow만으로 구현되어 있어서 OpenCV 없이 동작합니다.

## 6. RetinaFace + AdaFace 연결 예시 (추후 작업)

1. `src/backend/engines/` 폴더와 `__init__.py`를 만들고 구현 파일을 추가합니다.

```python
# src/backend/engines/retinaface_detector.py
import numpy as np
from backend.face_engine import FaceDetection, FaceDetector

class RetinaFaceDetector(FaceDetector):
    def __init__(self, score_threshold: float = 0.8):
        from retinaface import RetinaFace         # 무거운 import 는 여기서 (사용하는 패키지에 맞게)
        self.model = RetinaFace
        self.score_threshold = score_threshold

    def detect(self, image):
        bgr = image[:, :, ::-1]                    # RGB → BGR
        faces = ...                                # 모델 추론: 박스, 점수, 5점 랜드마크
        out = []
        for (x1, y1, x2, y2), score, lm5 in faces:
            if score < self.score_threshold:
                continue
            out.append(FaceDetection(
                bbox=(int(x1), int(y1), int(x2 - x1), int(y2 - y1)),
                landmarks=tuple((float(x), float(y)) for x, y in lm5),   # 왼눈, 오른눈, 코, 입왼, 입오
                score=float(score),
            ))
        return out
```

```python
# src/backend/engines/adaface_embedder.py
import numpy as np
from backend.face_engine import FaceEmbedder

class AdaFaceEmbedder(FaceEmbedder):
    dim = 512

    def __init__(self, weight_path: str):
        import torch                               # 무거운 import 는 여기서
        self.model = ...                           # 가중치 로드, eval()

    def embed(self, face_image):                   # 112x112 RGB (엔진이 정렬해서 넘김)
        bgr = face_image[:, :, ::-1].astype(np.float32)
        x = (bgr / 255.0 - 0.5) / 0.5              # AdaFace 입력 정규화 (공식 코드 확인)
        vec = ...                                  # 모델 추론 → (512,)
        vec = np.asarray(vec, dtype=np.float32).reshape(-1)
        return vec / np.linalg.norm(vec)
```

2. `src/backend/face_engine.py` 맨 아래의 주석을 풀어 등록합니다.

```python
def _make_retinaface_adaface() -> FaceEngine:
    from .engines.retinaface_detector import RetinaFaceDetector
    from .engines.adaface_embedder import AdaFaceEmbedder
    return FaceEngine("retinaface_adaface", RetinaFaceDetector(), AdaFaceEmbedder("<가중치 경로>"))

register_engine("retinaface_adaface", _make_retinaface_adaface)
```

3. 필요한 패키지를 `requirements.txt`에 추가합니다. 탐지 실험 환경과 맞추려면 `numpy==1.26.4`를 쓰는데, 백엔드는 `numpy>=1.24`라서 충돌하지 않습니다. 가중치 파일(`*.pt`, `*.onnx`)은 `.gitignore`로 제외되어 있으니 git에 올리지 말고, 받는 방법을 README에 적어 주세요.
4. `.env`를 수정합니다.

```
FACE_ENGINE=retinaface_adaface
THRESHOLD=0.3        # 모델마다 적정값이 다름. 실제 사진으로 조정
```

5. 서버를 재시작하고 `GET /health`에서 `face_engine`과 `embedding_dim`이 바뀌었는지 확인합니다.
6. **학생 임베딩을 다시 계산합니다** (7번).

## 7. ⚠️ FR 모델을 바꾸면 학생 임베딩 재계산 필수

모델이 다르면 같은 사람이라도 임베딩이 전혀 다릅니다.
- 차원이 **다르면** 서버가 그 학생들을 비교에서 빼고 경고 로그(개수만)를 남깁니다. 그래서 아무도 매칭되지 않습니다.
- 차원이 **같으면** 경고 없이 엉뚱한 결과가 나옵니다. 더 위험한 경우입니다.

엔진을 바꾼 뒤에는 서버를 끄고 반드시 실행하세요.

```powershell
cd src
python -m backend.scripts.compute_embeddings --dry-run   # 결과만 확인
python -m backend.scripts.compute_embeddings             # 실제 저장
```

증명사진에서 얼굴이 정확히 1개가 아니면 그 학생의 임베딩을 NULL로 바꾸고 목록을 출력합니다(매칭에서 제외되므로 증명사진을 확인해야 함).

## 8. 임계값(THRESHOLD)과 1:1 매칭

- 매칭 조건은 `코사인 유사도 > THRESHOLD`입니다.
- 한 사진 안에서 얼굴 하나는 수강생 한 명에게만, 수강생 한 명은 얼굴 하나에만 배정됩니다. 유사도가 높은 쌍부터 배정합니다.
- 실제 모델이 정해지면 같은 사람/다른 사람 쌍으로 유사도 분포를 확인해 값을 정하세요.

## 9. 더미 엔진 (테스트·데모용, 유지)

| 입력 | DummyDetector 결과 (랜드마크 없음 → bbox 크롭) |
|---|---|
| 거의 단색 이미지 | 얼굴 0개 |
| 가로가 세로의 2배 이상 | 세로 길이의 정사각형 칸마다 가운데 절반을 얼굴로 봄 |
| 그 외 | 이미지 가운데 절반을 얼굴 1개로 봄 |

DummyEmbedder는 흑백 변환 → 16×8 축소 → 평균 제거 → L2 정규화로 128차원 벡터를 만듭니다. 같은 이미지는 유사도 1.0이 나오지만, 실제 얼굴은 인식하지 못합니다.

## 10. 확인 방법

```powershell
python -m pytest tests/test_face_engine.py    # 저장소 루트에서. 인터페이스·정렬·매칭 규칙 테스트
```

새 엔진용 테스트도 `tests/`에 추가하는 것을 권장합니다. 확인할 것은 세 가지입니다.
- 같은 사람 사진 두 장의 유사도가 THRESHOLD보다 큰지
- 다른 사람 사진의 유사도가 THRESHOLD보다 작은지
- 랜드마크 순서가 맞는지 (정렬된 112×112 이미지를 저장해 눈으로 확인)
