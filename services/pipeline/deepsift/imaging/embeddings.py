"""M8 — LOCAL VISION BASELINE: compact pretrained image embeddings on CPU via ONNX Runtime (no cloud, no training).

Not a claim of spacecraft deployability: models are Earth-image networks run on a laptop CPU.
Candidates (data/manifests/vision_models.json): MobileNetV2 (ONNX zoo), ResNet-18 (ONNX zoo), DINOv2-small (HF).
Embedding tap: classifier models → the pooled vector feeding the final Gemm; DINOv2 → CLS token of last_hidden_state.
Input: grayscale Navcam working image replicated to 3 channels, 224×224, ImageNet mean/std.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort

from deepsift.core.config import DATA_DIR

MODELS = {
    "mobilenetv2-12": {"tap": "472", "input": "input"},
    "resnet18-v1-7": {"tap": "flatten_170", "input": "data"},
    "dinov2-small": {"tap": "last_hidden_state", "input": "pixel_values", "cls": True},
}
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)[:, None, None]
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)[:, None, None]


def _tapped(name: str) -> Path:
    """Derived copy exposing the embedding tensor as a graph output (the downloaded original is never modified)."""
    src = DATA_DIR / "models" / f"{name}.onnx"
    dst = DATA_DIR / "models" / f"{name}.embed.onnx"
    tap = MODELS[name]["tap"]
    if not dst.exists():
        m = onnx.load(str(src))
        if tap not in [o.name for o in m.graph.output]:
            m.graph.output.append(onnx.helper.make_tensor_value_info(tap, onnx.TensorProto.FLOAT, None))
        onnx.save(m, str(dst))
    return dst


class Embedder:
    def __init__(self, name: str, threads: int = 4):
        self.name = name
        self.cfg = MODELS[name]
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        self.sess = ort.InferenceSession(str(_tapped(name)), so, providers=["CPUExecutionProvider"])
        self.size_bytes = (DATA_DIR / "models" / f"{name}.onnx").stat().st_size

    @staticmethod
    def preprocess(work: np.ndarray) -> np.ndarray:
        from PIL import Image

        im = Image.fromarray((np.clip(work, 0, 1) * 255).astype(np.uint8)).resize((224, 224), Image.BICUBIC)
        x = np.asarray(im, dtype=np.float32)[None] / 255.0
        x = np.repeat(x, 3, axis=0)
        return ((x - MEAN) / STD)[None].astype(np.float32)

    def embed(self, work: np.ndarray) -> tuple[np.ndarray, float]:
        x = self.preprocess(work)
        feeds = {self.cfg["input"]: x}
        t0 = time.perf_counter()
        out = self.sess.run([self.cfg["tap"]], feeds)[0]
        ms = (time.perf_counter() - t0) * 1000
        v = out[0, 0] if self.cfg.get("cls") else out.reshape(out.shape[0], -1)[0]
        v = v.astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-12), ms


def rss_mb() -> float:
    import resource

    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1e6 if r > 1e7 else r / 1024      # macOS reports bytes, Linux kB
