"""시퀀스 ②~④ API 테스트 (더미 엔진, 임시 usaint DB)."""
from __future__ import annotations

import datetime as dt

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


# ---------- ② 강의실 · 회차 ----------
def test_rooms(client, data):
    assert client.get("/rooms").json() == [
        {"room_no": "11101", "camera": None},
        {"room_no": "21303", "camera": "cam-21303"},
    ]


def test_find_lectures_zero_one_two(client, data):
    def find(room, day):
        r = client.get("/lectures", params={"room_no": room, "date": day.isoformat()})
        assert r.status_code == 200
        return r.json()

    two = find("21303", D0)
    assert [l["lecture_id"] for l in two] == [data.l1, data.l2]
    assert two[0] == {
        "lecture_id": data.l1,
        "course_code": "C1",
        "course_name": "알고리즘(가반)",
        "week": 10,
        "session_no": 1,
        "date": D0.isoformat(),
        "room_no": "21303",
    }
    assert [l["lecture_id"] for l in find("11101", D0)] == [data.l4]
    assert find("21303", D0 + dt.timedelta(days=1)) == []
    assert find("99999", D0) == []


def test_find_lectures_date_defaults_to_today(client, db):
    db.add_all([Room(room_no="R9"), Course(course_code="CX", course_name="오늘 과목")])
    db.flush()
    db.add(Lecture(course_code="CX", room_no="R9", week=1, session_no=1, date=dt.date.today()))
    db.commit()
    assert [l["course_code"] for l in client.get("/lectures", params={"room_no": "R9"}).json()] == ["CX"]


def test_find_lectures_requires_room(client):
    assert client.get("/lectures").status_code == 422


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
        client.get("/lectures", params={"room_no": "21303", "date": D0.isoformat()}),
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


def test_health_frontend_and_cors(client):
    assert client.get("/health").json() == {"status": "ok", "face_engine": "dummy", "embedding_dim": 128}
    page = client.get("/app/camera.html")
    assert page.status_code == 200 and "js/api.js" in page.text
    assert client.get("/", follow_redirects=False).headers["location"] == "/app/"
    r = client.options(
        "/rooms", headers={"Origin": "http://127.0.0.1:5500", "Access-Control-Request-Method": "GET"}
    )
    assert r.headers.get("access-control-allow-origin") == "http://127.0.0.1:5500"
    r = client.options("/rooms", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers
