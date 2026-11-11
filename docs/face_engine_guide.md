# 얼굴 엔진 연결 가이드

실제 얼굴 검출·인식 모델을 백엔드에 연결하는 방법입니다.
백엔드의 다른 부분(DB, API, 출석 판정)은 수정할 필요가 없습니다. `src/backend/face_engine.py`에서 인터페이스 두 개만 구현하면 됩니다.

---

## 1. 인터페이스

```python
class FaceDetector(ABC):
    def detect(self, image: np.ndarray) -> list[tuple[int, int, int, int]]: ...

class FaceEmbedder(ABC):
    dim: int   # 임베딩 차원 (클래스 속성)
    def embed(self, face_image: np.ndarray) -> np.ndarray: ...
```

검출기와 임베더는 `FaceEngine(name, detector, embedder)`로 묶여서 서버에 전달됩니다.
`FaceEngine`은 아래 규칙을 한 번 더 검사하고 보정합니다(bbox를 이미지 범위로 자르기, float32로 변환, 재정규화). 그래도 각 구현은 규칙을 지켜야 합니다.

## 2. 입력 규칙

| 항목 | 규칙 |
|---|---|
| 타입 | `numpy.ndarray` |
| shape | `(H, W, 3)` |
| dtype | `uint8` (0~255) |
| 색 순서 | **RGB** ⚠️ OpenCV(`cv2`) 기반 모델은 대부분 **BGR**을 기대하므로 구현 안에서 `image[:, :, ::-1]`로 바꿔 주세요 |
| 방향 | EXIF 회전이 이미 반영된 상태 |
| 크기 | **원본 크기 그대로** 들어옵니다. 프론트엔드 카메라는 640×480 JPEG이고, 증명사진은 크기가 제각각입니다. 모델에 필요한 리사이즈·패딩·정규화(mean/std)는 **구현 안에서** 처리합니다. |

- `detect(image)`에는 전체 사진이 들어옵니다.
- `embed(face_image)`에는 `detect`가 돌려준 bbox대로 **잘라낸 얼굴**이 들어옵니다(위와 같은 RGB uint8 형식).
  얼굴 정렬(landmark 기반 alignment)이 필요하면 아래 7번을 참고하세요.

## 3. 출력 규칙

### `detect` → `list[(x, y, w, h)]`
- 좌상단 `(x, y)`, 너비 `w`, 높이 `h`. 단위는 **원본 이미지 기준 픽셀**입니다.
- `(x1, y1, x2, y2)` 형식을 쓰는 모델이면 `(x1, y1, x2 - x1, y2 - y1)`로 바꿔서 돌려주세요.
- 얼굴이 없으면 빈 리스트를 돌려줍니다. 신뢰도가 낮은 검출은 구현 안에서 걸러 주세요.
- 학생 등록 API는 얼굴이 **정확히 1개**일 때만 성공합니다. 0개이거나 2개 이상이면 400 에러를 냅니다.

### `embed` → `np.ndarray`
- shape `(dim,)`인 **1차원** 배열, dtype `float32`
- **L2 정규화** 필수: `vec / np.linalg.norm(vec)`. 서버는 내적값을 코사인 유사도로 사용합니다.
- 값은 유한해야 합니다(NaN/inf 금지).
- `dim` 속성과 실제 길이가 다르면 서버가 `ValueError`를 냅니다.

## 4. 새 구현 추가 방법

1. `src/backend/engines/` 폴더를 만들고 구현 파일을 추가합니다(예: `src/backend/engines/insightface_engine.py`). `__init__.py`도 함께 만듭니다.

```python
import numpy as np
from backend.face_engine import FaceDetector, FaceEmbedder

class InsightDetector(FaceDetector):
    def __init__(self):
        from insightface.app import FaceAnalysis      # 무거운 import 는 여기서
        self.app = FaceAnalysis(name="buffalo_l")
        self.app.prepare(ctx_id=-1, det_size=(640, 640))

    def detect(self, image):
        faces = self.app.get(image[:, :, ::-1])       # RGB → BGR
        return [(int(x1), int(y1), int(x2 - x1), int(y2 - y1))
                for x1, y1, x2, y2 in (f.bbox for f in faces)]

class InsightEmbedder(FaceEmbedder):
    dim = 512
    def embed(self, face_image):
        ...  # 모델 추론
        vec = np.asarray(vec, dtype=np.float32).reshape(-1)
        return vec / np.linalg.norm(vec)
```

2. `src/backend/face_engine.py` 맨 아래에 등록합니다. import를 팩토리 함수 안에 두면 다른 엔진을 쓸 때 모델이 로드되지 않습니다.

```python
def _make_insightface() -> FaceEngine:
    from .engines.insightface_engine import InsightDetector, InsightEmbedder
    return FaceEngine("insightface", InsightDetector(), InsightEmbedder())

register_engine("insightface", _make_insightface)
```

