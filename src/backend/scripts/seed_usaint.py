"""데모용 usaint DB(usaint.db)에 예시 데이터를 넣는다.

실제 usaint(학사 포털)에는 학생·과목·강의실·회차·수강 정보가 이미 있다는 가정이다.
이 스크립트는 그 DB 를 흉내 내기 위해 실행할 때마다 usaint.db 를 새로 만든다(기존 데이터 삭제).
여러 번 실행해도 데이터가 중복으로 쌓이지 않는다.

    (저장소의 src 폴더에서, venv 활성화 후:  cd src)
    python -m backend.scripts.seed_usaint

만드는 것 (DATA_DIR 아래, git 제외)
- usaint.db                  : 6개 테이블 + 예시 데이터, 학생 임베딩까지 계산
- photos/students/<학번>.png : 예시 증명사진. 실제 얼굴이 아닌 합성 패턴(개인정보 보호)
                               이미 그 학번의 사진이 있으면 지우거나 덮어쓰지 않고 그대로 쓴다
                               (실제 얼굴 사진을 넣어 두면 seed 를 다시 돌려도 유지되고 임베딩도 그 사진으로 계산).
                               패턴으로 되돌리려면 그 파일을 지우고 다시 실행한다.
- demo/*.png                 : 데모용 단체 사진. /docs 의 POST /lectures/{id}/photos 로 올려
                               더미 엔진에서도 출석이 잡히는 흐름을 볼 수 있다.

회차: 과목마다 2026-09-01 이 있는 주를 1주차로 15주차까지, 정해진 요일에 만든다.
(시스템프로그래밍은 주 2회 화·목, 나머지는 주 1회)
seed 를 실행한 날(오늘)에 정규 회차가 없는 과목은 오늘 날짜의 회차를 하나 더 만들어서,
데모 당일 과목 홈에서 오늘 회차가 강조되고 바로 촬영할 수 있게 한다.
session_no(차수)는 같은 주 안에서 날짜순으로 1, 2, 3… 이다.
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

SEMESTER_START = dt.date(2026, 9, 1)  # 이 날짜가 있는 주가 1주차
WEEKS = 15

MON, TUE, WED, THU, FRI = range(5)

# (room_no, camera). camera 는 카메라 연결 정보 자리(추후 연동). 화면에는 표시하지 않는다.
ROOMS = [
    ("11101", "cam-11101"),
    ("21303", "cam-21303"),
    ("21304", "cam-21304"),
    ("21305", "cam-21305"),
]


@dataclass(frozen=True)
class CourseSeed:
    code: str
    name: str
    room_no: str
    weekdays: tuple[int, ...]  # 정규 수업 요일 (월=0)


COURSES = [
    CourseSeed("2150165801", "시스템프로그래밍", "21303", (TUE, THU)),  # 주 2회
    CourseSeed("2150163303", "알고리즘", "21304", (TUE,)),
    CourseSeed("2150061301", "오픈소스기반기초설계", "21305", (WED,)),
]

# (학번, 이름, 패턴 시드)
STUDENTS = [
    ("20181818", "김도영", 1),
    ("20191919", "이예찬", 2),
    ("20202020", "이승호", 3),
    ("20231004", "최지우", 4),
    ("20231005", "정하준", 5),
    ("20231006", "강수아", 6),
    ("20231007", "조은우", 7),
    ("20231008", "윤지아", 8),
]

# 과목마다 4~5명, 여러 과목을 함께 듣는 학생 포함
ENROLLMENTS = {
    "2150165801": ["20181818", "20191919", "20202020", "20231004", "20231005"],
    "2150163303": ["20202020", "20231004", "20231005", "20231006"],
    "2150061301": ["20181818", "20231006", "20231007", "20231008"],
}

# 데모 단체 사진: (파일 이름, 사진에 들어갈 학번들)
DEMO_PHOTOS = [
    ("sysprog_1001_1002_1003.png", ["20181818", "20191919", "20202020"]),
    ("algorithm_1003_1004_1005.png", ["20202020", "20231004", "20231005"]),
    ("algorithm_non_enrolled_1001_1002.png", ["20181818", "20191919"]),
    ("opensource_1007_1008.png", ["20231007", "20231008"]),
]

PHOTO_SIZE = 200


def face_pattern(seed: int, size: int = PHOTO_SIZE) -> np.ndarray:
    """시드별로 다른 '얼굴' 대용 패턴(부드러운 랜덤 무늬, RGB uint8)."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, size=(32, 32, 3), dtype=np.uint8)
    return np.asarray(Image.fromarray(small).resize((size, size), Image.BICUBIC))


