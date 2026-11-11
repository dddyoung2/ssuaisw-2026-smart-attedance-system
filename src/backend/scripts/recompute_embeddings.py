"""저장된 임베딩을 현재 FACE_ENGINE 으로 다시 계산한다.

얼굴 모델(또는 임베딩 차원)을 바꾼 뒤 반드시 실행해야 한다.
이전 모델의 임베딩과 새 모델의 임베딩은 서로 비교할 수 없기 때문이다.

    (저장소의 src 폴더에서, venv 활성화 후:  cd src)
    python -m backend.scripts.recompute_embeddings              # 학생 + verified 얼굴
    python -m backend.scripts.recompute_embeddings --dry-run    # 저장하지 않고 결과만 확인
    python -m backend.scripts.recompute_embeddings --all-detections
    python -m backend.scripts.recompute_embeddings --engine insightface

- 학생: 증명사진에서 얼굴을 다시 검출해 임베딩. 얼굴이 정확히 1개가 아니면
  임베딩을 NULL 로 바꾸고(비교 대상에서 빠짐) 목록으로 알려준다 → 사진 재등록 필요.
- 검출(detections): 저장된 bbox 로 강의실 사진을 잘라 임베딩만 다시 계산한다.
  기본은 verified=true 인 것만(USE_VERIFIED_FACES 비교 대상). --all-detections 면 전부.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field

from sqlalchemy import select

from ..config import Settings, get_settings
from ..database import make_engine, make_session_factory
from ..face_engine import FaceEngine, clip_bbox, create_face_engine, crop
from ..models import Detection, Student
from ..services import storage
from ..services.recognition import to_blob

logger = logging.getLogger("recompute")


@dataclass
class Report:
    students_ok: int = 0
    students_failed: list[tuple[str, str]] = field(default_factory=list)
    detections_ok: int = 0
    detections_failed: list[tuple[int, str]] = field(default_factory=list)


def recompute(
    settings: Settings,
    engine: FaceEngine,
    *,
    all_detections: bool = False,
    dry_run: bool = False,
) -> Report:
    report = Report()
    db_engine = make_engine(settings.db_url)
    SessionLocal = make_session_factory(db_engine)
    try:
        with SessionLocal() as db:
            for s in db.scalars(select(Student).order_by(Student.student_id)):
                try:
                    image = storage.load_image(settings, s.photo_path)
                    boxes = engine.detect(image)
                    if len(boxes) != 1:
                        raise ValueError(f"얼굴 {len(boxes)}개 검출")
                    s.embedding = to_blob(engine.embed(crop(image, boxes[0])))
                    report.students_ok += 1
                except Exception as e:  # noqa: BLE001 — 한 명 실패해도 계속
                    s.embedding = None
                    report.students_failed.append((s.student_id, str(e)))

            q = select(Detection)
            if not all_detections:
                q = q.where(Detection.verified.is_(True))
            for d in db.scalars(q):
                try:
                    image = storage.load_image(settings, d.photo.photo_path)
                    box = clip_bbox(d.bbox, image.shape[1], image.shape[0])
                    if box is None:
                        raise ValueError("bbox 가 이미지 밖에 있음")
                    d.embedding = to_blob(engine.embed(crop(image, box)))
                    report.detections_ok += 1
                except Exception as e:  # noqa: BLE001
                    report.detections_failed.append((d.detection_id, str(e)))

            if dry_run:
                db.rollback()
            else:
                db.commit()
    finally:
        db_engine.dispose()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="임베딩 재계산")
    parser.add_argument("--engine", help="사용할 FACE_ENGINE (기본: .env 값)")
    parser.add_argument("--all-detections", action="store_true", help="verified 가 아닌 검출도 재계산")
    parser.add_argument("--dry-run", action="store_true", help="DB 에 저장하지 않음")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    engine = create_face_engine(args.engine or settings.face_engine)

    r = recompute(settings, engine, all_detections=args.all_detections, dry_run=args.dry_run)
    print(f"엔진: {engine.name} ({engine.dim}차원){'  [dry-run: 저장 안 함]' if args.dry_run else ''}")
    print(f"학생   성공 {r.students_ok} / 실패 {len(r.students_failed)}")
    for sid, why in r.students_failed:
        print(f"  - {sid}: {why}  → 임베딩 NULL, 증명사진 재등록 필요")
    print(f"검출   성공 {r.detections_ok} / 실패 {len(r.detections_failed)}")
    for did, why in r.detections_failed:
        print(f"  - detection {did}: {why}")
    return 0 if not (r.students_failed or r.detections_failed) else 1


if __name__ == "__main__":
    sys.exit(main())
