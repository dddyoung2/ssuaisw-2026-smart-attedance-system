"""Original CVLFace IR101 weights with the official AdaFace backbone.

팀 FR 꾸러미(adaface_original)의 adaface_eval/model.py 를 옮긴 것.
바꾼 곳: net import(상대 경로), 가중치 기본 경로(같은 폴더의 weight/).
"""
import hashlib
import json
import math
from pathlib import Path
import struct

import numpy as np
import torch
from .net import build_model

WEIGHT_PATH = Path(__file__).resolve().parent / 'weight' / 'adaface_ir101_webface12m_original.safetensors'
EXPECTED_SHA256 = '2ea535a43877bd3de8091903935c783ce335be66a9f8917fae9a7a18ae4bbf56'


def file_sha256(filename):
    digest = hashlib.sha256()
    with Path(filename).open('rb') as handle:
        for block in iter(lambda: handle.read(8*1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_weights(filename):
    """Read the verified F32/I64 safetensors file; no external model code is executed."""
    filename = Path(filename)
    actual = file_sha256(filename)
    if actual != EXPECTED_SHA256:
        raise ValueError(f'Expected ORIGINAL IR101/WebFace12M weights; SHA-256 mismatch: {actual}')
    types = {'F32':(torch.float32,4), 'I64':(torch.int64,8)}
    state = {}
    with filename.open('rb') as handle:
        length = struct.unpack('<Q',handle.read(8))[0]
        header = json.loads(handle.read(length))
        for name,entry in header.items():
            if name=='__metadata__':
                continue
            dtype,size = types[entry['dtype']]
            start,stop = entry['data_offsets']
            if stop-start != math.prod(entry['shape'])*size:
                raise ValueError(f'Invalid tensor byte size: {name}')
            handle.seek(8+length+start)
            raw = handle.read(stop-start)
            if len(raw)!=stop-start:
                raise ValueError(f'Truncated tensor: {name}')
            state[name.removeprefix('model.net.')] = torch.frombuffer(bytearray(raw),dtype=dtype).reshape(entry['shape'])
    return state


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
            result.append(values)
        return np.concatenate(result,axis=0) if result else np.empty((0,512),np.float32)

    def synchronize(self):
        if self.device.type=='cuda':
            torch.cuda.synchronize(self.device)
