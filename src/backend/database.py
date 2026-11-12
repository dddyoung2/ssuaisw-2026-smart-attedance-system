"""DB 엔진/세션 생성.

엔진은 앱마다 만들어 app.state 에 보관한다(테스트에서 임시 DB를 쓰기 위함).
"""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    is_sqlite = url.startswith("sqlite")
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )
    if is_sqlite:
        # SQLite 는 기본적으로 외래키 제약(ON DELETE CASCADE 등)이 꺼져 있다.
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db(request: Request) -> Iterator[Session]:
    db: Session = request.app.state.SessionLocal()
    try:
        yield db
    finally:
        db.close()
