"""업로드 검증과 이미지 디코딩.

업로드된 강의실 사진은 메모리에서만 다룬다(파일로 저장하지 않음).
디스크에서 읽는 것은 학생 증명사진(student.photo_path, data_dir 기준 상대경로)뿐이다.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from ..config import Settings

ALLOWED_EXT = {".jpg", ".jpeg", ".png"}
_CONTENT_TYPE_EXT = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png"}
_ALLOWED_FORMATS = {"JPEG", "PNG"}


def read_upload(upload: UploadFile, settings: Settings) -> bytes:
    """확장자·크기·실제 이미지 형식을 검사하고 파일 내용(bytes)을 돌려준다."""
    ext = Path(upload.filename or "").suffix.lower()
    if not ext:
        ext = _CONTENT_TYPE_EXT.get((upload.content_type or "").lower(), "")
    if ext not in ALLOWED_EXT:
        raise HTTPException(415, "jpg, jpeg, png 파일만 업로드할 수 있습니다.")

    limit = settings.max_upload_bytes
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"파일이 너무 큽니다. 최대 {settings.max_upload_mb:g}MB")
    if not data:
        raise HTTPException(400, "빈 파일입니다.")

    try:
        with Image.open(BytesIO(data)) as im:
            fmt = im.format
            im.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise HTTPException(400, "이미지 파일을 읽을 수 없습니다.") from None
    if fmt not in _ALLOWED_FORMATS:
        raise HTTPException(415, "jpg, jpeg, png 파일만 업로드할 수 있습니다.")
    return data


def decode_image(data: bytes) -> np.ndarray:
    """bytes → RGB uint8 (H, W, 3). EXIF 회전 정보를 반영한다. 메모리에서만 처리."""
    with Image.open(BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im)
        return np.asarray(im.convert("RGB"), dtype=np.uint8)


def abs_path(settings: Settings, rel_path: str) -> Path:
    path = (settings.data_dir / rel_path).resolve()
    if not path.is_relative_to(settings.data_dir.resolve()):
        raise ValueError("data_dir 밖의 경로입니다.")
    return path


def load_image(settings: Settings, rel_path: str) -> np.ndarray:
    """학생 증명사진 읽기 (data_dir 기준 상대경로)."""
    return decode_image(abs_path(settings, rel_path).read_bytes())
