"""얼굴 검출 → 인식 인계: 출력 1(검출 박스 좌표 리스트), 출력 2(정렬 얼굴 이미지 리스트)."""
import threading

from .align import align_face, to_xywh
from .detector import RetinaFaceDetector

_detector = None
_lock = threading.Lock()   # 출석 사진과 미리보기 요청이 동시에 와도 검출기는 한 번만 로드

# load face-detector with its weight
def get_detector():
    global _detector
    with _lock:
        if _detector is None:
            _detector = RetinaFaceDetector()
    return _detector

def detect_boxes(photo_rgb, detector=None):
    """검출만 (정렬·인식 없음). 카메라 미리보기용.
    반환: [(x, y, w, h), ...] 입력 이미지 픽셀 정수, 신뢰도 높은 순"""
    det = detector or get_detector()
    h, w = photo_rgb.shape[:2]
    dets, _ = det.detect(photo_rgb)
    return [to_xywh(d, w, h) for d in dets]

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
