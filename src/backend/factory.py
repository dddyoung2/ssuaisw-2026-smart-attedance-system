"""FastAPI 앱 생성 함수. 테스트에서는 임시 설정으로 create_app(settings) 를 호출한다."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIR, Settings, get_settings
from .database import Base, make_engine, make_session_factory
from .face_engine import create_face_engine
from .routers import lectures, rooms

logger = logging.getLogger(__name__)



def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_dirs()

    db_engine = make_engine(settings.db_url)
    # 데모용: usaint DB 테이블이 없으면 생성(빈 DB). 예시 데이터는 scripts/seed_usaint.py 로 넣는다.
    # 실제 usaint 와 연동할 때는 테이블을 만들지 않고 읽기만 해야 한다.
    Base.metadata.create_all(db_engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        db_engine.dispose()

    app = FastAPI(
        title="osogi 얼굴인식 출석 API",
        version="0.1.0",
        description=(
            "강의실 단체 사진으로 수강생 출석을 기록하는 데모 백엔드 (usaint DB 연동 구조). "
            "**인증 없음 — 운영 전 인증 추가 필요.**"
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db_engine = db_engine
    app.state.SessionLocal = make_session_factory(db_engine)
    app.state.face_engine = create_face_engine(settings.face_engine)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    for r in (rooms.router, lectures.router):
        app.include_router(r)

    @app.get("/health", tags=["system"], summary="서버 상태")
    def health():
        fe = app.state.face_engine
        return {"status": "ok", "face_engine": fe.name, "embedding_dim": fe.dim}

    # 프론트엔드(src/frontend)를 /app 에서 함께 서빙 (Live Server 없이도 실행 가능)
    if FRONTEND_DIR.is_dir():
        app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

        @app.get("/", include_in_schema=False)
        def root():
            return RedirectResponse("/app/")

    logger.info(
        "DB=%s, FACE_ENGINE=%s, THRESHOLD=%s, CORS=%s",
        _mask_db_url(settings.db_url),
        settings.face_engine,
        settings.threshold,
        settings.cors_origin_list,
    )
    return app


def _mask_db_url(url: str) -> str:
    """로그에 DB 비밀번호가 찍히지 않도록 가린다."""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        creds, host = rest.rsplit("@", 1)
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return url
