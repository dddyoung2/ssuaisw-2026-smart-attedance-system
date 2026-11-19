"""usaint DB 스키마가 설계와 정확히 일치하는지, PK·FK 제약이 동작하는지."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from backend.database import Base, make_engine, make_session_factory
from backend.models import Attendance, Course, Enrollment, Lecture, Room, Student

EXPECTED = {
    "room": ["room_no", "camera"],
    "class": ["course_code", "course_name"],
    "student": ["student_id", "name", "photo_path", "embedding"],
    "enrollment": ["course_code", "student_id"],
    "lecture": ["lecture_id", "course_code", "room_no", "week", "session_no", "date", "photo_path"],
    "attendance": ["lecture_id", "student_id", "present"],
}
EXPECTED_PK = {
    "room": ["room_no"],
    "class": ["course_code"],
    "student": ["student_id"],
    "enrollment": ["course_code", "student_id"],
    "lecture": ["lecture_id"],
    "attendance": ["lecture_id", "student_id"],
}
# (테이블, 컬럼) → (참조 테이블, 참조 컬럼, ON DELETE)
EXPECTED_FK = {
    ("enrollment", "course_code"): ("class", "course_code", "CASCADE"),
    ("enrollment", "student_id"): ("student", "student_id", "CASCADE"),
    ("lecture", "course_code"): ("class", "course_code", "CASCADE"),
    ("lecture", "room_no"): ("room", "room_no", None),
    ("attendance", "lecture_id"): ("lecture", "lecture_id", "CASCADE"),
    ("attendance", "student_id"): ("student", "student_id", "CASCADE"),
}


@pytest.fixture
def engine(tmp_path):
    eng = make_engine(f"sqlite:///{(tmp_path / 'usaint.db').as_posix()}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    with make_session_factory(engine)() as s:
        yield s


def test_tables_and_columns_match_design(engine):
    insp = inspect(engine)
    assert sorted(insp.get_table_names()) == sorted(EXPECTED)  # 사진 테이블 등 다른 테이블 없음
    for table, cols in EXPECTED.items():
        assert [c["name"] for c in insp.get_columns(table)] == cols, table
        assert insp.get_pk_constraint(table)["constrained_columns"] == EXPECTED_PK[table], table

    fks = {}
    for table in EXPECTED:
        for fk in insp.get_foreign_keys(table):
            (col,), (ref_col,) = fk["constrained_columns"], fk["referred_columns"]
            fks[(table, col)] = (fk["referred_table"], ref_col, fk["options"].get("ondelete"))
    assert fks == EXPECTED_FK


def test_column_types(engine):
    insp = inspect(engine)
    types = {(t, c["name"]): str(c["type"]).upper() for t in EXPECTED for c in insp.get_columns(t)}
    assert types[("student", "embedding")] == "BLOB"
    assert types[("lecture", "lecture_id")] == "INTEGER"
    assert types[("lecture", "date")] == "DATE"
    assert types[("lecture", "photo_path")].startswith("VARCHAR")
    assert types[("attendance", "present")] == "BOOLEAN"
    assert types[("room", "room_no")].startswith("VARCHAR")


def test_lecture_id_autoincrement_and_present_default_false(session):
    _base(session)
    lec = Lecture(course_code="C1", room_no="R1", week=1, session_no=1, date=dt.date(2026, 3, 2))
    session.add(lec)
    session.flush()
    assert isinstance(lec.lecture_id, int)
    assert lec.photo_path is None  # 수업 사진 경로는 비워 둘 수 있음
    # present 를 지정하지 않으면 false (DB 기본값)
    session.execute(
        text("INSERT INTO attendance (lecture_id, student_id) VALUES (:l, 'A')"), {"l": lec.lecture_id}
    )
    assert session.scalar(select(Attendance.present)) is False


def _base(s):
    s.add_all([Room(room_no="R1"), Course(course_code="C1", course_name="과목")])
    s.add_all([Student(student_id="A", name="가"), Student(student_id="B", name="나")])
    s.flush()


def test_duplicate_enrollment_rejected(session):
    _base(session)
    session.add(Enrollment(course_code="C1", student_id="A"))
    session.flush()
    session.add(Enrollment(course_code="C1", student_id="A"))
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize(
    "row",
    [
        Enrollment(course_code="C1", student_id="NOPE"),  # 없는 학번
        Enrollment(course_code="NOPE", student_id="A"),  # 없는 과목
    ],
    ids=["unknown-student", "unknown-course"],
)
def test_enrollment_fk_rejected(session, row):
    _base(session)
    session.add(row)
    with pytest.raises(IntegrityError):
        session.flush()


def test_lecture_and_attendance_fk_rejected(session):
    _base(session)
    session.add(Lecture(course_code="C1", room_no="NOPE", week=1, session_no=1, date=dt.date.today()))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    _base(session)
    session.add(Attendance(lecture_id=999, student_id="A"))
    with pytest.raises(IntegrityError):
        session.flush()


def _with_lecture(s):
    _base(s)
    s.add_all([Enrollment(course_code="C1", student_id="A"), Enrollment(course_code="C1", student_id="B")])
    lec = Lecture(course_code="C1", room_no="R1", week=1, session_no=1, date=dt.date(2026, 3, 2))
    s.add(lec)
    s.flush()
    s.add_all([Attendance(lecture_id=lec.lecture_id, student_id=x) for x in ("A", "B")])
    s.commit()
    return lec.lecture_id


def _count(s, model):
    return len(s.scalars(select(model)).all())


def test_delete_course_cascades(session):
    _with_lecture(session)
    session.execute(text("DELETE FROM class WHERE course_code = 'C1'"))
    session.commit()
    assert (_count(session, Enrollment), _count(session, Lecture), _count(session, Attendance)) == (0, 0, 0)
    assert _count(session, Student) == 2  # 학생은 남음


def test_delete_student_cascades(session):
    _with_lecture(session)
    session.execute(text("DELETE FROM student WHERE student_id = 'A'"))
    session.commit()
    assert [e.student_id for e in session.scalars(select(Enrollment))] == ["B"]
    assert [a.student_id for a in session.scalars(select(Attendance))] == ["B"]


def test_delete_lecture_cascades_attendance(session):
    lid = _with_lecture(session)
    session.execute(text("DELETE FROM lecture WHERE lecture_id = :l"), {"l": lid})
    session.commit()
    assert _count(session, Attendance) == 0


def test_room_with_lectures_cannot_be_deleted(session):
    _with_lecture(session)
    with pytest.raises(IntegrityError):
        session.execute(text("DELETE FROM room WHERE room_no = 'R1'"))
        session.commit()


def test_course_students_shortcut(session):
    _with_lecture(session)
    course = session.get(Course, "C1")
    assert [s.student_id for s in course.students] == ["A", "B"]
