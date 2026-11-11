"""라우터에서 쓰는 공통 의존성."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import Settings
from .database import get_db
from .face_engine import FaceEngine
from .models import ClassSession


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_engine(request: Request) -> FaceEngine:
    return request.app.state.face_engine


def get_session_or_404(session_id: int, db: Session = Depends(get_db)) -> ClassSession:
    sess = db.get(ClassSession, session_id)
    if sess is None:
        raise HTTPException(404, f"수업 회차 {session_id}를 찾을 수 없습니다.")
    return sess