def _week1_monday() -> dt.date:
    return SEMESTER_START - dt.timedelta(days=SEMESTER_START.weekday())


def week_of(day: dt.date) -> int:
    """날짜가 몇 주차인지. 학기 시작 전 날짜는 1주차로 본다."""
    return max(1, (day - _week1_monday()).days // 7 + 1)


def lecture_schedule(course: CourseSeed, today: dt.date) -> list[tuple[int, int, dt.date]]:
    """과목의 회차 목록 [(week, session_no, date), ...] (날짜순).

    정규 회차(1~15주차, 정해진 요일) + 오늘 정규 회차가 없으면 오늘 회차 1개.
    session_no 는 같은 주 안에서 날짜순 번호.
    """
    monday = _week1_monday()
    dates = {
        monday + dt.timedelta(weeks=w, days=wd) for w in range(WEEKS) for wd in course.weekdays
    }
    dates.add(today)  # 이미 있으면 그대로

    out: list[tuple[int, int, dt.date]] = []
    per_week: dict[int, int] = {}
    for d in sorted(dates):
        w = week_of(d)
        per_week[w] = per_week.get(w, 0) + 1
        out.append((w, per_week[w], d))
    return out


def _reset_png_dir(path) -> None:
    """seed 가 만드는 폴더의 이전 사진을 지운다(예전 seed 의 파일이 남지 않도록)."""
    path.mkdir(parents=True, exist_ok=True)
    for f in path.glob("*.png"):
        f.unlink()


def seed(settings: Settings, today: dt.date | None = None, *, with_embeddings: bool = True) -> dict:
    """usaint.db 를 새로 만들고 예시 데이터를 넣는다. 오늘 회차 정보를 돌려준다."""
    today = today or dt.date.today()
    settings.ensure_dirs()
    settings.student_photo_dir.mkdir(parents=True, exist_ok=True)
    _reset_png_dir(settings.demo_photo_dir)

    # 예시 증명사진: 사진이 없는 학생만 합성 패턴으로 만든다 (이미 있는 사진은 그대로 둠)
    patterns = {sid: face_pattern(s) for sid, _, s in STUDENTS}
    kept_photos = []
    for sid, arr in patterns.items():
        path = settings.student_photo_dir / f"{sid}.png"
        if path.exists():
            kept_photos.append(sid)
            continue
        Image.fromarray(arr).save(path)
    # 데모 단체 사진 (합성 패턴, 매번 새로 만듦)
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
            db.add_all(Course(course_code=c.code, course_name=c.name) for c in COURSES)
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
                Lecture(course_code=c.code, room_no=c.room_no, week=w, session_no=s, date=d)
                for c in COURSES
                for w, s, d in lecture_schedule(c, today)
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

    return {
        "today": today,
        "lecture_count": len(lectures),
        "todays_lectures": todays,
        "embedding_report": report,
        "kept_photos": kept_photos,  # 이미 있어서 그대로 둔 증명사진의 학번
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="데모용 usaint DB 예시 데이터 생성 (기존 데이터 삭제)")
    parser.add_argument("--no-embeddings", action="store_true", help="임베딩 계산을 건너뜀")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    result = seed(settings, with_embeddings=not args.no_embeddings)

    print(f"usaint DB: {settings.db_url}")
    print(
        f"강의실 {len(ROOMS)} · 과목 {len(COURSES)} · 학생 {len(STUDENTS)} · 회차 {result['lecture_count']}"
    )
    print(f"오늘({result['today']}) 회차:")
    names = {c.code: (c.name, c.room_no) for c in COURSES}
    for lid, code, week, sess in result["todays_lectures"]:
        name, room = names[code]
        print(f"  lecture_id={lid}  {name}  {week}-{sess}  {room}")
    kept = result["kept_photos"]
    if kept:
        print(f"기존 증명사진 유지 {len(kept)}명: {', '.join(kept)}")
    r = result["embedding_report"]
    if r is not None:
        print(f"임베딩: 성공 {r.ok} / 실패 {len(r.failed)}")
    print(f"데모 단체 사진: {settings.demo_photo_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
