"""카메라 미리보기(POST /preview) 테스트: 검출만, 축소 후 좌표 복원, 출석·DB 영향 없음 (더미 엔진)."""
from __future__ import annotations

import numpy as np
import pytest

from backend.engines import fd_pipeline
from backend.face_engine import DummyDetector, create_face_engine
from backend.services.preview import PREVIEW_MAX_SIDE, detect_preview

from .conftest import SEEDS, blank_png, classroom, face_array, present_map, to_jpeg, to_png


def preview(client, data: bytes, filename="frame.jpg", ctype="image/jpeg"):
    return client.post("/preview", files={"photo": (filename, data, ctype)})


def test_preview_returns_boxes_in_sent_image_coords(client):
    r = preview(client, classroom(1, 2, 3), filename="f.png", ctype="image/png")
    assert r.status_code == 200
    body = r.json()
    assert (body["width"], body["height"]) == (360, 120)
    # 더미 검출기: 120px 칸마다 가운데 절반이 박스
    assert body["boxes"] == [{"x": 30 + 120 * i, "y": 30, "w": 60, "h": 60} for i in range(3)]


def test_preview_no_face(client):
    r = preview(client, blank_png(), filename="f.png", ctype="image/png")
    assert r.status_code == 200 and r.json()["boxes"] == []


def test_large_frame_is_downscaled_and_boxes_mapped_back():
    eng = create_face_engine("dummy")
    big = np.hstack([face_array(s, 600) for s in (1, 2, 3)])  # 1800x600 → 960x320 로 줄여 검출
    calls = []

    class Spy(DummyDetector):
        def detect(self, photo):
            calls.append(photo.shape)
            return super().detect(photo)

    eng.detector = Spy()
    boxes = detect_preview(big, eng)
    assert calls == [(320, PREVIEW_MAX_SIDE, 3)]  # 원본이 아닌 축소 이미지로 검출
    full = create_face_engine("dummy").detect(big)  # 원본 크기 검출과 좌표가 거의 같다
    assert len(boxes) == len(full) == 3
    assert np.abs(np.array(boxes) - np.array(full)).max() <= 2


def test_preview_does_not_touch_attendance_or_files(client, data, settings):
    def snapshot():
        return sorted(
            (p.relative_to(settings.data_dir), p.stat().st_size) for p in settings.data_dir.rglob("*") if p.is_file()
        )

    client.post(f"/lectures/{data.l1}/start")
    before = snapshot()
    for _ in range(3):
        assert preview(client, to_jpeg(face_array(SEEDS["S1"]))).status_code == 200
    assert snapshot() == before  # 사진 파일·DB 변화 없음
    assert not any(present_map(client, data.l1).values())  # 수강생 얼굴이어도 출석 안 됨


def test_preview_rejects_invalid_files(client):
    assert preview(client, to_png(face_array(1)), filename="a.gif", ctype="image/gif").status_code == 415
    assert preview(client, b"not an image", filename="a.png", ctype="image/png").status_code == 400
    big = b"\x89PNG" + b"0" * (1024 * 1024 + 10)  # 테스트 설정 MAX_UPLOAD_MB=1
    assert preview(client, big, filename="a.png", ctype="image/png").status_code == 413


def test_detect_boxes_matches_detect_and_align_boxes():
    det = DummyDetector()
    img = np.hstack([face_array(s) for s in (1, 2)])
    boxes, _ = fd_pipeline.detect_and_align(img, detector=det)
    assert fd_pipeline.detect_boxes(img, detector=det) == boxes
    assert all(type(v) is int for b in boxes for v in b)


def test_camera_page_has_preview_overlay(client):
    page = client.get("/app/camera.html").text
    js = client.get("/app/js/camera.js").text
    assert 'id="overlay"' in page and 'id="faceBadge"' in page
    assert "api('/preview'" in js and "탐지된 얼굴" in js
    assert f"const PREVIEW_MAX_SIDE = {PREVIEW_MAX_SIDE};" in js  # 서버와 같은 크기로 줄여 보낸다
