"""Host-independent OCR contract: normalized top-left boxes and local inference."""
from functools import lru_cache
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def configuration():
    backend = os.environ.get("PIU_OCR_BACKEND", "auto").lower()
    if backend == "auto":
        backend = "vision" if sys.platform == "darwin" else "easyocr"
    device = os.environ.get("PIU_OCR_DEVICE", "cpu").lower()
    if backend not in {"vision", "easyocr"}:
        raise ValueError("PIU_OCR_BACKEND must be auto, vision or easyocr")
    if device not in {"cpu", "auto", "cuda", "mps"} and not (device.startswith("cuda:") and device[5:].isdigit()):
        raise ValueError("PIU_OCR_DEVICE must be cpu, auto, cuda, cuda:N or mps")
    return {"backend": backend, "device": "native" if backend == "vision" else device}


def ocr_binary():
    if sys.platform != "darwin" or not shutil.which("swiftc"):
        raise ValueError("Vision requires macOS and Xcode Command Line Tools; use PIU_OCR_BACKEND=easyocr on Linux")
    source = ROOT / "native/ocr.swift"
    binary = ROOT / ".local/bin/piu-ocr"
    cache = ROOT / ".local/cache/swift"
    cache.mkdir(parents=True, exist_ok=True)
    binary.parent.mkdir(parents=True, exist_ok=True)
    if not binary.exists() or binary.stat().st_mtime_ns < source.stat().st_mtime_ns:
        temporary = binary.with_suffix(f".{os.getpid()}.tmp")
        subprocess.run(["swiftc", "-module-cache-path", str(cache), str(source), "-o", str(temporary)], check=True)
        temporary.replace(binary)
    return binary


@lru_cache(maxsize=4)
def reader(english, device):
    try:
        import easyocr
    except ImportError as error:
        raise ValueError('Install Linux OCR with .venv/bin/pip install -e ".[ocr]"') from error
    return easyocr.Reader(["en"] if english else ["ko", "en"],
                          gpu=False if device == "cpu" else True if device == "auto" else device,
                          model_storage_directory=str(ROOT / ".local/cache/easyocr/models"),
                          user_network_directory=str(ROOT / ".local/cache/easyocr/network"),
                          verbose=False)


def normalized_line(points, text, confidence, width, height):
    xs, ys = zip(*points)
    x0, x1 = max(0, min(xs)), min(width, max(xs))
    y0, y1 = max(0, min(ys)), min(height, max(ys))
    return {"text": text, "confidence": float(confidence),
            "box": [x0 / width, y0 / height, (x1 - x0) / width, (y1 - y0) / height]}


def ocr_images(paths, english=False):
    paths = list(paths)
    if not paths:
        return []
    config = configuration()
    if config["backend"] == "vision":
        result = subprocess.run([str(ocr_binary()), *(["--english"] if english else []), *map(str, paths)],
                                capture_output=True, text=True)
        if result.returncode:
            raise ValueError("Local Vision OCR failed: " + result.stderr.strip())
        return json.loads(result.stdout)
    engine = reader(english, config["device"])
    from PIL import Image
    results = []
    for path in paths:
        with Image.open(path) as image:
            width, height = image.size
        lines = [normalized_line(points, text, confidence, width, height)
                 for points, text, confidence in engine.readtext(str(path), detail=1, paragraph=False)]
        results.append({"path": str(path), "lines": lines})
    return results
