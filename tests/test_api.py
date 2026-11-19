"""API 테스트: 과목·회차 조회, 회차 시작 → 사진 → 출결 현황 (더미 엔진, 임시 usaint DB)."""
from __future__ import annotations

import pytest
from sqlalchemy import inspect, select, update

from backend.models import Attendance, Course, Lecture, Room, Student

from .conftest import (
    D0,
    SEEDS,
    STRANGER,
    blank_png,
    classroom,
    face_array,
    present_map,
    to_jpeg,
    upload,
)


# ---------- 과목 목록 · 과목 홈(회차 목록) · 회차 정보 ----------
def test_courses_sorted_by_name_with_lecture_count(client, data):
    assert client.get("/courses").json() == [
        {"course_code": "C1", "course_name": "알고리즘(가반)", "lecture_count": 3},
        {"course_code": "C2", "course_name": "알고리즘(나반)", "lecture_count": 2},
        {"course_code": "C0", "course_name": "자료구조", "lecture_count": 0},
    ]


def test_courses_empty_db(client):
    assert client.get("/courses").json() == []


def test_course_detail(client, data):
    assert client.get("/courses/C1").json() == {"course_code": "C1", "course_name": "알고리즘(가반)"}


def test_course_lectures_sorted_by_date_week_session(client, data):
    body = client.get("/courses/C1/lectures").json()
    # 추가된 순서(l1, l3, l5)가 아니라 수업일 순(l1, l5, l3)
    assert [l["lecture_id"] for l in body] == [data.l1, data.l5, data.l3]
    assert body[0] == {
        "lecture_id": data.l1,
        "week": 10,
        "session_no": 1,
        "date": D0.isoformat(),
        "room_no": "21303",
    }
    assert client.get("/courses/C0/lectures").json() == []


def test_course_lectures_same_date_sorted_by_week_then_session(client, db):
    db.add_all([Room(room_no="R1"), Course(course_code="CX", course_name="과목")])
    db.flush()
    db.add_all(
        [
            Lecture(course_code="CX", room_no="R1", week=2, session_no=1, date=D0),
            Lecture(course_code="CX", room_no="R1", week=1, session_no=2, date=D0),
            Lecture(course_code="CX", room_no="R1", week=1, session_no=1, date=D0),
        ]
    )
    db.commit()
    body = client.get("/courses/CX/lectures").json()
    assert [(l["week"], l["session_no"]) for l in body] == [(1, 1), (1, 2), (2, 1)]


def test_unknown_course_is_404(client, data):
    assert client.get("/courses/NOPE").status_code == 404
    assert client.get("/courses/NOPE/lectures").status_code == 404


def test_lecture_detail(client, data):
    assert client.get(f"/lectures/{data.l2}").json() == {
        "lecture_id": data.l2,
        "course_code": "C2",
        "course_name": "알고리즘(나반)",
        "week": 10,
        "session_no": 1,
        "date": D0.isoformat(),
        "room_no": "21303",
    }


def test_room_date_lecture_search_removed(client, data):
    r = client.get("/lectures", params={"room_no": "21303", "date": D0.isoformat()})
    assert r.status_code in (404, 405)


# ---------- 강의실 · 회차 시작 ----------
def test_rooms(client, data):
    assert client.get("/rooms").json() == [
        {"room_no": "11101", "camera": None},
        {"room_no": "21303", "camera": "cam-21303"},
    ]


def test_start_creates_false_rows_for_enrolled_only(client, data, db):
    r = client.post(f"/lectures/{data.l1}/start")
    assert r.status_code == 200
    assert r.json() == {"lecture_id": data.l1, "student_count": 4, "created": 4}
    rows = db.execute(select(Attendance.student_id, Attendance.present).where(Attendance.lecture_id == data.l1)).all()
    assert sorted(rows) == [("S1", False), ("S2", False), ("S3", False), ("S6", False)]  # S4·S5 없음

    # 다시 호출해도 중복 생성 없음, 이미 true 인 행은 그대로
    db.execute(update(Attendance).where(Attendance.student_id == "S1").values(present=True))
    db.commit()
    assert client.post(f"/lectures/{data.l1}/start").json()["created"] == 0
    assert present_map(client, data.l1)["S1"] is True


# ---------- ③ 사진 → 매칭 → 출석 ----------
def test_photo_marks_matched_enrolled_students_present(client, data):
    client.post(f"/lectures/{data.l1}/start")
    r = upload(client, data.l1, classroom(SEEDS["S1"], SEEDS["S2"]))
    assert r.status_code == 200
    assert r.json() == {"face_count": 2, "matched_count": 2, "summary": {"total": 4, "present": 2, "absent": 2}}
    assert present_map(client, data.l1) == {"S1": True, "S2": True, "S3": False, "S6": False}


