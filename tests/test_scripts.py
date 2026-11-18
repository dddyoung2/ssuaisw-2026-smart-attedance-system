"""seed_usaint / compute_embeddings 스크립트 테스트 (임시 폴더)."""
from __future__ import annotations

import datetime as dt

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.database import make_engine, make_session_factory
from backend.face_engine import DummyDetector, DummyEmbedder, FaceEmbedder, FaceEngine, create_face_engine, register_engine
from backend.factory import create_app
from backend.models import Course, Enrollment, Lecture, Room, Student
from backend.scripts.compute_embeddings import compute_all
from backend.scripts.seed_usaint import seed

from .conftest import make_settings

TODAY = dt.date(2026, 11, 18)


def test_seed_creates_demo_usaint_db(tmp_path):
    settings = make_settings(tmp_path)
    result = seed(settings, today=TODAY)

    eng = make_engine(settings.db_url)
    with make_session_factory(eng)() as db:
        count = lambda m: db.scalar(select(func.count()).select_from(m))
        assert (count(Room), count(Course), count(Student), count(Enrollment), count(Lecture)) == (1, 2, 6, 7, 6)
        assert all(s.embedding is not None and len(s.embedding) == 128 * 4 for s in db.scalars(select(Student)))
        todays = db.scalars(select(Lecture).where(Lecture.room_no == "21303", Lecture.date == TODAY)).all()
        assert sorted(l.course_code for l in todays) == ["2150163301", "2150163302"]
    eng.dispose()

    assert len(result["todays_lectures"]) == 2
    assert len(list(settings.student_photo_dir.glob("*.png"))) == 6
    assert len(list(settings.demo_photo_dir.glob("*.png"))) == 3

    # 다시 실행하면 새로 만든다 (중복 오류 없음)
    seed(settings, today=TODAY)


def test_seed_demo_photos_mark_attendance(tmp_path):
    settings = make_settings(tmp_path, max_upload_mb=5)
    lid_a = seed(settings, today=TODAY)["todays_lectures"][0][0]
    with TestClient(create_app(settings)) as c:
        def up(name):
            path = settings.demo_photo_dir / name
            return c.post(f"/lectures/{lid_a}/photos", files={"photo": (name, path.read_bytes(), "image/png")}).json()

        assert up("lecture_A_non_enrolled_1005.png")["matched_count"] == 0  # 비수강생
        r = up("lecture_A_students_1001_1002_1003.png")
        assert (r["face_count"], r["matched_count"]) == (3, 3)
        assert r["summary"] == {"total": 4, "present": 3, "absent": 1}


def test_compute_embeddings_after_model_change(tmp_path):
    """FR 모델(임베딩 차원)이 바뀌면 compute_embeddings 로 다시 계산해야 매칭된다."""

    class Embedder64(FaceEmbedder):
        dim = 64

        def embed(self, face_image):
            return DummyEmbedder().embed(face_image)[:64]

    register_engine("dummy64", lambda: FaceEngine("dummy64", DummyDetector(), Embedder64()))
    settings = make_settings(tmp_path, face_engine="dummy64", max_upload_mb=5)
    lid_a = seed(settings, today=TODAY, with_embeddings=False)["todays_lectures"][0][0]

    # 128차원(이전 모델) 임베딩을 넣어 둔 상태 → 새 모델(64차원)에서는 비교 대상에서 빠짐
    eng = make_engine(settings.db_url)
    Session = make_session_factory(eng)
    with Session() as db:
        assert compute_all(db, settings, create_face_engine("dummy")).ok == 6
        db.commit()

    photo = (settings.demo_photo_dir / "lecture_A_students_1001_1002_1003.png").read_bytes()
    with TestClient(create_app(settings)) as c:
        up = lambda: c.post(f"/lectures/{lid_a}/photos", files={"photo": ("a.png", photo, "image/png")}).json()
        assert up()["matched_count"] == 0

        with Session() as db:
            report = compute_all(db, settings, create_face_engine("dummy64"))
            db.commit()
        assert (report.ok, report.failed) == (6, [])
        assert up()["matched_count"] == 3

    # 증명사진이 없거나 얼굴이 1개가 아니면 NULL 로 바꾸고 실패 목록에 남김
    (settings.student_photo_dir / "20231001.png").unlink()
    from PIL import Image

    Image.fromarray(np.full((50, 50, 3), 9, np.uint8)).save(settings.student_photo_dir / "20231002.png")
    with Session() as db:
        report = compute_all(db, settings, create_face_engine("dummy64"))
        db.commit()
        assert sorted(sid for sid, _ in report.failed) == ["20231001", "20231002"]
        assert db.get(Student, "20231001").embedding is None
    eng.dispose()
