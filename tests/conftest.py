"""테스트 공통: 매 테스트마다 임시 폴더에 DB/사진을 만들고 더미 엔진을 쓴다.
사용자의 .env 나 backend/data 는 건드리지 않는다."""
from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.config import Settings
from backend.factory import create_app


def make_settings(tmp_path, **overrides) -> Settings:
    values = dict(
        data_dir=tmp_path / "data",
        database_url=None,
        face_engine="dummy",
        threshold=0.5,
        use_verified_faces=False,
        max_upload_mb=1,
        cors_origins="http://127.0.0.1:5500",
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


# ---------- 테스트용 이미지 ----------
def face_array(seed: int, size: int = 120) -> np.ndarray:
    """시드별로 서로 다른 '얼굴' 패턴(부드러운 랜덤 무늬). 서로 다른 시드끼리는 유사도가 낮다."""
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
    """여러 '얼굴'을 가로로 이어 붙인 강의실 사진(더미 검출기는 칸마다 얼굴 1개로 인식)."""
    if len(seeds) == 1:
        return to_png(face_array(seeds[0]))
    return to_png(np.hstack([face_array(s) for s in seeds]))


def blank_png(size: int = 120) -> bytes:
    return to_png(np.full((size, size, 3), 200, dtype=np.uint8))


def register(client, student_id: str, name: str, seed: int, *, filename="photo.png"):
    return client.post(
        "/students",
        data={"student_id": student_id, "name": name},
        files={"photo": (filename, to_png(face_array(seed)), "image/png")},
    )


def upload(client, session_id: int, data: bytes, filename="class.png", ctype="image/png"):
    return client.post(
        f"/sessions/{session_id}/photos", files={"photo": (filename, data, ctype)}
    )