def test_only_enrolled_students_are_compared(client, data):
    # S4 는 나반만, S5 는 아무 과목도 수강하지 않음 → 가반 회차에서는 매칭되지 않음
    r = upload(client, data.l1, classroom(SEEDS["S4"], SEEDS["S5"], SEEDS["S3"]))
    assert r.json()["face_count"] == 3
    assert r.json()["matched_count"] == 1
    assert present_map(client, data.l1) == {"S1": False, "S2": False, "S3": True, "S6": False}
    # 같은 S4 얼굴이 나반 회차에서는 매칭됨
    assert upload(client, data.l2, classroom(SEEDS["S4"])).json()["matched_count"] == 1
    assert present_map(client, data.l2) == {"S3": False, "S4": True}


def test_stranger_is_not_matched(client, data):
    r = upload(client, data.l1, classroom(STRANGER))
    assert (r.json()["face_count"], r.json()["matched_count"]) == (1, 0)
    assert not any(present_map(client, data.l1).values())


def test_one_face_matches_at_most_one_student(client, data, db):
    # S2 의 임베딩을 S1 과 똑같이 만들어 한 얼굴이 두 학생과 유사도 1.0 이 되게 한다
    s1 = db.get(Student, "S1").embedding
    db.execute(update(Student).where(Student.student_id == "S2").values(embedding=s1))
    db.commit()
    r = upload(client, data.l1, classroom(SEEDS["S1"]))
    assert r.json()["matched_count"] == 1
    p = present_map(client, data.l1)
    assert p["S1"] + p["S2"] == 1


def test_one_student_matches_at_most_one_face(client, data):
    # 같은 학생 얼굴이 사진에 두 번 → 얼굴 2개 중 1개만 매칭
    r = upload(client, data.l1, classroom(SEEDS["S1"], SEEDS["S1"]))
    assert (r.json()["face_count"], r.json()["matched_count"]) == (2, 1)
    assert r.json()["summary"]["present"] == 1


def test_present_stays_true_across_photos(client, data):
    upload(client, data.l1, classroom(SEEDS["S1"]))
    upload(client, data.l1, classroom(SEEDS["S2"]))  # S1 없음
    upload(client, data.l1, blank_png())  # 얼굴 없음
    upload(client, data.l1, to_jpeg(face_array(STRANGER)), filename="c.jpg", ctype="image/jpeg")
    assert present_map(client, data.l1) == {"S1": True, "S2": True, "S3": False, "S6": False}


def test_photo_without_start_prepares_rows(client, data):
    r = upload(client, data.l2, classroom(SEEDS["S3"]))
    assert r.json()["summary"] == {"total": 2, "present": 1, "absent": 1}


def test_student_without_embedding_is_skipped(client, data):
    # S6 는 임베딩이 NULL → 비교 대상이 아니므로 오류 없이 결석 유지
    upload(client, data.l1, classroom(SEEDS["S1"], SEEDS["S2"], SEEDS["S3"]))
    assert present_map(client, data.l1)["S6"] is False


def test_uploaded_photo_is_not_stored(client, data, settings, app):
    def snapshot():
        return sorted(p.relative_to(settings.data_dir) for p in settings.data_dir.rglob("*") if p.is_file())

    before = snapshot()
    db_size = (settings.data_dir / "usaint.db").stat().st_size
    for _ in range(3):
        assert upload(client, data.l1, classroom(SEEDS["S1"], STRANGER)).status_code == 200
    assert snapshot() == before  # 새 파일 없음 (사진 파일 저장 안 함)

    # DB 에도 사진을 담을 테이블·컬럼이 없고, 바뀐 것은 attendance 뿐
    insp = inspect(app.state.db_engine)
    assert sorted(insp.get_table_names()) == ["attendance", "class", "enrollment", "lecture", "room", "student"]
    blob_cols = [
        (t, c["name"]) for t in insp.get_table_names() for c in insp.get_columns(t) if str(c["type"]).upper() == "BLOB"
    ]
    assert blob_cols == [("student", "embedding")]
    assert (settings.data_dir / "usaint.db").stat().st_size <= db_size + 8192  # 사진 크기만큼 커지지 않음


# ---------- ④ 출결 현황 ----------
def test_attendance_response(client, data):
    upload(client, data.l1, classroom(SEEDS["S2"]))
    body = client.get(f"/lectures/{data.l1}/attendance").json()
    assert body["lecture"]["course_name"] == "알고리즘(가반)"
    assert body["lecture"]["lecture_id"] == data.l1
    assert body["summary"] == {"total": 4, "present": 1, "absent": 3}
    assert body["students"][1] == {"student_id": "S2", "name": "학생S2", "present": True}
    assert all(set(s) == {"student_id", "name", "present"} for s in body["students"])


