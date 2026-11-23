# Backend

강의실 단체 사진으로 **수강생 출석**을 기록하는 데모 백엔드입니다.
학생·과목·강의실·회차·수강 정보는 **usaint**(숭실대 학사 포털) DB에 이미 있다고 가정합니다. 데모에서는 SQLite 파일 `usaint.db`로 이 DB를 흉내 냅니다.
우리 시스템은 이 DB를 **읽고**, 출석 결과(`attendance`)만 **씁니다**.

> ⚠️ **운영 전 인증 추가 필요**
> 데모용이라 로그인이나 인증이 없습니다. 실제 운영 전에 인증, HTTPS, 개인정보 처리 동의 절차를 반드시 추가하세요.

## 실행 순서 (Windows PowerShell, 저장소 루트에서)

```powershell
# 1) 설치 (처음 한 번)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env            # 선택. 없으면 기본값 사용

# 2) 예시 데이터 넣기 (usaint.db 를 새로 만듦, 기존 데이터 삭제)
#    회차 중 "오늘" 회차는 실행한 날짜 기준으로 만들어지므로 데모 당일에 다시 실행하세요.
cd src
python -m backend.scripts.seed_usaint
cd ..

# 3) 서버 실행
python main.py                     # 개발 중에는 python main.py --reload

# 4) 화면 확인: http://127.0.0.1:8000/app/
#    과목 목록 → [과목 홈 바로가기] → 오늘 회차(분홍색) [출결 확인]
#    → [전자 출결] → [카메라] → 지각 인정 시간 선택 → [촬영 시작] → [출결 현황 보기]
```

| 주소 | 내용 |
|---|---|
| http://127.0.0.1:8000/app/ | 출결 화면 (`src/frontend`를 백엔드가 직접 제공, 첫 화면은 과목 목록) |
| http://127.0.0.1:8000/docs | API 문서 (Swagger UI) |
| http://127.0.0.1:8000/health | 서버 상태와 현재 얼굴 엔진 |

```powershell
python -m pytest                   # 테스트 (저장소 루트에서)
```

Python 3.10 이상이 필요합니다. Python 3.11(numpy 1.26.4)과 Python 3.14(numpy 2.x)에서 테스트를 확인했습니다.

### seed가 만드는 예시 데이터 (`DATA_DIR`, 기본 `src/backend/data/`, git 제외)

여러 번 실행해도 중복으로 쌓이지 않습니다(DB와 seed가 만든 사진을 지우고 다시 만듦).

| 항목 | 내용 |
|---|---|
| class | `2150165801` 시스템프로그래밍, `2150163303` 알고리즘, `2150061301` 오픈소스기반기초설계 |
| room | `11101`, `21303`, `21304`, `21305`. `camera`는 카메라 연결 정보 자리(추후 연동, 화면에는 표시 안 함) |
| lecture | 2026-09-01이 있는 주를 1주차로 **15주차까지**. 시스템프로그래밍은 **주 2회**(화·목, 21303), 알고리즘은 화(21304), 오픈소스기반기초설계는 수(21305) |
| 오늘 회차 | 실행한 날에 정규 회차가 없는 과목에는 **오늘 날짜 회차를 하나 추가**합니다. 그래서 모든 과목에 오늘 회차가 있습니다. 차수(`session_no`)는 같은 주 안에서 날짜순으로 다시 매깁니다(예: 11/19(목) 실행 → 알고리즘 `12-1` 11/17(화), `12-2` 11/19(목)) |
| student | 8명. 증명사진은 실제 얼굴이 아닌 **합성 패턴 이미지**(`photos/students/<학번>.png`)이고, 임베딩도 계산해서 넣음 |
| enrollment | 과목마다 4~5명 (여러 과목을 함께 듣는 학생 포함) |
| demo/ | 데모용 단체 사진 4장 (아래 참고) |

**더미 엔진에서 출석이 잡히는 걸 보려면**
예시 증명사진과 `demo/` 사진은 합성 패턴이라 기본 엔진(`retinaface`)은 얼굴을 찾지 못합니다(학생 임베딩도 만들어지지 않음). 예시 데이터로 확인할 때는 `.env`에 `FACE_ENGINE=dummy`를 지정한 뒤 seed와 서버를 실행하세요.
더미 엔진은 실제 얼굴을 인식하지 못해서 웹캠으로 찍은 사진은 아무와도 매칭되지 않습니다. 대신 `/docs`의 `POST /lectures/{id}/photos`에 `demo/` 사진을 올리면 출석이 반영됩니다. 회차 번호(`lecture_id`)는 seed 실행 결과에 출력됩니다.