3. 필요한 패키지를 `requirements.txt`에 추가합니다. 모델 가중치 파일(`*.pt`, `*.onnx` 등)은 git에 올리지 말고(이미 `.gitignore`에 포함) 받는 방법을 README에 적어 주세요.
4. `.env`를 수정합니다.

```
FACE_ENGINE=insightface
THRESHOLD=0.35        # 모델마다 적정값이 다름. 실제 사진으로 조정
```

5. 서버를 재시작하고 `GET /health`에서 `face_engine`, `embedding_dim` 값을 확인합니다.
6. **기존 임베딩을 재계산합니다**(아래 5번).

## 5. ⚠️ 모델을 바꾸면 임베딩 재계산 필수

모델이 다르면 같은 사람이라도 임베딩이 전혀 다릅니다. 차원이 같아도 서로 비교할 수 없습니다.
- 차원이 **다르면** 서버가 기존 임베딩을 비교에서 빼고 경고 로그를 남깁니다. 그래서 아무도 매칭되지 않습니다.
- 차원이 **같으면** 경고 없이 엉뚱한 결과가 나옵니다. 더 위험한 경우입니다.

따라서 엔진을 바꾼 뒤에는 **반드시** 아래 명령을 실행하세요(서버는 꺼 둔 상태에서).

```powershell
# venv 활성화 후 src 폴더에서 실행
cd src
python -m backend.scripts.recompute_embeddings --dry-run   # 먼저 결과만 확인
python -m backend.scripts.recompute_embeddings             # 실제 저장
```

| 대상 | 처리 |
|---|---|
| 학생 | 저장된 증명사진에서 다시 검출하고 임베딩을 계산합니다. 얼굴이 1개가 아니면 임베딩을 NULL로 바꾸고 목록을 출력합니다. 해당 학생은 증명사진을 다시 등록해야 합니다. |
| verified 검출 | 저장된 bbox로 강의실 사진을 잘라 다시 임베딩합니다(`USE_VERIFIED_FACES`가 쓰는 데이터). |
| 모든 검출 | `--all-detections` 옵션을 주면 미확인 검출도 다시 계산합니다. |

`--engine 이름` 옵션으로 `.env`와 다른 엔진을 지정할 수도 있습니다. 재계산을 하더라도 이미 기록된 출석 결과는 바뀌지 않습니다.

## 6. 임계값(THRESHOLD)

- 매칭 조건은 `코사인 유사도 > THRESHOLD`입니다. 얼굴마다 가장 유사한 학생 한 명을 고릅니다.
- 매칭에 실패해도 가장 가까운 학생과의 유사도는 `detections.similarity`에 기록됩니다. 교수 확인 화면이나 임계값 조정에 참고하세요.
- 실제 모델이 정해지면 같은 사람/다른 사람 쌍으로 유사도 분포를 확인하고 값을 정하세요.

## 7. 얼굴 정렬이 필요한 모델

ArcFace 계열처럼 5점 landmark로 정렬해야 하는 모델은 bbox로 잘라낸 이미지만으로는 정확도가 떨어집니다. 데모 단계에서는 아래 방법 중 하나를 쓰면 됩니다.
- `detect`에서 bbox를 조금 넉넉하게 잡고, `embed` 안에서 다시 검출·정렬한 뒤 임베딩합니다(가장 간단함).
- 정렬 정보까지 넘기는 인터페이스가 필요하면 백엔드 담당자와 상의해 `FaceEngine.detect_and_embed`를 확장합니다.

## 8. 더미 엔진 동작 (참고)

| 입력 | DummyDetector 결과 |
|---|---|
| 거의 단색 이미지 | 얼굴 0개 |
| 가로가 세로의 2배 이상 | 세로 길이의 정사각형 칸마다 가운데 절반을 얼굴로 봄 |
| 그 외 | 이미지 가운데 절반을 얼굴 1개로 봄 |

DummyEmbedder는 흑백 변환 → 16×8 축소 → 평균 제거 → L2 정규화를 거쳐 128차원 벡터를 만듭니다.
같은 사진을 등록하고 업로드하면 유사도가 1.0이 됩니다. 웹캠 사진은 실제 인물과 관계없이 매칭될 수 있으니 결과에 의미를 두지 마세요.

## 9. 확인 방법

```powershell
pytest tests/test_face_engine.py    # 저장소 루트에서, 인터페이스 규칙 테스트
```

새 엔진용 테스트도 `tests/`에 추가하는 것을 권장합니다. 같은 사람 사진 두 장의 유사도가 THRESHOLD보다 큰지, 다른 사람 사진의 유사도가 THRESHOLD보다 작은지 확인하면 됩니다.
