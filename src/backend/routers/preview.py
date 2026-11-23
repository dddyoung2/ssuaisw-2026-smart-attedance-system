"""카메라 미리보기: 프레임 한 장 → 탐지된 얼굴 박스 (검출만).

인식·출석 기록·DB 접근은 하지 않고, 사진은 저장하지 않는다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from ..config import Settings
from ..deps import get_engine, get_settings_dep
from ..face_engine import FaceEngine
from ..schemas import BoxOut, PreviewOut
from ..services import storage
from ..services.preview import detect_preview

router = APIRouter(prefix="/preview", tags=["preview"])


@router.post(
    "",
    response_model=PreviewOut,
    summary="카메라 미리보기: 축소 프레임에서 얼굴 검출만 (인식·출석 기록 없음, 사진 저장 안 함)",
)
def preview_faces(
    photo: UploadFile = File(..., description="카메라 프레임 (jpg/jpeg/png). 긴 변 960px 초과면 서버가 줄여서 검출"),
    settings: Settings = Depends(get_settings_dep),
    engine: FaceEngine = Depends(get_engine),
):
    image = storage.decode_image(storage.read_upload(photo, settings))
    h, w = image.shape[:2]
    boxes = detect_preview(image, engine)
    return PreviewOut(width=w, height=h, boxes=[BoxOut(x=x, y=y, w=bw, h=bh) for x, y, bw, bh in boxes])