| 파일 | 결과 |
|---|---|
| `algorithm_1003_1004_1005.png` | 알고리즘 회차에서 3명 출석 (수강생 4명) |
| `algorithm_non_enrolled_1001_1002.png` | 알고리즘 회차에서 0명 (수강생이 아니라 비교 대상이 아님) |
| `sysprog_1001_1002_1003.png` | 시스템프로그래밍 회차에서 3명 출석 |
| `opensource_1007_1008.png` | 오픈소스기반기초설계 회차에서 2명 출석 |

**Live Server로 열 때**: 백엔드가 `src/backend/data`의 DB에 쓸 때마다 페이지가 새로고침될 수 있습니다. `/app/` 주소로 여는 것을 권장합니다.

## 화면 흐름

| 화면 | 파일 | 화면 → 백엔드 | 다음 화면 |
|---|---|---|---|
| 1. 과목 목록 (첫 화면) | `index.html` | `GET /courses` | `course.html?course=<과목코드>` |
| 2. 과목 홈 = 회차 목록 | `course.html` | `GET /courses/{code}`, `GET /courses/{code}/lectures` | [출결 확인] → `method.html?lecture=<id>` |
| 3. 출결 방식 선택 | `method.html` | `GET /lectures/{id}` | [전자 출결] → [카메라] → `camera.html?lecture=<id>` |
| 4. 카메라 | `camera.html` | `GET /lectures/{id}`, `GET /rooms`, 카메라가 켜져 있는 동안 `POST /preview`(얼굴 박스 미리보기), 촬영 시작 시 `POST /lectures/{id}/start` → 즉시 1장 + **5분마다** + **지각 인정 시간이 지났을 때** 1장 `POST /lectures/{id}/photos` | [출결 현황 보기] → `attendance.html?lecture=<id>` |
| 5. 출결 현황 | `attendance.html` | `GET /lectures/{id}/attendance` (10초마다) | – |

- 선택한 회차는 URL 쿼리로 넘기고 localStorage에도 저장합니다. URL에 `lecture`가 없으면 마지막으로 고른 회차를 쓰고, 그것도 없으면 과목 목록으로 돌아갑니다.
- "← 뒤로"는 바로 이전 단계로 갑니다(출결 현황 → 카메라 → 출결 방식 선택 → 그 회차의 과목 홈 → 과목 목록).
- 과목 홈: 주차 칸은 `<week>-<session_no>` 배지, 수업일 칸은 `9/1 (화)`와 강의실 번호. [수업일순]/[주차순] 토글은 화면에서 정렬만 바꿉니다. 오늘 회차 행은 분홍색으로 강조하고 그 행으로 스크롤합니다.
- 카메라 촬영 시점: [촬영 시작] 즉시 1장, 이후 5분마다 1장, 그리고 **지각 인정 시간**(촬영 시작 후 1~20분, 1분 단위, 기본 10분)이 지났을 때 1장을 더 찍습니다. DB에 수업 시작 시간이 없어서 촬영 시작을 기준으로 합니다. 정기 촬영과 30초 안에 겹치면(예: 10분) 한 장만 찍습니다. 예) 7분 → 0, 5, 7, 10, 15…분 / 10분 → 0, 5, 10, 15…분. 촬영 중에는 지각 인정 시간을 바꿀 수 없고, 촬영을 멈췄다가 다시 시작하면 그때부터 다시 계산합니다.
- 카메라: 강의실 기본값은 그 회차의 강의실입니다. 다른 강의실을 골라도 DB의 회차는 바뀌지 않습니다(어느 카메라로 찍을지만 고르는 것, 강의실 카메라 연동은 추후 작업이라 지금은 브라우저 카메라로 촬영).
- 카메라 미리보기: 카메라가 켜져 있으면 프레임을 긴 변 960px로 줄여 `POST /preview`로 보내고, 탐지된 얼굴 박스를 영상 위에 그리며 "탐지된 얼굴 N개"를 표시합니다. 요청은 한 번에 하나씩(응답이 오면 다음 프레임)이라 CPU에서 약 1초마다 갱신됩니다. 출석 사진을 처리하는 동안과 탭이 안 보일 때는 멈춥니다.
  - **미리보기 박스 ≠ 출석 판정.** 미리보기는 줄인 화면에서 검출만 하므로 작은(먼) 얼굴이 빠질 수 있습니다. 출석은 원본 해상도 사진으로 검출 → 정렬 → 인식을 따로 합니다. 예) 로컬 강의실 사진 1장: 원본 44개, 긴 변 960px 36개, 640px 22개.
- 수동·큐알·코드 출결은 "준비 중" 안내만 합니다.

## 출석 처리

