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

TODAY = dt.date(2026, 11, 18)  # 수요일, 12주차

SYSPROG, ALGO, OSS = "2150165801", "2150163303", "2150061301"


def _today_lecture(result, course_code: str) -> int:
    (lid,) = [lid for lid, code, _, _ in result["todays_lectures"] if code == course_code]
    return lid


def _counts(settings):
    eng = make_engine(settings.db_url)
    try:
        with make_session_factory(eng)() as db:
            count = lambda m: db.scalar(select(func.count()).select_from(m))
            return tuple(count(m) for m in (Room, Course, Student, Enrollment, Lecture))
    finally:
        eng.dispose()


def _schedule(settings, course_code):
    eng = make_engine(settings.db_url)
    try:
        with make_session_factory(eng)() as db:
            rows = db.execute(
                select(Lecture.week, Lecture.session_no, Lecture.date, Lecture.room_no)
                .where(Lecture.course_code == course_code)
                .order_by(Lecture.date)
            ).all()
            return [tuple(r) for r in rows]
    finally:
        eng.dispose()


def test_seed_creates_demo_usaint_db(tmp_path):
    settings = make_settings(tmp_path)
    result = seed(settings, today=TODAY)

    # 강의실 4 · 과목 3 · 학생 8 · 수강 5+4+4
    # 회차: 시스템프로그래밍 30(+오늘 1) · 알고리즘 15(+오늘 1) · 오픈소스 15(수요일이라 오늘이 정규 회차)
    assert _counts(settings) == (4, 3, 8, 13, 31 + 16 + 15)
    assert result["lecture_count"] == 62

    eng = make_engine(settings.db_url)
    with make_session_factory(eng)() as db:
        assert all(s.embedding is not None and len(s.embedding) == 128 * 4 for s in db.scalars(select(Student)))
        names = [c.course_name for c in db.scalars(select(Course))]
        assert sorted(names) == ["시스템프로그래밍", "알고리즘", "오픈소스기반기초설계"]
    eng.dispose()

    # 모든 과목에 오늘 회차가 있다
    assert sorted(code for _, code, _, _ in result["todays_lectures"]) == sorted([SYSPROG, ALGO, OSS])
    assert len(list(settings.student_photo_dir.glob("*.png"))) == 8
    assert len(list(settings.demo_photo_dir.glob("*.png"))) == 4


def test_seed_weekly_schedule(tmp_path):
    settings = make_settings(tmp_path)
    seed(settings, today=TODAY, with_embeddings=False)
    d = dt.date

    algo = _schedule(settings, ALGO)
    assert algo[0] == (1, 1, d(2026, 9, 1), "21304")  # 1-1 9/1 (화)
    assert algo[1] == (2, 1, d(2026, 9, 8), "21304")
    assert max(w for w, _, _, _ in algo) == 15
    assert (12, 2, TODAY, "21304") in algo  # 오늘(수) 추가 회차 → 12주차 2차시

    sysprog = _schedule(settings, SYSPROG)
    assert sysprog[:2] == [(1, 1, d(2026, 9, 1), "21303"), (1, 2, d(2026, 9, 3), "21303")]  # 주 2회 화·목
    assert [(w, s, x) for w, s, x, _ in sysprog if w == 12] == [
        (12, 1, d(2026, 11, 17)),
        (12, 2, TODAY),  # 오늘 추가 회차가 끼면 그 주의 차수를 날짜순으로 다시 매김
        (12, 3, d(2026, 11, 19)),
    ]

    oss = _schedule(settings, OSS)
    assert oss[0][:3] == (1, 1, d(2026, 9, 2))
    assert len(oss) == 15 and (12, 1, TODAY, "21305") in oss  # 오늘이 정규 회차라 추가 없음

    for sched in (algo, sysprog, oss):  # (주차, 차수)는 과목 안에서 겹치지 않음
        assert len({(w, s) for w, s, _, _ in sched}) == len(sched)


def test_seed_on_regular_day_adds_nothing(tmp_path):
    settings = make_settings(tmp_path)
    result = seed(settings, today=dt.date(2026, 11, 17), with_embeddings=False)  # 화요일
    # 시스템프로그래밍·알고리즘은 정규 회차, 오픈소스만 오늘 회차 추가
    assert result["lecture_count"] == 30 + 15 + 16
    assert len(result["todays_lectures"]) == 3


