"""로컬 확인용: input-img 사진을 검출·정렬해 output-img에 저장하고 처리 시간을 출력한다.
실행(src 폴더에서): python -m backend.engines.retinaface.test.run_local"""
import time
from pathlib import Path

import cv2
import numpy as np

from backend.services.storage import decode_image
from backend.engines.pipeline import detect_and_align, get_detector

TEST_DIR = Path(__file__).resolve().parent
IN_DIR = TEST_DIR / "input-img"
OUT_DIR = TEST_DIR / "output-img"
EXTS = {".jpg", ".jpeg", ".png"}

from PIL import Image          # import 부분에 추가


def save_rgb(path, img):
    Image.fromarray(img).save(path)


def main(in_dir=IN_DIR, out_dir=OUT_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)
    photos = sorted(p for p in in_dir.iterdir() if p.suffix.lower() in EXTS)
    if not photos:
        print(f"사진이 없습니다: {in_dir}")
        return
    get_detector()                                   # 가중치 로드는 시간 측정에서 제외
    for path in photos:
        photo = decode_image(path.read_bytes())
        t = time.perf_counter()
        boxes, images = detect_and_align(photo)
        sec = time.perf_counter() - t

        vis = photo.copy()                           # 출력 1 확인: 원본 크기 그대로 박스와 순번 표시
        th = max(2, photo.shape[1] // 600)
        for i, (x, y, w, h) in enumerate(boxes):
            cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), th)
            cv2.putText(vis, str(i), (x, y - 6), cv2.FONT_HERSHEY_SIMPLEX, th * 0.45, (0, 255, 0), th)
        save_rgb(out_dir / f"{path.stem}_boxes.jpg", vis)
        for i, img in enumerate(images):             # 출력 2 확인: 정렬 이미지 그대로 저장
            save_rgb(out_dir / f"{path.stem}_face{i:02d}.png", img)

        sizes = [im.shape[0] for im in images]
        size_txt = f"{min(sizes)}/{int(np.median(sizes))}/{max(sizes)}" if sizes else "-"
        print(f"{path.name}: {photo.shape[1]}x{photo.shape[0]}, 얼굴 {len(boxes)}개, "
              f"정렬 크기 최소/중간/최대 {size_txt}px, {sec:.1f}초")


if __name__ == "__main__":
    main()