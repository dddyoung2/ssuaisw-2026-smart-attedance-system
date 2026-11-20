"""강의실 목록 (카메라 화면의 강의실 선택).

camera 는 카메라 연결 정보(추후 연동). 화면에는 표시하지 않는다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import RoomOut
from ..services import usaint

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("", response_model=list[RoomOut], summary="강의실·카메라 목록")
def list_rooms(db: Session = Depends(get_db)):
    return [RoomOut(room_no=r.room_no, camera=r.camera) for r in usaint.list_rooms(db)]
