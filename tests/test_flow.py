"""더미 모델 기반 전체 흐름 테스트:
학생 등록 → 수업 생성 → 사진 업로드 → 출석 조회 → 매칭 수정 → 수동 수정 → 삭제."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.factory import create_app

from .conftest import (
    blank_png,
    classroom,
    face_array,
    make_settings,
    register,
    to_jpeg,
    to_png,
    upload,
)

A, B, C, STRANGER = 1, 2, 3, 99  # 얼굴 패턴 시드


def statuses(att_json) -> dict[str, str]:
    return {s["student_id"]: s["status"] for s in att_json["students"]}


def test_full_flow(client, settings):
    # 1) 학생 등록
    for sid, name, seed in [("20231001", "김민준", A), ("20231002", "이서연", B), ("20231003", "박도윤", C)]:
        r = register(client, sid, name, seed)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["has_embedding"] is True and body["embedding_dim"] == 128
        assert "embedding" not in body

    students = client.get("/students").json()
    assert [s["student_id"] for s in students] == ["20231001", "20231002", "20231003"]
    assert all("embedding" not in s for s in students)

    r = client.get("/students/20231001/photo")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"

    # 2) 수업 생성 (course_name 생략 → 기본값)
    r = client.post("/sessions", json={"room": "공학관 3층 301호"})
    assert r.status_code == 201
    sess = r.json()
    sid = sess["session_id"]
    assert sess["course_name"] == "데모 수업" and sess["photo_count"] == 0
    assert client.get("/sessions").json()[0]["session_id"] == sid

    # 처음에는 전원 결석
    att = client.get(f"/sessions/{sid}/attendance").json()
    assert att["summary"] == {"total": 3, "present": 0, "absent": 3}

    # 3) 사진 업로드 #1: A, B 두 명
    r = upload(client, sid, classroom(A, B))
    assert r.status_code == 201, r.text
    res = r.json()
    assert res["photo"]["face_count"] == 2
    matched = [d["matched_student_id"] for d in res["detections"]]
    assert matched == ["20231001", "20231002"]
    assert all(d["similarity"] > 0.99 for d in res["detections"])
    assert res["detections"][0]["matched_name"] == "김민준"
    assert statuses(res["attendance"]) == {"20231001": "present", "20231002": "present", "20231003": "absent"}
    det_b_photo1 = res["detections"][1]["detection_id"]

    # 4) 사진 업로드 #2: A + 모르는 사람 → 결과 합치기 (B 는 계속 present)
    r = upload(client, sid, classroom(A, STRANGER))
    res2 = r.json()
    assert res2["detections"][0]["matched_student_id"] == "20231001"
    stranger = res2["detections"][1]
    assert stranger["matched_student_id"] is None
    assert stranger["similarity"] is not None and stranger["similarity"] <= settings.threshold
    assert statuses(res2["attendance"])["20231002"] == "present"

    # JPEG 업로드도 동작
    r = upload(client, sid, to_jpeg(face_array(A)), filename="cam.jpg", ctype="image/jpeg")
    assert r.status_code == 201
    assert r.json()["detections"][0]["matched_student_id"] == "20231001"

    # 5) 출석 조회
    att = client.get(f"/sessions/{sid}/attendance").json()
    assert att["summary"] == {"total": 3, "present": 2, "absent": 1}
    by_id = {s["student_id"]: s for s in att["students"]}
    assert by_id["20231001"]["best_similarity"] > 0.99
    assert by_id["20231003"]["best_similarity"] is None

    dets = client.get(f"/sessions/{sid}/detections").json()
    assert len(dets) == 5
    assert all(d["verified"] is False for d in dets)

    photos = client.get(f"/sessions/{sid}/photos").json()
    assert len(photos) == 3
    assert client.get(photos[0]["image_url"]).status_code == 200
    face = client.get(dets[0]["face_url"])
    assert face.status_code == 200 and face.headers["content-type"] == "image/jpeg"

    # 6) 교수 매칭 수정: 모르는 사람 → C 로 지정
    r = client.patch(f"/detections/{stranger['detection_id']}", json={"matched_student_id": "20231003"})
    assert r.status_code == 200
    assert r.json()["verified"] is True and r.json()["matched_name"] == "박도윤"
    assert statuses(client.get(f"/sessions/{sid}/attendance").json())["20231003"] == "present"

    # B 의 유일한 검출을 '등록 학생 아님' 으로 → B 결석
    r = client.patch(f"/detections/{det_b_photo1}", json={"matched_student_id": None})
    assert r.status_code == 200 and r.json()["matched_student_id"] is None
    assert statuses(client.get(f"/sessions/{sid}/attendance").json())["20231002"] == "absent"

    # 없는 학생으로 수정 → 404
    assert client.patch(f"/detections/{det_b_photo1}", json={"matched_student_id": "nope"}).status_code == 404

    # 7) 출석 수동 수정: B 를 present 로 지정 → 재계산돼도 유지
    r = client.patch(f"/sessions/{sid}/attendance/20231002", json={"status": "present"})
    assert r.status_code == 200
    b = {s["student_id"]: s for s in r.json()["students"]}["20231002"]
    assert b["status"] == "present" and b["source"] == "manual"
    upload(client, sid, classroom(C))  # 재계산 유발
    assert statuses(client.get(f"/sessions/{sid}/attendance").json())["20231002"] == "present"
    # auto 로 되돌리면 인식 결과(결석)로 복귀
    r = client.patch(f"/sessions/{sid}/attendance/20231002", json={"status": "auto"})
    b = {s["student_id"]: s for s in r.json()["students"]}["20231002"]
    assert b["status"] == "absent" and b["source"] == "auto"

    # 8) 학생 삭제: 사진 파일 삭제, 매칭은 NULL, 출석에서 빠짐
    photo_files = list(settings.student_photo_dir.glob("20231001_*"))
    assert len(photo_files) == 1
    assert client.delete("/students/20231001").status_code == 204
    assert not photo_files[0].exists()
    assert client.get("/students/20231001/photo").status_code == 404
    att = client.get(f"/sessions/{sid}/attendance").json()
    assert "20231001" not in statuses(att) and att["summary"]["total"] == 2
    dets = client.get(f"/sessions/{sid}/detections").json()
    assert all(d["matched_student_id"] != "20231001" for d in dets)

    # 9) 사진 모두 지우기 → 파일 삭제, 출석 재계산 (C 는 검출이 사라져 결석)
    session_dir = settings.session_photo_dir / str(sid)
    assert any(session_dir.iterdir())
    r = client.delete(f"/sessions/{sid}/photos")
    assert r.status_code == 200
    assert statuses(r.json())["20231003"] == "absent"
    assert not any(session_dir.iterdir())
    assert client.get(f"/sessions/{sid}/detections").json() == []


def test_student_registration_errors(client):
    # 얼굴 0개
    r = client.post(
        "/students",
        data={"student_id": "1", "name": "무"},
        files={"photo": ("blank.png", blank_png(), "image/png")},
    )
    assert r.status_code == 400 and "검출되지" in r.json()["detail"]

    # 얼굴 2개
    r = client.post(
        "/students",
        data={"student_id": "2", "name": "둘"},
        files={"photo": ("two.png", classroom(A, B), "image/png")},
    )
    assert r.status_code == 400 and "2개" in r.json()["detail"]

    # 허용되지 않는 확장자
    r = register(client, "3", "셋", A, filename="photo.gif")
    assert r.status_code == 415

    # 확장자는 png 인데 내용이 이미지가 아님
    r = client.post(
        "/students",
        data={"student_id": "4", "name": "넷"},
        files={"photo": ("fake.png", b"not an image", "image/png")},
    )
    assert r.status_code == 400

    # 크기 초과 (테스트 설정 MAX_UPLOAD_MB=1)
    r = client.post(
        "/students",
        data={"student_id": "5", "name": "다섯"},
        files={"photo": ("big.png", b"\x89PNG" + b"0" * (1024 * 1024 + 10), "image/png")},
    )
    assert r.status_code == 413

    # 잘못된 학번 형식
    assert register(client, "../evil", "x", A).status_code == 422

    # 중복 학번
    assert register(client, "20231001", "김민준", A).status_code == 201
    assert register(client, "20231001", "김민준", A).status_code == 409

    # 실패한 요청은 파일을 남기지 않음
    assert client.get("/students").json()[0]["student_id"] == "20231001"


def test_not_found(client):
    assert client.get("/sessions/999/attendance").status_code == 404
    assert upload(client, 999, classroom(A)).status_code == 404
    assert client.patch("/detections/999", json={"matched_student_id": None}).status_code == 404
    assert client.get("/photos/999/image").status_code == 404
    assert client.delete("/students/none").status_code == 404


def test_use_verified_faces(tmp_path):
    """USE_VERIFIED_FACES=true 면 이전 수업에서 확인된 얼굴도 비교 대상."""
    for flag, expected in [(False, None), (True, "20231003")]:
        settings = make_settings(tmp_path / str(flag), use_verified_faces=flag)
        with TestClient(create_app(settings)) as c:
            register(c, "20231003", "박도윤", C)
            s1 = c.post("/sessions", json={"room": "301"}).json()["session_id"]
            det = upload(c, s1, classroom(STRANGER)).json()["detections"][0]
            assert det["matched_student_id"] is None
            c.patch(f"/detections/{det['detection_id']}", json={"matched_student_id": "20231003"})

            s2 = c.post("/sessions", json={"room": "301"}).json()["session_id"]
            det2 = upload(c, s2, classroom(STRANGER)).json()["detections"][0]
            assert det2["matched_student_id"] == expected


def test_cors_and_health(client):
    r = client.options(
        "/students",
        headers={"Origin": "http://127.0.0.1:5500", "Access-Control-Request-Method": "POST"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://127.0.0.1:5500"
    r = client.options(
        "/students",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in r.headers
    assert client.get("/health").json() == {"status": "ok", "face_engine": "dummy", "embedding_dim": 128}


def test_frontend_served(client):
    r = client.get("/app/")
    assert r.status_code == 200 and "출결 방식 선택" in r.text
    assert "js/api.js" in client.get("/app/camera.html").text
    assert client.get("/app/js/api.js").status_code == 200
    assert client.get("/", follow_redirects=False).headers["location"] == "/app/"


def test_session_photo_png_saved_as_file_not_db(client, settings):
    register(client, "1", "a", A)
    sid = client.post("/sessions", json={"room": "r"}).json()["session_id"]
    upload(client, sid, to_png(face_array(A)))
    files = list((settings.session_photo_dir / str(sid)).iterdir())
    assert len(files) == 1 and files[0].suffix == ".png"
