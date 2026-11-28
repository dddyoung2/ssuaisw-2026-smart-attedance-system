# 얼굴 엔진 연결 가이드

얼굴 검출·인식 모델이 백엔드에 연결되는 구조와 규칙입니다.
**검출은 RetinaFace(ResNet-50), 인식(FR)은 AdaFace(IR101, 파인튜닝 가중치)로 연결되어 있습니다**(`src/backend/engines/`). 기본 엔진 `retinaface`가 두 모델을 함께 씁니다.

백엔드의 다른 부분(DB, API, 매칭, 출석 저장)은 수정할 필요가 없습니다. 인식 모델을 바꿀 때는 `FaceEmbedder` 하나만 구현해 `face_engine.py`에 등록하면 됩니다.

---

## 1. 구조와 역할

```
백엔드 서비스 ── 사진(RGB numpy) ──▶ face_engine.FaceEngine ── [(박스, 임베딩), ...] ──▶ 백엔드 서비스
                                      │
                                      ├─ engines/fd_pipeline.py  detect_and_align()
                                      │     ① engines/detector.py  검출 (박스 + 5점)
                                      │     ② engines/align.py     정렬·크롭 (CelebA-HQ 방식, 리사이즈 없음)
                                      │
                                      └─ ③ engines/embedder.py   임베딩 (AdaFace, Bicubic 112 리사이즈는 여기서)
```

| 파일 | 역할 |
|---|---|
| `engines/detector.py` | `RetinaFaceDetector`: 사진 → 박스, 5점 |
| `engines/align.py` | `align_face`: 5점 → 정사각형 얼굴 / `to_xywh`: 박스 → `(x, y, w, h)` |
| `engines/fd_pipeline.py` | `detect_and_align`: 검출 → 정렬을 이어 인식에 넘길 `(boxes, images)` 생성 / `detect_boxes`: 검출만(카메라 미리보기용) / `get_detector`: 검출기를 한 번만 로드 |
| `engines/embedder.py` | `AdaFaceEmbedder`: 정렬 얼굴 → 512차원 임베딩(`embed`, 여러 얼굴 한 번에 `embed_batch`, 학생 등록용 여러 크기 평균 `embed_anchor`) / `to_input`·`anchor_views`: 전처리 / `get_recognizer`: 인식 모델을 한 번만 로드 |
| `engines/adaface/` | AdaFace 백본(`net.py`, 공식 코드 그대로)과 가중치 로더(`model.py`), `weight/` 가중치 위치 |
| `face_engine.py` | `FaceEngine`: fd_pipeline 결과를 임베더에 넘기고 임베딩 형식 검사(출석 사진 `detect_and_embed`, 학생 증명사진 `detect_and_embed_anchor`), 검출만(`detect`, 미리보기) / 엔진 등록·선택(`FACE_ENGINE`) |

- 얼굴 엔진은 **DB를 읽지 않습니다.** 사진을 받아 얼굴 임베딩 목록을 돌려주는 일만 합니다.
- 수강생 임베딩 조회, 1:1 매칭, 출석 저장은 백엔드(`services/`)가 맡습니다.
- 학생 증명사진 임베딩도 같은 엔진으로 계산합니다(`scripts/compute_embeddings.py`, `detect_and_embed_anchor`). 그래야 같은 공간의 벡터끼리 비교됩니다.

## 2. 검출 출력 (engines/detector.py)

`RetinaFaceDetector.detect(photo_rgb)` → `(dets, landms)`

| 출력 | 형식 |
|---|---|
| `dets` | `(N, 5)` float32 `[x1, y1, x2, y2, score]`, 원본 픽셀 좌표, 신뢰도 높은 순 |
| `landms` | `(N, 5, 2)` float32 `[x, y]` 5점, 원본 픽셀 좌표 |

- 입력은 **원본 크기 RGB** `(H, W, 3)` uint8입니다. BGR 변환과 평균값 빼기는 검출기 안에서 합니다.
- 5점 순서: 왼눈 → 오른눈 → 코 → 왼입꼬리 → 오른입꼬리 ("왼쪽"은 이미지에서 보이는 왼쪽)
- 신뢰도 기준 `0.90`, NMS `0.4`이고, 얼굴이 없으면 `(0, 5)`, `(0, 5, 2)` 배열을 돌려줍니다.
- 다른 검출기(테스트용 `DummyDetector` 등)도 이 형식을 그대로 따라야 합니다.

## 3. 정렬 출력 (engines/align.py)

