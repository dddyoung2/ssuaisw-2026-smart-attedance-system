"""테스트 공통: 매 테스트마다 임시 폴더에 usaint DB 를 만들고 더미 엔진을 쓴다.
사용자의 .env 나 src/backend/data 는 건드리지 않는다(실제 데이터 미사용)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from io import BytesIO

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.config import Settings
from backend.factory import create_app
from backend.models import Course, Enrollment, Lecture, Room, Student
from backend.services.recognition import to_blob

D0 = dt.date(2026, 11, 18)  # 테스트 기준 날짜 (고정)


def make_settings(tmp_path, **overrides) -> Settings:
    values = dict(
        data_dir=tmp_path / "data",
        database_url=None,
        face_engine="dummy",
        threshold=0.5,
        max_upload_mb=1,
        cors_origins="http://127.0.0.1:5500",
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db(app):
    with app.state.SessionLocal() as s:
        yield s


# ---------- 테스트용 이미지 ----------
def face_array(seed: int, size: int = 120) -> np.ndarray:
    """시드별로 다른 '얼굴' 대용 패턴. 서로 다른 시드끼리는 유사도가 낮다."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, size=(32, 32, 3), dtype=np.uint8)
    return np.asarray(Image.fromarray(small).resize((size, size), Image.BICUBIC))


def to_png(arr: np.ndarray) -> bytes:
    buf = BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def to_jpeg(arr: np.ndarray) -> bytes:
    buf = BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def classroom(*seeds: int) -> bytes:
    """얼굴 패턴을 가로로 이어 붙인 단체 사진 (더미 검출기는 칸마다 얼굴 1개로 인식)."""
    if len(seeds) == 1:
        return to_png(face_array(seeds[0]))
    return to_png(np.hstack([face_array(s) for s in seeds]))


def blank_png(size: int = 120) -> bytes:
    return to_png(np.full((size, size, 3), 200, dtype=np.uint8))


def upload(client, lecture_id: int, data: bytes, filename="class.png", ctype="image/png"):
    return client.post(f"/lectures/{lecture_id}/photos", files={"photo": (filename, data, ctype)})


# ---------- 예시 usaint 데이터 ----------
# 학번 → 얼굴 패턴 시드
SEEDS = {"S1": 1, "S2": 2, "S3": 3, "S4": 4, "S5": 5}
STRANGER = 99  # 아무도 아닌 얼굴


@dataclass
class Data:
    """fixture 가 넣은 예시 데이터의 회차 번호."""

    l1: int  # 가반, 21303, D0
    l2: int  # 나반, 21303, D0   → 21303 @ D0 회차 2개
    l3: int  # 가반, 21303, D0+7
    l4: int  # 나반, 11101, D0
    l5: int  # 가반, 21303, D0+2 (10주차 2차시, 마지막에 추가 → id 순서와 날짜 순서가 다름)


@pytest.fixture
def data(app, db) -> Data:
    """
    class C1(가반): S1, S2, S3, S6(임베딩 없음)    class C2(나반): S3, S4
    class C0(자료구조): 수강생·회차 없음 (코드는 가장 앞, 과목명은 가장 뒤)
    S5 는 어떤 과목도 수강하지 않음
    """
    engine = app.state.face_engine

    def emb(seed: int) -> bytes:
        (_, vec), = engine.detect_and_embed(face_array(seed))
        return to_blob(vec)

    db.add_all([Room(room_no="21303", camera="cam-21303"), Room(room_no="11101", camera=None)])
    db.add_all(
        [
            Course(course_code="C1", course_name="알고리즘(가반)"),
            Course(course_code="C2", course_name="알고리즘(나반)"),
            Course(course_code="C0", course_name="자료구조"),
        ]
    )
    db.add_all(
        [Student(student_id=sid, name=f"학생{sid}", embedding=emb(seed)) for sid, seed in SEEDS.items()]
        + [Student(student_id="S6", name="학생S6", embedding=None)]
    )
    db.flush()
    db.add_all(
        Enrollment(course_code=c, student_id=s)
        for c, s in [("C1", "S1"), ("C1", "S2"), ("C1", "S3"), ("C1", "S6"), ("C2", "S3"), ("C2", "S4")]
    )
    lectures = [
        Lecture(course_code="C1", room_no="21303", week=10, session_no=1, date=D0),
        Lecture(course_code="C2", room_no="21303", week=10, session_no=1, date=D0),
        Lecture(course_code="C1", room_no="21303", week=11, session_no=1, date=D0 + dt.timedelta(days=7)),
        Lecture(course_code="C2", room_no="11101", week=10, session_no=2, date=D0),
        Lecture(course_code="C1", room_no="21303", week=10, session_no=2, date=D0 + dt.timedelta(days=2)),
    ]
    db.add_all(lectures)
    db.commit()
    return Data(*(l.lecture_id for l in lectures))


def present_map(client, lecture_id: int) -> dict[str, bool]:
    body = client.get(f"/lectures/{lecture_id}/attendance").json()
    return {s["student_id"]: s["present"] for s in body["students"]}
