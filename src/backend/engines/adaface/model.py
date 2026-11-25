"""Fine-tuned AdaFace IR101 weights with the official AdaFace backbone.

팀 FR 꾸러미(adaface_original)의 adaface_eval/model.py 를 옮긴 것.
바꾼 곳: net import(상대 경로), 가중치 기본 경로(같은 폴더의 weight/),
가중치를 파인튜닝 checkpoint(adaface_weight.pt, model_state_dict)로 교체.
"""
import hashlib
from pathlib import Path

import numpy as np
import torch
from .net import build_model

WEIGHT_PATH = Path(__file__).resolve().parent / 'weight' / 'adaface_weight.pt'
EXPECTED_SHA256 = '006b0d4845b0551075cccbaef5514fa7a8eecb8c95a145d1349bd19f61cbabc4'


def file_sha256(filename):
    digest = hashlib.sha256()
    with Path(filename).open('rb') as handle:
        for block in iter(lambda: handle.read(8*1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_weights(filename):
    """Read the verified fine-tuned checkpoint (.pt) and return its model_state_dict.

    weights_only=True: 텐서·기본 자료형만 읽고 pickle 안의 코드는 실행하지 않는다.
    """
    filename = Path(filename)
    actual = file_sha256(filename)
    if actual != EXPECTED_SHA256:
        raise ValueError(f'Expected fine-tuned AdaFace weights (adaface_weight.pt); SHA-256 mismatch: {actual}')
    checkpoint = torch.load(filename, map_location='cpu', weights_only=True)
    if not isinstance(checkpoint, dict) or 'model_state_dict' not in checkpoint:
        raise ValueError('Expected a checkpoint dict with "model_state_dict"')
    return checkpoint['model_state_dict']


class AdaFaceRecognizer:
    """112x112 RGB uint8 faces -> L2-normalized 512D embeddings."""

    def __init__(self,weights=None,device='cpu',cpu_threads=4):
        self.weights = Path(weights) if weights else WEIGHT_PATH
        if not self.weights.is_file():
            raise FileNotFoundError(f'Place the release asset at {self.weights}, or pass weights=PATH')
        self.device = torch.device(device)
        if self.device.type=='cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA was requested but is unavailable; select a working device or explicitly use cpu')
        if cpu_threads<1:
            raise ValueError('cpu_threads must be positive')
        torch.set_num_threads(cpu_threads)
        self.model = build_model('ir_101')
        self.model.load_state_dict(read_weights(self.weights),strict=True)
        self.model.to(self.device).eval().requires_grad_(False)
        self.sha256 = EXPECTED_SHA256

    @torch.inference_mode()
    def encode_rgb(self,images,batch_size=32):
        images = np.asarray(images)
        if images.dtype!=np.uint8 or images.ndim!=4 or images.shape[1:]!=(112,112,3):
            raise ValueError('Expected RGB uint8 array with shape (N,112,112,3)')
        if batch_size<1:
            raise ValueError('batch_size must be positive')
        result=[]
        for start in range(0,len(images),batch_size):
            batch=images[start:start+batch_size].astype(np.float32).transpose(0,3,1,2).copy()/127.5-1
            features,_=self.model(torch.from_numpy(batch).to(self.device))
            values=features.float().cpu().numpy()
            if not np.isfinite(values).all():
                raise ValueError('Non-finite model features')
            if np.max(np.abs(np.linalg.norm(values,axis=1)-1))>=1e-4:
                raise ValueError('Expected unit-length model embeddings')
            result.append(values)
        return np.concatenate(result,axis=0) if result else np.empty((0,512),np.float32)

    def synchronize(self):
        if self.device.type=='cuda':
            torch.cuda.synchronize(self.device)