| 단계 | API | 백엔드 처리 |
|---|---|---|
| 회차 시작 | `POST /lectures/{id}/start` | 그 과목 수강생 전원의 ATTENDANCE 행이 없으면 `present=false`로 생성 (여러 번 호출해도 안전) |
| 사진 처리 | `POST /lectures/{id}/photos` | ENROLLMENT⋈STUDENT JOIN 한 번으로 **수강생 임베딩만** 조회 → 얼굴 엔진(검출 → 정렬·크롭 → 임베딩) → **1:1 매칭** → 매칭된 학생 `present=true`. **사진은 저장하지 않음** |
| 출결 현황 | `GET /lectures/{id}/attendance` | ATTENDANCE⋈STUDENT → 학번, 이름, 출석 여부, 요약 |

**1:1 매칭**: 모든 (얼굴, 수강생) 쌍의 코사인 유사도를 구하고, 유사도가 높은 쌍부터 "둘 다 아직 배정되지 않았으면" 배정합니다(greedy). 한 사진 안에서 얼굴 하나는 수강생 한 명에게만, 수강생 한 명은 얼굴 하나에만 배정됩니다. 유사도가 `THRESHOLD`(기본 0.5)보다 커야 인정합니다.

**OR 유지**: 한 번 `present=true`가 되면, 이후 사진에서 인식되지 않아도 true로 남습니다. false로 되돌리는 경로는 없습니다.

## DB 설계 (usaint)

```
room ─1:N─ lecture ─1:N─ attendance ─N:1─ student
              │                              │
class ─1:N────┘                              │
  └──────1:N── enrollment ──N:1──────────────┘
```

| 테이블 | 컬럼 | 키 |
|---|---|---|
| room | room_no, camera | PK room_no |
| class (`Course`) | course_code(분반 포함), course_name | PK course_code |
| student | student_id, name, photo_path, embedding(BLOB) | PK student_id |
| enrollment | course_code, student_id | PK (course_code, student_id), FK → class·student **CASCADE** |
| lecture | lecture_id(자동 증가), course_code, room_no, week, session_no, date, photo_path | PK lecture_id, FK → class **CASCADE**, FK → room |
| attendance | lecture_id, student_id, present(기본 false) | PK (lecture_id, student_id), FK → lecture·student **CASCADE** |

- 증명사진은 파일로 두고 `student.photo_path`(DATA_DIR 기준 상대경로)만 저장합니다.
- `lecture.photo_path`는 FD 모델로 학생 얼굴에 박스를 친 수업 사진의 경로 자리입니다. **컬럼만 추가했고 아직 저장하는 코드는 없어서 항상 NULL**입니다. 테이블이 바뀌었으므로 기존 `usaint.db`는 seed를 다시 실행해 새로 만들어야 합니다.
- `embedding`은 "증명사진에서 미리 추출해 넣어 둔 값"(float32 배열 → bytes)입니다. NULL인 학생은 매칭에서 제외됩니다.
- `Course.students`는 enrollment를 거쳐 수강생 목록을 바로 가져오는 조회용 relationship입니다.
- SQLite에서 FK가 동작하도록 연결할 때마다 `PRAGMA foreign_keys=ON`을 실행합니다.

## API

| Method | 경로 | 응답 |
|---|---|---|
| GET | `/courses` | `[{course_code, course_name, lecture_count}]` (과목명 순, `lecture_count` = 회차 수) |
| GET | `/courses/{course_code}` | `{course_code, course_name}` |
| GET | `/courses/{course_code}/lectures` | `[{lecture_id, week, session_no, date, room_no}]` (수업일 → 주차 → 차수 순) |
| GET | `/lectures/{lecture_id}` | `{lecture_id, course_code, course_name, week, session_no, date, room_no}` |
| POST | `/lectures/{lecture_id}/start` | `{lecture_id, student_count, created}` |
| POST | `/lectures/{lecture_id}/photos` | multipart `photo` (jpg/jpeg/png) → `{face_count, matched_count, summary:{total, present, absent}}` |
| GET | `/lectures/{lecture_id}/attendance` | `{lecture:{…}, summary:{…}, students:[{student_id, name, present}]}` |
| GET | `/rooms` | `[{room_no, camera}]` (화면은 `room_no`만 사용) |
| POST | `/preview` | multipart `photo` (jpg/jpeg/png) → `{width, height, boxes:[{x, y, w, h}]}`. 검출만(인식·출석 기록 없음, 사진 저장 안 함). 긴 변 960px 초과면 줄여서 검출하고 좌표는 보낸 이미지 기준으로 돌려줌 |
| GET | `/health` | `{status, face_engine, embedding_dim}` |

- 없는 과목·회차는 404를 반환합니다.
- 잘못된 파일: 빈 파일이거나 이미지가 아니면 400, 크기 초과(`MAX_UPLOAD_MB`)는 413, jpg/png가 아니면 415를 반환합니다.
- 어떤 응답에도 임베딩 값은 포함되지 않습니다.
- **삭제됨**: `GET /lectures?room_no=&date=` (강의실+날짜로 회차 찾기). 회차는 이제 과목 홈에서 먼저 고릅니다.

