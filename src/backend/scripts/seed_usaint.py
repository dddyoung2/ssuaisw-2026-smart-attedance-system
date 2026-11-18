"""데모용 usaint DB(usaint.db)에 예시 데이터를 넣는다.

실제 usaint(학사 포털)에는 학생·과목·강의실·회차·수강 정보가 이미 있다는 가정이다.
이 스크립트는 그 DB 를 흉내 내기 위해 실행할 때마다 usaint.db 를 새로 만든다(기존 데이터 삭제).

    (저장소의 src 폴더에서, venv 활성화 후:  cd src)
    python -m backend.scripts.seed_usaint

만드는 것 (DATA_DIR 아래, git 제외)
- usaint.db                  : 6개 테이블 + 예시 데이터, 학생 임베딩까지 계산
- photos/students/<학번>.png : 예시 증명사진. 실제 얼굴이 아닌 합성 패턴(개인정보 보호)
- demo/*.png                 : 데모용 단체 사진. /docs 의 POST /lectures/{id}/photos 로 올려
                               더미 엔진에서도 출석이 잡히는 흐름을 볼 수 있다.

회차 날짜는 실행한 날(오늘)을 기준으로 만든다. 오늘 21303 강의실에는
알고리즘 가반·나반 두 회차가 있어서, 화면에서 회차를 고르는 경우를 확인할 수 있다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from dataclasses import dataclass

import numpy as np
from PIL import Image

from ..config import Settings, get_settings
from ..database import Base, make_engine, make_session_factory
from ..face_engine import create_face_engine
from ..models import Course, Enrollment, Lecture, Room, Student
from .compute_embeddings import compute_all

ROOMS = [("21303", "정보과학관 21303 전면 카메라 (cam-21303-1)")]

COURSES = [
    ("2150163301", "알고리즘(가반)"),
    ("2150163302", "알고리즘(나반)"),
]

# (학번, 이름, 패턴 시드)
STUDENTS = [
    ("20231001", "김민준", 1),
    ("20231002", "이서연", 2),
    ("20231003", "박도윤", 3),
    ("20231004", "최지우", 4),
    ("20231005", "정하준", 5),
    ("20231006", "강수아", 6),
]

# 가반 4명, 나반 3명 (20231004 는 두 분반 모두 수강하는 예시)
ENROLLMENTS = {
    "2150163301": ["20231001", "20231002", "20231003", "20231004"],
    "2150163302": ["20231004", "20231005", "20231006"],
}

THIS_WEEK = 10


@dataclass(frozen=True)
class LectureSeed:
    course_code: str
    week: int
    session_no: int
    days_from_today: int


LECTURES = [
    # 지난주
    LectureSeed("2150163301", THIS_WEEK - 1, 1, -7),
    LectureSeed("2150163302", THIS_WEEK - 1, 1, -7),
    # 오늘: 같은 강의실·같은 날에 두 분반 → 화면에서 회차 선택
    LectureSeed("2150163301", THIS_WEEK, 1, 0),
    LectureSeed("2150163302", THIS_WEEK, 1, 0),
    # 이번 주 두 번째 수업
    LectureSeed("2150163301", THIS_WEEK, 2, 2),
    LectureSeed("2150163302", THIS_WEEK, 2, 2),
]

# 데모 단체 사진: (파일 이름, 사진에 들어갈 학번들)
DEMO_PHOTOS = [
    ("lecture_A_students_1001_1002_1003.png", ["20231001", "20231002", "20231003"]),
    ("lecture_B_students_1005_1006.png", ["20231005", "20231006"]),
    ("lecture_A_non_enrolled_1005.png", ["20231005"]),
]

PHOTO_SIZE = 200


def face_pattern(seed: int, size: int = PHOTO_SIZE) -> np.ndarray:
    """시드별로 다른 '얼굴' 대용 패턴(부드러운 랜덤 무늬, RGB uint8)."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, size=(32, 32, 3), dtype=np.uint8)
    return np.asarray(Image.fromarray(small).resize((size, size), Image.BICUBIC))


def seed(settings: Settings, today: dt.date | None = None, *, with_embeddings: bool = True) -> dict:
    """usaint.db 를 새로 만들고 예시 데이터를 넣는다. 만든 회차 정보를 돌려준다."""
    today = today or dt.date.today()
    settings.ensure_dirs()
    settings.student_photo_dir.mkdir(parents=True, exist_ok=True)
    settings.demo_photo_dir.mkdir(parents=True, exist_ok=True)

    # 예시 증명사진 / 데모 단체 사진 (합성 패턴)
    patterns = {sid: face_pattern(s) for sid, _, s in STUDENTS}
    for sid, arr in patterns.items():
        Image.fromarray(arr).save(settings.student_photo_dir / f"{sid}.png")
    for filename, ids in DEMO_PHOTOS:
        Image.fromarray(np.hstack([patterns[i] for i in ids])).save(
            settings.demo_photo_dir / filename
        )

    db_engine = make_engine(settings.db_url)
    try:
        Base.metadata.drop_all(db_engine)
        Base.metadata.create_all(db_engine)
        with make_session_factory(db_engine)() as db:
            db.add_all(Room(room_no=r, camera=c) for r, c in ROOMS)
            db.add_all(Course(course_code=c, course_name=n) for c, n in COURSES)
            db.add_all(
                Student(student_id=sid, name=name, photo_path=f"photos/students/{sid}.png")
                for sid, name, _ in STUDENTS
            )
            db.flush()
            db.add_all(
                Enrollment(course_code=code, student_id=sid)
                for code, ids in ENROLLMENTS.items()
                for sid in ids
            )
            lectures = [
                Lecture(
                    course_code=l.course_code,
                    room_no=ROOMS[0][0],
                    week=l.week,
                    session_no=l.session_no,
                    date=today + dt.timedelta(days=l.days_from_today),
                )
                for l in LECTURES
            ]
            db.add_all(lectures)
            db.flush()

            report = None
            if with_embeddings:
                report = compute_all(db, settings, create_face_engine(settings.face_engine))
            db.commit()

            todays = [
                (l.lecture_id, l.course_code, l.week, l.session_no)
                for l in lectures
                if l.date == today
            ]
    finally:
        db_engine.dispose()

    return {"today": today, "todays_lectures": todays, "embedding_report": report}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="데모용 usaint DB 예시 데이터 생성 (기존 데이터 삭제)")
    parser.add_argument("--no-embeddings", action="store_true", help="임베딩 계산을 건너뜀")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    result = seed(settings, with_embeddings=not args.no_embeddings)

    print(f"usaint DB: {settings.db_url}")
    print(f"강의실 {len(ROOMS)} · 과목 {len(COURSES)} · 학생 {len(STUDENTS)} · 회차 {len(LECTURES)}")
    print(f"오늘({result['today']}) 21303 회차:")
    names = dict(COURSES)
    for lid, code, week, sess in result["todays_lectures"]:
        print(f"  lecture_id={lid}  {names[code]}  {week}주차 {sess}차시")
    r = result["embedding_report"]
    if r is not None:
        print(f"임베딩: 성공 {r.ok} / 실패 {len(r.failed)}")
    print(f"데모 단체 사진: {settings.demo_photo_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
