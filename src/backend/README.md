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
cd src
python -m backend.scripts.seed_usaint
cd ..

# 3) 서버 실행
python main.py                     # 개발 중에는 python main.py --reload

# 4) 화면 확인: http://127.0.0.1:8000/app/
#    카메라 → 강의실 21303 → "오늘 수업 찾기" → 수업 선택(가반/나반) → 촬영 시작 → 출결 현황 보기
```

| 주소 | 내용 |
|---|---|
| http://127.0.0.1:8000/app/ | 출결 화면 (`src/frontend`를 백엔드가 직접 제공) |
| http://127.0.0.1:8000/docs | API 문서 (Swagger UI) |
| http://127.0.0.1:8000/health | 서버 상태와 현재 얼굴 엔진 |

```powershell
python -m pytest                   # 테스트 (저장소 루트에서)
```

Python 3.10 이상이 필요합니다. Python 3.11(numpy 1.26.4)과 Python 3.14(numpy 2.x)에서 테스트를 확인했습니다.

### seed가 만드는 예시 데이터 (`DATA_DIR`, 기본 `src/backend/data/`, git 제외)

| 항목 | 내용 |
|---|---|
| room | `21303` (정보과학관, 카메라 1개) |
| class | `2150163301` 알고리즘(가반), `2150163302` 알고리즘(나반) |
| student | 6명. 증명사진은 실제 얼굴이 아닌 **합성 패턴 이미지**(`photos/students/<학번>.png`)이고, 임베딩도 계산해서 넣음 |
| enrollment | 가반 4명, 나반 3명 (20231004는 두 분반을 모두 수강) |
| lecture | **실행한 날(오늘)** 21303에 가반·나반 각 1회차(같은 강의실·같은 날 2개), 지난주 2회차, 이틀 뒤 2회차 |
| demo/ | 데모용 단체 사진 3장 (아래 참고) |

**더미 엔진에서 출석이 잡히는 걸 보려면**
더미 엔진은 실제 얼굴을 인식하지 못해서 웹캠으로 찍은 사진은 아무와도 매칭되지 않습니다. 대신 `/docs`의 `POST /lectures/{id}/photos`에 `demo/` 사진을 올리면 출석이 반영됩니다.

| 파일 | 결과 (가반 회차 기준) |
|---|---|
| `lecture_A_students_1001_1002_1003.png` | 3명 출석 |
| `lecture_A_non_enrolled_1005.png` | 0명 (나반 학생이라 비교 대상이 아님) |
| `lecture_B_students_1005_1006.png` | 나반 회차에서 2명 출석 |

**Live Server로 열 때**: 백엔드가 `src/backend/data`의 DB에 쓸 때마다 페이지가 새로고침될 수 있습니다. `/app/` 주소로 여는 것을 권장합니다.

## 동작 시퀀스

| 단계 | 화면 → 백엔드 | 백엔드 처리 |
|---|---|---|
| ① 출결 방식 선택 | (첫 화면) | – |
| ② 강의실·카메라 선택 | `GET /rooms` | ROOM 조회 → `room_no`, `camera` |
| ② 수업 확인 | `GET /lectures?room_no=…&date=오늘` | LECTURE에서 강의실·날짜가 같은 회차 조회. **여러 개면 교수가 고름**, 없으면 "오늘 이 강의실에 등록된 수업이 없습니다" |
| ② 회차 확정 | `POST /lectures/{id}/start` | 그 과목 수강생 전원의 ATTENDANCE 행이 없으면 `present=false`로 생성 |
| ③ 촬영 (즉시 1장, 이후 60초마다) | `POST /lectures/{id}/photos` | ENROLLMENT⋈STUDENT JOIN 한 번으로 **수강생 임베딩만** 조회 → 얼굴 엔진(검출 → 정렬·크롭 → 임베딩) → **1:1 매칭** → 매칭된 학생 `present=true`. **사진은 저장하지 않음** |
| ④ 출결현황 (10초마다) | `GET /lectures/{id}/attendance` | ATTENDANCE⋈STUDENT → 학번, 이름, 출석 여부, 요약 |

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
| lecture | lecture_id(자동 증가), course_code, room_no, week, session_no, date | PK lecture_id, FK → class **CASCADE**, FK → room |
| attendance | lecture_id, student_id, present(기본 false) | PK (lecture_id, student_id), FK → lecture·student **CASCADE** |

- 증명사진은 파일로 두고 `photo_path`(DATA_DIR 기준 상대경로)만 저장합니다.
- `embedding`은 "증명사진에서 미리 추출해 넣어 둔 값"(float32 배열 → bytes)입니다. NULL인 학생은 매칭에서 제외됩니다.
- `Course.students`는 enrollment를 거쳐 수강생 목록을 바로 가져오는 조회용 relationship입니다.
- SQLite에서 FK가 동작하도록 연결할 때마다 `PRAGMA foreign_keys=ON`을 실행합니다.

## API

| Method | 경로 | 응답 |
|---|---|---|
| GET | `/rooms` | `[{room_no, camera}]` |
| GET | `/lectures?room_no=21303&date=2026-11-18` | `[{lecture_id, course_code, course_name, week, session_no, date, room_no}]` (`date`를 생략하면 서버 기준 오늘) |
| POST | `/lectures/{lecture_id}/start` | `{lecture_id, student_count, created}` |
| POST | `/lectures/{lecture_id}/photos` | multipart `photo` (jpg/jpeg/png) → `{face_count, matched_count, summary:{total, present, absent}}` |
| GET | `/lectures/{lecture_id}/attendance` | `{lecture:{…}, summary:{…}, students:[{student_id, name, present}]}` |
| GET | `/health` | `{status, face_engine, embedding_dim}` |

- 없는 `lecture_id`는 404를 반환합니다.
- 잘못된 파일: 빈 파일이거나 이미지가 아니면 400, 크기 초과(`MAX_UPLOAD_MB`)는 413, jpg/png가 아니면 415를 반환합니다.
- 어떤 응답에도 임베딩 값은 포함되지 않습니다.

## 코드 구조

```
main.py (저장소 루트)        python main.py → uvicorn
src/backend/
├─ main.py, factory.py       앱 조립: DB, 얼굴 엔진, CORS, 라우터, /app 정적 제공
├─ config.py                 환경설정 (.env)
├─ database.py               DB 엔진·세션, SQLite FK PRAGMA
├─ models.py                 usaint 6개 테이블
├─ schemas.py                응답 형식
├─ face_engine.py            얼굴 엔진 인터페이스 + 더미 구현 (DB 접근 없음)
├─ routers/                  rooms.py, lectures.py (요청 접수)
├─ services/
│  ├─ usaint.py              ★ usaint DB 를 읽고 쓰는 SQL 은 모두 여기에 (실제 usaint 연동 시 이 파일만 교체)
│  ├─ recognition.py         1:1 매칭 (순수 계산)
│  ├─ attendance.py          출석 처리 흐름 (start / 사진 / 현황)
│  └─ storage.py             업로드 검증, 메모리 디코딩, 증명사진 읽기
└─ scripts/
   ├─ seed_usaint.py         데모용 usaint.db + 예시 데이터
   └─ compute_embeddings.py  학생 임베딩 (재)계산 — FR 모델을 바꾸면 실행
