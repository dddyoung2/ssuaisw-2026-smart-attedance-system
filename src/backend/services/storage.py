"""업로드 검증과 이미지 파일 저장/삭제.

DB 에는 data_dir 기준 상대경로(posix)만 저장하므로 OS 가 바뀌어도 그대로 쓸 수 있다.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import numpy as np
from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from ..config import Settings

logger = logging.getLogger(__name__)

ALLOWED_EXT = {".jpg", ".jpeg", ".png"}
_CONTENT_TYPE_EXT = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png"}
_FORMAT_EXT = {"JPEG": ".jpg", "PNG": ".png"}
MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def read_upload(upload: UploadFile, settings: Settings) -> tuple[bytes, str]:
    """확장자·크기·실제 이미지 형식을 검사하고 (bytes, 저장용 확장자)를 돌려준다."""
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
    if fmt not in _FORMAT_EXT:
        raise HTTPException(415, "jpg, jpeg, png 파일만 업로드할 수 있습니다.")
    return data, _FORMAT_EXT[fmt]


def decode_image(data: bytes) -> np.ndarray:
    """bytes → RGB uint8 (H, W, 3). EXIF 회전 정보를 반영한다."""
    with Image.open(BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im)
        return np.asarray(im.convert("RGB"), dtype=np.uint8)


def load_image(settings: Settings, rel_path: str) -> np.ndarray:
    return decode_image(abs_path(settings, rel_path).read_bytes())


def abs_path(settings: Settings, rel_path: str) -> Path:
    path = (settings.data_dir / rel_path).resolve()
    if not path.is_relative_to(settings.data_dir.resolve()):
        raise ValueError("data_dir 밖의 경로입니다.")
    return path


def _save(settings: Settings, rel_path: Path, data: bytes) -> str:
    target = settings.data_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(target)
    return rel_path.as_posix()


def save_student_photo(settings: Settings, student_id: str, data: bytes, ext: str) -> str:
    name = f"{student_id}_{uuid.uuid4().hex[:8]}{ext}"
    return _save(settings, Path("photos", "students", name), data)


def save_session_photo(settings: Settings, session_id: int, data: bytes, ext: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    name = f"{stamp}_{uuid.uuid4().hex[:8]}{ext}"
    return _save(settings, Path("photos", "sessions", str(session_id), name), data)


def delete_file(settings: Settings, rel_path: str | None) -> None:
    if not rel_path:
        return
    try:
        abs_path(settings, rel_path).unlink(missing_ok=True)
    except OSError as e:
        logger.warning("파일 삭제 실패 %s: %s", rel_path, e)


def media_type_of(rel_path: str) -> str:
    return MEDIA_TYPES.get(Path(rel_path).suffix.lower(), "application/octet-stream")