## 코드 구조

```
main.py (저장소 루트)        python main.py → uvicorn
src/backend/
├─ main.py, factory.py       앱 조립: DB, 얼굴 엔진, CORS, 라우터, /app 정적 제공
├─ config.py                 환경설정 (.env)
├─ database.py               DB 엔진·세션, SQLite FK PRAGMA
├─ models.py                 usaint 6개 테이블
├─ schemas.py                응답 형식
├─ face_engine.py            얼굴 엔진 등록·선택, 검출 결과(fd_pipeline) → 인식 연결, 더미 구현 (DB 접근 없음)
├─ engines/                  얼굴 검출·정렬·인식: detector.py, align.py, fd_pipeline.py, embedder.py, retinaface/·adaface/(모델 코드, weight/)
├─ routers/                  courses.py, lectures.py, rooms.py, preview.py (요청 접수)
├─ services/
│  ├─ usaint.py              ★ usaint DB 를 읽고 쓰는 SQL 은 모두 여기에 (실제 usaint 연동 시 이 파일만 교체)
│  ├─ recognition.py         1:1 매칭 (순수 계산)
│  ├─ attendance.py          출석 처리 흐름 (start / 사진 / 현황)
│  ├─ storage.py             업로드 검증, 메모리 디코딩, 증명사진 읽기
│  └─ preview.py             카메라 미리보기: 축소 프레임에서 검출만
└─ scripts/
   ├─ seed_usaint.py         데모용 usaint.db + 예시 데이터
   └─ compute_embeddings.py  학생 임베딩 (재)계산 — FR 모델을 바꾸면 실행
src/frontend/
├─ index.html                1. 과목 목록
├─ course.html               2. 과목 홈 (회차 목록)
├─ method.html               3. 출결 방식 선택
├─ camera.html               4. 카메라
├─ attendance.html           5. 출결 현황
└─ js/                       화면별 스크립트, api.js(공용: API 호출, 회차 번호, 날짜 표시)
```

## 환경 변수 (.env)

| 이름 | 기본값 | 설명 |
|---|---|---|
| `DB_URL` (또는 `DATABASE_URL`) | 비움 → `DATA_DIR/usaint.db` | usaint DB 접속 주소 |
| `DATA_DIR` | `src/backend/data` | usaint.db, 예시 증명사진, 데모 사진 (상대경로는 저장소 루트 기준) |
| `CORS_ORIGINS` | `http://127.0.0.1:5500,http://localhost:5500` | 쉼표로 구분 |
| `FACE_ENGINE` | `retinaface` | 얼굴 엔진 ([가이드](../../docs/face_engine_guide.md)). `retinaface`는 검출(RetinaFace)·인식(AdaFace) 가중치 2개 필요, `dummy`는 가중치 없이 테스트·예시 데이터용 |
| `THRESHOLD` | `0.5` | 코사인 유사도가 이 값보다 커야 매칭 |
| `MAX_UPLOAD_MB` | `10` | 업로드 최대 크기 (카메라 원본 해상도 사진, 최대 4K JPEG) |

## 설계상 한계

- **DB에 없어 표시하지 않는 항목**: 학기, 교수명(과목 카드), 수업 시간, 건물 이름(회차 목록), LMS의 동영상·화상강의·과제·퀴즈·토론·공지 수. 화면에는 DB에 있는 값(과목명·코드, 회차 수, 주차-차수, 날짜, 강의실 번호)만 보여 줍니다.
- **카메라 연동 전**: `room.camera`(카메라 연결 정보)는 아직 쓰지 않고, 브라우저가 연결된 카메라로 촬영합니다. 카메라 화면에서 고른 강의실은 표시용입니다.
- **사진 미저장**: 업로드 사진은 메모리에서 처리한 뒤 버립니다. 나중에 인식 결과를 다시 확인하거나 재처리할 수 없습니다. (`lecture.photo_path`에 박스 친 사진을 저장하는 기능은 추후 작업. 한 회차에 사진이 여러 장 찍히므로 어느 사진을 남길지, 보관 기간을 정해야 합니다.)
- **지각 구분 없음**: 지각 인정 시간이 지난 뒤 처음 인식된 학생도 `present=true`(출석)로 기록됩니다. DB에 지각 상태가 없습니다.
- **수동 수정 없음**: 교수가 출석을 직접 고치는 API는 없습니다. 인식되지 않은 학생은 결석으로 남습니다.
- **수강 명단 기준**: 수강생만 비교하므로, 등록되지 않은 사람이나 다른 분반 학생은 매칭되지 않습니다(의도한 동작).
- 기본 엔진 `retinaface`(RetinaFace + AdaFace)의 `THRESHOLD=0.5`는 임시값입니다. 실제 강의실 사진으로 다시 정해야 합니다.