`align_face(photo_rgb, landmarks)` → `(S, S, 3)` uint8 RGB

- CelebA-HQ(ProGAN 공개 코드) 방식으로 중심·방향을 잡은 **정사각형**입니다.
- 한 변 `S = round(max(눈 사이 × 4, 눈–입 × 3.6))`. **회전과 이동만 하고 배율은 1**입니다(리사이즈 없음).
- 사진 밖으로 나간 부분은 검은색으로 채웁니다.

`fd_pipeline.detect_and_align(photo_rgb)` → `(boxes, images)`

- `boxes`: `[(x, y, w, h), ...]` 원본 픽셀 정수, 사진 범위 안으로 자름
- `images`: `[img, ...]` 위 정렬 결과
- 같은 인덱스 = 같은 얼굴, 신뢰도 높은 순. 얼굴이 없으면 `([], [])`

## 4. 인식 모델 인터페이스 (face_engine.py)

```python
class FaceEmbedder(ABC):
    dim: int                                        # 임베딩 차원 (클래스 속성)
    def embed(self, face_image: np.ndarray) -> np.ndarray: ...
```

- `embed(face_image)`에는 3번의 **정렬 이미지 `(S, S, 3)` RGB가 리사이즈 없이** 들어옵니다.
- **모델 입력 크기로 리사이즈, 색 순서 변환(BGR 등), 정규화는 임베더 안에서** 합니다.
- 반환: shape `(dim,)` 1차원, dtype `float32`, **L2 정규화** (`vec / np.linalg.norm(vec)`)
- `FaceEngine`이 차원·NaN 검사와 재정규화를 한 번 더 합니다. `dim`과 실제 길이가 다르면 오류가 납니다.

## 5. 엔진 등록과 선택

`face_engine.py` 맨 아래에 엔진이 등록되어 있고, `.env`의 `FACE_ENGINE`으로 고릅니다.

| 이름 | 검출 | 인식 | 용도 |
|---|---|---|---|
| `retinaface` (기본값) | RetinaFace | AdaFace (512차원) | 실제 서버 |
| `dummy` | 더미 | 더미 (128차원) | 가중치 없이 테스트·CI |

```python
def _make_retinaface() -> FaceEngine:
    from .engines.embedder import AdaFaceEmbedder
    return FaceEngine("retinaface", None, AdaFaceEmbedder())

register_engine("retinaface", _make_retinaface)
```

- 검출기 자리에 `None`을 넘기면 `fd_pipeline.get_detector()`의 RetinaFace를 씁니다. 처음 사진을 처리할 때 **한 번만** 불러옵니다. 등록 코드에서 `RetinaFaceDetector()`를 따로 만들지 마세요(모델이 두 번 올라갑니다).
- AdaFace도 같은 방식으로, 처음 임베딩할 때 `embedder.get_recognizer()`가 **한 번만** 불러옵니다. 그래서 가중치가 없어도 서버는 켜지고, 사진을 처리할 때 오류가 납니다.
- `retinaface` 엔진은 가중치 파일 2개가 있어야 동작합니다. 받는 방법은 루트 README의 "가중치 다운로드"를 따릅니다.
  - `src/backend/engines/retinaface/weight/Resnet50_Final.pth`
  - `src/backend/engines/adaface/weight/adaface_weight.pt`

## 6. AdaFace 인식 (engines/embedder.py)

| 항목 | 값 |
|---|---|
| 모델 | AdaFace IR101, WebFace12M 사전학습 가중치를 CelebAMask-HQ로 파인튜닝 (`adaface_weight.pt`) |
| 가중치 형식 | PyTorch checkpoint. `model_state_dict`만 꺼내 씀 (`torch.load(weights_only=True)`) |
| 입력 | 정렬 얼굴 RGB 크롭 **전체를 Bicubic으로 112×112** (`to_input`, 정사각형이 아니면 가로·세로를 각각 맞춤) |
| 출석 사진 얼굴 | 한 사진의 얼굴들을 32개씩 묶어 한 번에 임베딩 (`embed_batch`) |
| 학생 증명사진 | **여러 크기 평균** (`embed_anchor`): 크롭 원본 1장 + 16·24·32·48·64·96·128·256·512 중 크롭의 min(가로, 세로) 이하 크기로 AREA 축소한 뷰 → 각각 Bicubic 112 → 임베딩 평균 → L2 정규화 |
| 색 순서 | **RGB 그대로** (BGR 변환 없음) |
| 정규화 | `pixel / 127.5 - 1` (로더 `encode_rgb` 안에서 함) |
| 출력 | 512차원, L2 정규화 (모델 출력 길이가 1이 아니면 오류) |
| 가중치 읽기 | checkpoint의 `model_state_dict`만 읽음 (`weights_only=True`, pickle 안 코드는 실행하지 않음) |