def test_attendance_before_start_is_empty(client, data):
    body = client.get(f"/lectures/{data.l3}/attendance").json()
    assert body["summary"] == {"total": 0, "present": 0, "absent": 0}
    assert body["students"] == []


# ---------- 오류 · 개인정보 ----------
def test_unknown_lecture_is_404(client, data):
    assert client.get("/lectures/9999").status_code == 404
    assert client.post("/lectures/9999/start").status_code == 404
    assert upload(client, 9999, classroom(1)).status_code == 404
    assert client.get("/lectures/9999/attendance").status_code == 404


def test_invalid_files(client, data):
    lid = data.l1
    assert upload(client, lid, classroom(1), filename="a.gif", ctype="image/gif").status_code == 415
    assert upload(client, lid, b"not an image", filename="a.png").status_code == 400
    assert upload(client, lid, b"", filename="a.png").status_code == 400
    big = b"\x89PNG" + b"0" * (1024 * 1024 + 10)  # 테스트 설정 MAX_UPLOAD_MB=1
    assert upload(client, lid, big, filename="a.png").status_code == 413
    # 확장자는 png 인데 실제 내용이 GIF
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.fromarray(face_array(1)).save(buf, format="GIF")
    assert upload(client, lid, buf.getvalue(), filename="a.png").status_code == 415
    # 실패한 요청은 출석을 바꾸지 않음
    assert not any(present_map(client, lid).values())


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_keys(v)


def _has_number_vector(obj) -> bool:
    """숫자 배열(임베딩 같은 벡터)이 들어 있는지."""
    if isinstance(obj, list):
        if obj and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in obj):
            return True
        return any(_has_number_vector(v) for v in obj)
    if isinstance(obj, dict):
        return any(_has_number_vector(v) for v in obj.values())
    return False


def test_responses_never_contain_embedding(client, data):
    responses = [
        client.get("/rooms"),
        client.get("/courses"),
        client.get("/courses/C1"),
        client.get("/courses/C1/lectures"),
        client.get(f"/lectures/{data.l1}"),
        client.post(f"/lectures/{data.l1}/start"),
        upload(client, data.l1, classroom(SEEDS["S1"])),
        client.get(f"/lectures/{data.l1}/attendance"),
        client.get("/health"),
    ]
    for r in responses:
        assert r.status_code == 200
        body = r.json()
        assert "embedding" not in set(_walk_keys(body))  # /health 의 embedding_dim(차원 숫자)은 값이 아님
        assert not _has_number_vector(body)


def test_old_apis_removed(client):
    for path in ("/students", "/sessions", "/detections/1", "/photos/1/image"):
        assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    "path, script, marker",
    [
        ("/app/", "js/index.js", 'id="courseList"'),  # 첫 화면 = 과목 목록
        ("/app/course.html", "js/course.js", 'id="lectureList"'),
        ("/app/method.html", "js/method.js", 'id="eBtn"'),
        ("/app/camera.html", "js/camera.js", 'id="shootBtn"'),
        ("/app/attendance.html", "js/attendance.js", 'id="studentList"'),
    ],
)
def test_frontend_pages_served(client, path, script, marker):
    page = client.get(path)
    assert page.status_code == 200
    assert 'src="js/api.js"' in page.text and f'src="{script}"' in page.text and marker in page.text
    # 연결된 스크립트도 실제로 제공된다
    assert client.get("/app/js/api.js").status_code == 200
    assert client.get(f"/app/{script}").status_code == 200


def test_frontend_no_removed_api_calls(client):
    """프론트엔드가 삭제된 API(강의실+날짜 회차 조회, /sessions)를 부르지 않는다."""
    for script in ("api", "index", "course", "method", "camera", "attendance"):
        js = client.get(f"/app/js/{script}.js").text
        assert "/lectures?room_no" not in js and "/sessions" not in js, script


def test_health_frontend_and_cors(client):
    assert client.get("/health").json() == {"status": "ok", "face_engine": "dummy", "embedding_dim": 128}
    assert client.get("/", follow_redirects=False).headers["location"] == "/app/"
    r = client.options(
        "/rooms", headers={"Origin": "http://127.0.0.1:5500", "Access-Control-Request-Method": "GET"}
    )
    assert r.headers.get("access-control-allow-origin") == "http://127.0.0.1:5500"
    r = client.options("/rooms", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers
