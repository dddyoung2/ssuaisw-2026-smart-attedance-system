from pathlib import Path
import numpy as np
import torch

from .retinaface.box_utils import decode, decode_landm, py_cpu_nms
from .retinaface.model import RetinaFace, cfg_re50
from .retinaface.prior_box import PriorBox

WEIGHT_PATH = Path(__file__).resolve().parent / "retinaface" / "weight" / "Resnet50_Final.pth"
CONF_THRES = 0.90          # 운영 임계값 (결과보고서 3.3, WIDER)
NMS_THRES = 0.4
TOP_K = 5000
KEEP_TOP_K = 750
MEAN_BGR = (104, 117, 123)

class RetinaFaceDetector:
    def __init__(self, weight_path=WEIGHT_PATH, conf=CONF_THRES, nms=NMS_THRES):
        self.conf, self.nms = conf, nms
        net = RetinaFace(cfg=cfg_re50, phase="test")
        sd = torch.load(weight_path, map_location="cpu", weights_only=True)
        sd = {k.split("module.", 1)[-1]: v for k, v in sd.get("state_dict", sd).items()}
        net.load_state_dict(sd, strict=True)
        self.net = net.eval()

    @torch.inference_mode()
    def detect(self, photo_rgb):
        """photo_rgb: (H, W, 3) uint8 RGB 원본.
        반환: dets (N, 5) [x1, y1, x2, y2, score], landms (N, 5, 2) [x, y]
              원본 픽셀 좌표, 신뢰도 높은 순.
              5점 순서: 왼눈, 오른눈, 코, 왼입꼬리, 오른입꼬리 (이미지 기준 좌우)"""
        h, w = photo_rgb.shape[:2]
        x = np.float32(photo_rgb[:, :, ::-1])          # RGB → BGR
        x -= MEAN_BGR
        x = torch.from_numpy(np.ascontiguousarray(x.transpose(2, 0, 1))).unsqueeze(0)

        loc, conf, landm = self.net(x)
        priors = PriorBox(cfg_re50, image_size=(h, w)).forward()
        var = cfg_re50["variance"]
        boxes = (decode(loc.squeeze(0), priors, var) * torch.tensor([w, h] * 2)).numpy()
        landms = (decode_landm(landm.squeeze(0), priors, var) * torch.tensor([w, h] * 5)).numpy()
        scores = conf.squeeze(0)[:, 1].numpy()

        keep = np.where(scores > self.conf)[0]
        boxes, landms, scores = boxes[keep], landms[keep], scores[keep]
        order = scores.argsort()[::-1][:TOP_K]
        boxes, landms, scores = boxes[order], landms[order], scores[order]

        dets = np.hstack((boxes, scores[:, None])).astype(np.float32, copy=False)
        if len(dets):
            keep = py_cpu_nms(dets, self.nms)[:KEEP_TOP_K]
            dets, landms = dets[keep], landms[keep]
        return dets.reshape(-1, 5), landms.reshape(-1, 5, 2).astype(np.float32)