```

## 환경 변수 (.env)

| 이름 | 기본값 | 설명 |
|---|---|---|
| `DB_URL` (또는 `DATABASE_URL`) | 비움 → `DATA_DIR/usaint.db` | usaint DB 접속 주소 |
| `DATA_DIR` | `src/backend/data` | usaint.db, 예시 증명사진, 데모 사진 (상대경로는 저장소 루트 기준) |
| `CORS_ORIGINS` | `http://127.0.0.1:5500,http://localhost:5500` | 쉼표로 구분 |
| `FACE_ENGINE` | `dummy` | 얼굴 엔진 ([가이드](../../docs/face_engine_guide.md)) |
| `THRESHOLD` | `0.5` | 코사인 유사도가 이 값보다 커야 매칭 |
| `MAX_UPLOAD_MB` | `5` | 업로드 최대 크기 |

## 설계상 한계

- **회차 선택**: LECTURE에 시간 컬럼이 없어서 같은 강의실·같은 날에 회차가 여러 개면 자동으로 정할 수 없습니다. 교수가 화면에서 직접 고릅니다.
- **사진 미저장**: 업로드 사진은 메모리에서 처리한 뒤 버립니다(README의 "사진 즉시 삭제"와 일치). 나중에 인식 결과를 다시 확인하거나 재처리할 수 없습니다.
- **수동 수정 없음**: 교수가 출석을 직접 고치는 API는 없습니다. 인식되지 않은 학생은 결석으로 남습니다.
- **수강 명단 기준**: 수강생만 비교하므로, 등록되지 않은 사람이나 다른 분반 학생은 매칭되지 않습니다(의도한 동작).
- 더미 엔진은 실제 얼굴을 인식하지 못합니다. 실제 모델(RetinaFace + FR 모델)을 연결해야 웹캠 사진으로 출석이 잡힙니다.