def test_seed_is_repeatable(tmp_path):
    settings = make_settings(tmp_path)
    seed(settings, today=TODAY, with_embeddings=False)
    stale = settings.demo_photo_dir / "old_demo.png"
    stale.write_bytes(b"x")
    seed(settings, today=TODAY, with_embeddings=False)
    assert _counts(settings) == (4, 3, 8, 13, 62)  # 중복으로 쌓이지 않음
    assert not stale.exists()  # 이전 seed 의 사진도 정리


def test_seed_keeps_existing_student_photos(tmp_path):
    from PIL import Image

    settings = make_settings(tmp_path)
    seed(settings, today=TODAY, with_embeddings=False)
    mine = settings.student_photo_dir / "20181818.png"
    Image.fromarray(np.tile(np.arange(64, dtype=np.uint8)[:, None, None], (1, 64, 3))).save(mine)  # 바꿔 넣은 사진
    mine_bytes = mine.read_bytes()
    (settings.student_photo_dir / "20191919.png").unlink()  # 지운 사진

    result = seed(settings, today=TODAY)
    assert mine.read_bytes() == mine_bytes  # 덮어쓰지 않음
    assert "20181818" in result["kept_photos"] and "20191919" not in result["kept_photos"]
    assert (settings.student_photo_dir / "20191919.png").exists()  # 없던 학생만 패턴으로 다시 만듦
    assert len(list(settings.student_photo_dir.glob("*.png"))) == 8

    # 임베딩은 유지한 사진으로 계산된다
    eng = make_engine(settings.db_url)
    with make_session_factory(eng)() as db:
        expected = create_face_engine("dummy").detect_and_embed(np.asarray(Image.open(mine).convert("RGB")))[0][1]
        got = np.frombuffer(db.get(Student, "20181818").embedding, np.float32)
        assert np.allclose(got, expected)
    eng.dispose()


def test_seed_demo_photos_mark_attendance(tmp_path):
    settings = make_settings(tmp_path, max_upload_mb=5)
    lid = _today_lecture(seed(settings, today=TODAY), ALGO)
    with TestClient(create_app(settings)) as c:
        def up(name):
            path = settings.demo_photo_dir / name
            return c.post(f"/lectures/{lid}/photos", files={"photo": (name, path.read_bytes(), "image/png")}).json()

        assert up("algorithm_non_enrolled_1001_1002.png")["matched_count"] == 0  # 비수강생
        r = up("algorithm_1003_1004_1005.png")
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
    lid_a = _today_lecture(seed(settings, today=TODAY, with_embeddings=False), ALGO)

    # 128차원(이전 모델) 임베딩을 넣어 둔 상태 → 새 모델(64차원)에서는 비교 대상에서 빠짐
    eng = make_engine(settings.db_url)
    Session = make_session_factory(eng)
    with Session() as db:
        assert compute_all(db, settings, create_face_engine("dummy")).ok == 8
        db.commit()

    photo = (settings.demo_photo_dir / "algorithm_1003_1004_1005.png").read_bytes()
    with TestClient(create_app(settings)) as c:
        up = lambda: c.post(f"/lectures/{lid_a}/photos", files={"photo": ("a.png", photo, "image/png")}).json()
        assert up()["matched_count"] == 0

        with Session() as db:
            report = compute_all(db, settings, create_face_engine("dummy64"))
            db.commit()
        assert (report.ok, report.failed) == (8, [])
        assert up()["matched_count"] == 3

    # 증명사진이 없거나 얼굴이 1개가 아니면 NULL 로 바꾸고 실패 목록에 남김
    (settings.student_photo_dir / "20181818.png").unlink()
    from PIL import Image

    Image.fromarray(np.full((50, 50, 3), 9, np.uint8)).save(settings.student_photo_dir / "20191919.png")
    with Session() as db:
        report = compute_all(db, settings, create_face_engine("dummy64"))
        db.commit()
        assert sorted(sid for sid, _ in report.failed) == ["20181818", "20191919"]
        assert db.get(Student, "20181818").embedding is None
    eng.dispose()
