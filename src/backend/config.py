"""환경 설정.

값은 우선순위대로 (1) 환경변수 (2) 저장소 루트의 .env (3) 아래 기본값에서 읽는다.
경로는 모두 pathlib 기준이며, 상대경로는 저장소 루트 기준으로 해석한다.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent  # <저장소>/src/backend
SRC_DIR = BACKEND_DIR.parent  # <저장소>/src
PROJECT_DIR = SRC_DIR.parent  # <저장소> (.env 위치)
FRONTEND_DIR = SRC_DIR / "frontend"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # 데이터(DB 파일, 사진) 저장 위치. 상대경로면 저장소 루트 기준.
    data_dir: Path = BACKEND_DIR / "data"

    # 비워두면 data_dir/attendance.db 를 쓰는 SQLite.
    # 예) postgresql+psycopg://user:pass@localhost:5432/attendance
    # (.env.example 의 기존 이름 DB_URL 도 인식)
    database_url: str | None = Field(
        default=None, validation_alias=AliasChoices("DATABASE_URL", "DB_URL")
    )

    # 쉼표로 구분한 CORS 허용 주소
    cors_origins: str = "http://127.0.0.1:5500,http://localhost:5500"

    # 얼굴 엔진 이름 (face_engine.py 의 레지스트리 키)
    face_engine: str = "dummy"

    # 코사인 유사도가 이 값보다 "커야" 매칭
    threshold: float = 0.5

    # true면 이전 수업에서 교수가 확인(verified)한 얼굴 임베딩도 비교 대상에 포함
    use_verified_faces: bool = False

    # 업로드 파일 최대 크기(MB)
    max_upload_mb: float = 5.0

    log_level: str = "INFO"

    @field_validator("data_dir", mode="after")
    @classmethod
    def _resolve_data_dir(cls, v: Path) -> Path:
        return v if v.is_absolute() else (PROJECT_DIR / v).resolve()

    @field_validator("database_url", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        return v or None

    # ---- 파생 값 ----
    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'attendance.db').as_posix()}"

    @property
    def student_photo_dir(self) -> Path:
        return self.data_dir / "photos" / "students"

    @property
    def session_photo_dir(self) -> Path:
        return self.data_dir / "photos" / "sessions"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)

    def ensure_dirs(self) -> None:
        self.student_photo_dir.mkdir(parents=True, exist_ok=True)
        self.session_photo_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