- 전처리는 FR 쪽 실사용 코드(FR_draft `fr_draft/attendance.py`의 `model_input`, `anchor_views`)와 같습니다. FR이 임계값 0.109를 정할 때 쓴 전처리와 맞추기 위함입니다.
- 크롭은 ArcFace 5점 정렬이 아니라 CelebA-HQ 방식(머리카락까지 들어가는 넉넉한 크롭, FR 요청)을 그대로 112로 맞춥니다.
- CPU에서 얼굴 1개당 약 0.1초, 가중치 첫 로드는 수 초 걸립니다. 학생 1명 등록은 뷰 수(최대 10개)만큼 임베딩합니다. 로더가 PyTorch CPU 스레드를 4개로 정합니다.

### 다른 인식 모델로 바꿀 때

1. `engines/`에 `FaceEmbedder`를 구현한 클래스를 추가합니다. 리사이즈, 색 순서, 정규화는 그 모델의 공식 코드를 따라 임베더 안에서 합니다.
2. `face_engine.py`의 `_make_retinaface`에서 임베더를 바꾸거나, 새 이름으로 등록합니다. 검출기 자리는 `None` 그대로 둡니다.
3. 패키지는 기존 고정 버전(`torch==2.12.0`, `torchvision==0.27.0`, `opencv-python==4.11.0.86`, `numpy==1.26.4`)과 맞춥니다. 가중치 파일(`*.pt`, `*.pth`, `*.onnx`, `*.safetensors`)은 `.gitignore`로 제외되어 있으니 git에 올리지 말고, 받는 방법을 README에 적습니다.
4. `.env`의 `FACE_ENGINE`과 `THRESHOLD`를 바꿉니다. 임계값은 모델마다 적정값이 다르니 실제 사진으로 정합니다(8번).
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
- 지금 기본값 `0.109`는 AdaFace 파인튜닝 가중치의 학습 설정값입니다(VGGFace2 기준 공개 참고값과 같음). 실제 강의실 사진과 증명사진으로 같은 사람/다른 사람 유사도 분포를 확인해야 합니다.

## 9. 더미 엔진 (테스트·CI용, 유지)

| 입력 | DummyDetector 결과 (RetinaFaceDetector와 같은 `(dets, landms)` 형식) |
|---|---|
| 거의 단색 이미지 | 얼굴 0개 |
| 가로가 세로의 2배 이상 | 세로 길이의 정사각형 칸마다 가운데 절반을 박스로 봄 |
| 그 외 | 이미지 가운데 절반을 박스 1개로 봄 |

5점은 박스 안의 고정 비율 위치이고, 정렬은 실제와 같이 `engines/align.py`가 합니다.
DummyEmbedder는 흑백 변환 → 16×8 축소 → 평균 제거 → L2 정규화로 128차원 벡터를 만듭니다. 같은 이미지는 유사도 1.0이 나오지만, 실제 얼굴은 인식하지 못합니다.

## 10. 확인 방법

```powershell
python -m pytest tests/test_face_engine.py tests/test_align.py tests/test_detector.py tests/test_embedder.py    # 저장소 루트에서
```

| 테스트 | 확인하는 것 |
|---|---|
| `test_face_engine.py` | 엔진 등록·선택(서버 시작 때 모델을 불러오지 않는지), 임베딩 검사, 더미 엔진, 1:1 매칭 |
| `test_align.py` | 정렬 결과의 크기·방향·배율 |
| `test_detector.py` | 검출·인계 출력 규격. 실제 RetinaFace 테스트는 가중치와 `engines/retinaface/test/input-img/` 사진이 있을 때만 실행 |
| `test_embedder.py` | Bicubic 112 변환, 여러 크기 뷰 규칙·평균, 얼굴 묶음 임베딩, 임베더 연결 규격. 실제 AdaFace 테스트는 가중치가 있을 때만 실행 |
| `test_preview.py` | 카메라 미리보기 `POST /preview`: 검출만, 큰 프레임 축소 후 좌표 복원, 출석·파일 변화 없음 |

같은 사람/다른 사람 사진으로 THRESHOLD를 확인하는 테스트는 얼굴 사진이 필요해 저장소에 넣지 않습니다(개인정보). 로컬에서 따로 확인합니다.
