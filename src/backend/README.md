# Backend

강의실 사진에서 얼굴을 인식해 출석을 자동으로 기록하는 **데모 백엔드**입니다.
FastAPI, SQLite(SQLAlchemy 2.0)를 사용하고, 얼굴 모델은 교체할 수 있는 구조입니다(현재는 더미 엔진).

> ⚠️ **운영 전 인증 추가 필요**
> 데모용이라 로그인/인증이 없습니다. 서버에 접속할 수 있는 사람은 누구나 학생 사진을 보고 지울 수 있습니다.
> 실제로 운영하기 전에 인증, HTTPS, 개인정보 처리 동의 절차를 반드시 추가하세요.

## 설치와 실행 (Windows PowerShell, 저장소 루트에서)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env

python main.py            # 서버 실행
python main.py --reload   # 개발용: 코드 수정 시 자동 재시작
pytest                    # 테스트
```

| 주소 | 내용 |
|---|---|
| http://127.0.0.1:8000/app/ | 출결 화면 (`src/frontend`를 백엔드가 직접 서빙) |
| http://127.0.0.1:8000/docs | API 문서 (Swagger UI, 학생 등록도 여기서) |
| http://127.0.0.1:8000/health | 서버 상태와 현재 얼굴 엔진 |

Python 3.10 이상이 필요합니다. Python 3.11(pip 24.0, numpy 1.26.4)과 Python 3.14(numpy 2.x)에서 설치와 테스트를 확인했습니다.

처음 실행하면 `src/backend/data/`(DB 파일, 사진)가 자동으로 만들어집니다. 이 폴더는 `.gitignore`에 포함되어 있습니다.

**Live Server로 프론트엔드를 열 때**: 백엔드가 `src/backend/data`에 파일을 쓸 때마다 페이지가 새로고침되어 촬영이 끊깁니다. `/app/` 주소로 열거나, VS Code 설정 `liveServer.settings.ignoreFiles`에 `"**/src/backend/data/**"`를 추가하세요.

## 폴더 구조

```
main.py                  저장소 루트의 실행 스크립트 (python main.py)
src/backend/
├─ main.py               FastAPI 앱 (backend.main:app)
├─ factory.py            앱 조립: DB, 얼굴 엔진, CORS, 라우터, /app 정적 서빙
├─ config.py             환경설정 (.env)
├─ database.py           DB 엔진/세션
├─ models.py             ORM 테이블
├─ schemas.py            요청/응답 형식
├─ face_engine.py        얼굴 검출/임베딩 인터페이스 + 더미 구현
├─ deps.py               공통 의존성
├─ routers/              students, sessions, photos, detections
├─ services/             storage(파일), recognition(매칭), attendance(출석 계산), views
├─ scripts/              recompute_embeddings.py (모델 교체 시 임베딩 재계산)
└─ data/                 (자동 생성, git 제외)
tests/                   pytest (더미 엔진 기반)
docs/face_engine_guide.md 얼굴 모델 연결 가이드
```

## 환경 변수 (.env)

| 이름 | 기본값 | 설명 |
|---|---|---|
| `DB_URL` (또는 `DATABASE_URL`) | 비움 → SQLite | 예: `postgresql+psycopg://user:pw@localhost:5432/attendance` |
| `DATA_DIR` | `src/backend/data` | DB와 사진 저장 폴더 (상대경로는 저장소 루트 기준) |
| `CORS_ORIGINS` | `http://127.0.0.1:5500,http://localhost:5500` | 쉼표로 구분 |
| `FACE_ENGINE` | `dummy` | 얼굴 엔진 이름 |
| `THRESHOLD` | `0.5` | 코사인 유사도가 이 값보다 커야 매칭 |
| `USE_VERIFIED_FACES` | `false` | 이전 수업에서 교수가 확인한 얼굴도 비교 대상에 포함 |
| `MAX_UPLOAD_MB` | `5` | 업로드 최대 크기 |

## 출석 판정 방식

1. 사진이 올라오면 얼굴을 검출하고 각 얼굴의 임베딩을 계산합니다.
2. 등록된 학생 임베딩과 코사인 유사도를 비교해, 얼굴마다 가장 유사한 학생을 고릅니다. 유사도가 `THRESHOLD`보다 크면 매칭합니다.
3. 출석은 그 수업의 모든 검출 결과로 **매번 다시 계산**합니다. 한 장이라도 매칭된 학생은 present, 나머지 등록 학생은 absent입니다.
4. 교수가 직접 바꾼 출석(`source=manual`)은 다시 계산해도 유지됩니다. `{"status":"auto"}`를 보내면 자동 판정으로 돌아갑니다.

