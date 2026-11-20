"""얼굴 검출 → 인식 인계: 출력 1(검출 박스 좌표 리스트), 출력 2(정렬 얼굴 이미지 리스트)."""
from .align import align_face, to_xywh
from .detector import RetinaFaceDetector

_detector = None

# load face-detector with its weight
def get_detector():
    global _detector
    if _detector is None:
        _detector = RetinaFaceDetector()
    return _detector

def detect_and_align(photo_rgb, detector=None):
    """photo_rgb: (H, W, 3) uint8 RGB 원본 (리사이즈 없음)
    반환: (boxes, images)
      boxes : [(x, y, w, h), ...]  검출 박스, 원본 픽셀 정수
      images: [img, ...]           (S, S, 3) uint8 RGB, CelebA-HQ 방식 정렬, 리사이즈 없음
      같은 인덱스 = 같은 얼굴, 신뢰도 높은 순, 얼굴이 없으면 ([], [])"""
    det = detector or get_detector()
    h, w = photo_rgb.shape[:2]
    dets, landms = det.detect(photo_rgb)
    boxes = [to_xywh(d, w, h) for d in dets]
    images = [align_face(photo_rgb, l) for l in landms]
    return boxes, images
