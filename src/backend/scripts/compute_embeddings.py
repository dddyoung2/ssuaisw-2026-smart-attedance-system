"""학생 증명사진에서 임베딩을 계산해 student.embedding 에 저장한다.

student.embedding 은 "증명사진에서 미리 추출해 넣어 둔 값"이라는 가정이다.
FR(얼굴 인식) 모델을 바꾸면 이전 임베딩과 비교할 수 없으므로 반드시 다시 실행한다.

    (저장소의 src 폴더에서, venv 활성화 후:  cd src)
    python -m backend.scripts.compute_embeddings              # 전체 다시 계산
    python -m backend.scripts.compute_embeddings --dry-run    # 저장하지 않고 결과만 확인
    python -m backend.scripts.compute_embeddings --engine dummy

증명사진 → 검출·정렬(CelebA-HQ 크롭) → 등록용 임베딩(engine.embed_anchor).
AdaFace 는 크롭 원본과 여러 크기로 줄인 뷰의 임베딩을 평균 낸다(engines/embedder.py).
증명사진에서 얼굴이 정확히 1개가 아니면 그 학생의 임베딩은 NULL 로 바꾸고 목록으로 알려준다
(NULL 인 학생은 매칭에서 빠진다 → 증명사진 확인 필요).
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import make_engine, make_session_factory
from ..face_engine import FaceEngine, create_face_engine
from ..services import storage, usaint
from ..services.recognition import to_blob

logger = logging.getLogger("compute_embeddings")


@dataclass
class Report:
    ok: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)


def compute_all(db: Session, settings: Settings, engine: FaceEngine) -> Report:
    """증명사진이 있는 모든 학생의 임베딩을 다시 계산한다. commit 은 호출자가 한다."""
    report = Report()
    for s in usaint.students_with_photo(db):
        try:
            image = storage.load_image(settings, s.photo_path)
            faces = engine.detect_and_embed_anchor(image)
            if len(faces) != 1:
                raise ValueError(f"얼굴 {len(faces)}개 검출")
            usaint.set_student_embedding(db, s.student_id, to_blob(faces[0][1]))
            report.ok += 1
        except Exception as e:  # noqa: BLE001 — 한 명 실패해도 계속
            usaint.set_student_embedding(db, s.student_id, None)
            report.failed.append((s.student_id, str(e)))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="학생 증명사진 임베딩 계산")
    parser.add_argument("--engine", help="사용할 FACE_ENGINE (기본: .env 값)")
    parser.add_argument("--dry-run", action="store_true", help="DB 에 저장하지 않음")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    engine = create_face_engine(args.engine or settings.face_engine)

    db_engine = make_engine(settings.db_url)
    try:
        with make_session_factory(db_engine)() as db:
            report = compute_all(db, settings, engine)
            if args.dry_run:
                db.rollback()
            else:
                db.commit()
    finally:
        db_engine.dispose()

    print(f"엔진: {engine.name} ({engine.dim}차원){'  [dry-run: 저장 안 함]' if args.dry_run else ''}")
    print(f"성공 {report.ok} / 실패 {len(report.failed)}")
    for sid, why in report.failed:
        print(f"  - {sid}: {why}  → 임베딩 NULL, 증명사진 확인 필요")
    return 0 if not report.failed else 1


if __name__ == "__main__":
    sys.exit(main())