## DB 테이블

| 테이블 | 주요 컬럼 |
|---|---|
| students | student_id(PK), name, photo_path, embedding(BLOB, NULL 허용), created_at |
| sessions | session_id(PK), course_name, room, started_at |
| session_photos | photo_id(PK), session_id(FK), photo_path, captured_at |
| detections | detection_id(PK), photo_id(FK), bbox_x/y/w/h, embedding(BLOB), matched_student_id(FK, NULL 허용), similarity, verified |
| attendance | (session_id, student_id) PK, status(present/absent), source(auto/manual), updated_at |

- 사진은 파일로 저장하고 DB에는 상대경로만 저장합니다. 임베딩은 float32 배열을 바이트로 바꾼 BLOB입니다.
- 삭제 규칙: 수업 → 사진 → 검출은 CASCADE, 학생 삭제 시 검출의 매칭은 SET NULL, 출석 기록은 CASCADE

## API

| Method | 경로 | 설명 |
|---|---|---|
| POST | `/students` | 학생 등록 (multipart: `student_id`, `name`, `photo`). 얼굴 0개 또는 2개 이상이면 400 |
| GET | `/students` | 학생 목록 (임베딩 제외) |
| GET | `/students/{student_id}/photo` | 증명사진 |
| DELETE | `/students/{student_id}` | 학생 삭제 (사진 파일 포함) |
| POST | `/sessions` | 수업 회차 생성 `{course_name?, room}` |
| GET | `/sessions`, `/sessions/{id}` | 수업 회차 목록 / 조회 |
| POST | `/sessions/{id}/photos` | 강의실 사진 업로드 → 검출 → 인식 → 출석 반영 |
| GET | `/sessions/{id}/photos` | 사진 목록 |
| DELETE | `/sessions/{id}/photos` | 사진 모두 삭제 + 출석 재계산 |
| GET | `/photos/{photo_id}/image` | 강의실 사진 |
| GET | `/sessions/{id}/attendance` | 출석 결과 (학번, 이름, 상태, 최고 유사도) |
| PATCH | `/sessions/{id}/attendance/{student_id}` | 출석 수동 수정 `{status: present\|absent\|auto}` |
| GET | `/sessions/{id}/detections` | 검출된 얼굴 목록 (교수 확인용) |
| PATCH | `/detections/{id}` | 매칭 수정 `{matched_student_id: "학번"\|null}` → verified=true |
| GET | `/detections/{id}/face` | 검출된 얼굴 부분 이미지 |

업로드는 jpg, jpeg, png만 허용합니다(415). 크기를 넘으면 413을 반환합니다.

## 얼굴 모델 교체

[docs/face_engine_guide.md](../../docs/face_engine_guide.md)를 참고하세요. 모델을 바꾼 뒤에는 기존 임베딩을 반드시 다시 계산해야 합니다.

```powershell
cd src
python -m backend.scripts.recompute_embeddings
```

## 사진 보관 정책과 README 명세와 다른 점

- **촬영 사진은 보관합니다** (README의 "사진 즉시 삭제"와 다름). 판정 후에도 원본 파일과 DB 기록(`session_photos`, `detections`)을 남겨,
  교수 확인용 얼굴 이미지와 모델 교체 시 임베딩 재계산에 사용합니다. 출결 화면의 "사진 모두 지우기"(`DELETE /sessions/{id}/photos`)로만 삭제됩니다.
- **사진과 DB는 각자 PC에만 저장됩니다.** `src/backend/data/`는 git에서 제외되므로, 저장소를 받은 팀원은 빈 DB로 시작하고 학생도 각자 등록해야 합니다.
- **"확인 필요" 상태**: 지금은 present/absent 두 가지이고, 인식되지 않은 얼굴은 `GET /sessions/{id}/detections`에서 `matched_student_id: null`로 확인합니다.
- **수강 명단 제한 없음** (README의 "수강 명단에 한정해 매칭"과 다름): 강의와 학생을 잇는 테이블이 없어서, 모든 수업에서 **등록된 학생 전체**를 상대로 매칭하고 출석을 계산합니다.
  데모 단계에서는 이대로 두고, 이후 `courses`·`enrollments` 테이블을 추가해 매칭 대상과 출석 대상을 수강생으로 제한할 예정입니다.
