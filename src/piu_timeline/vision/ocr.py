"""Host-independent OCR contract: normalized top-left boxes and local inference."""
from collections import OrderedDict
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import warnings
from time import perf_counter

from piu_timeline import ROOT


def configuration():
    backend = os.environ.get("PIU_OCR_BACKEND", "auto").lower()
    if backend == "auto":
        backend = "vision" if sys.platform == "darwin" else "paddleocr"
    device = os.environ.get("PIU_OCR_DEVICE", "auto").lower()
    if backend not in {"vision", "easyocr", "paddleocr"}:
        raise ValueError("PIU_OCR_BACKEND must be auto, vision, paddleocr or easyocr")
    if device not in {"cpu", "auto", "cuda", "mps"} and not (device.startswith("cuda:") and device[5:].isdigit()):
        raise ValueError("PIU_OCR_DEVICE must be cpu, auto, cuda, cuda:N or mps")
    return {"backend": backend, "device": "native" if backend == "vision" else device}


def cache_identity():
    config=configuration()
    if config['backend']=='paddleocr':
        from piu_timeline.vision.paddle import PIPELINE
        return {**config,'pipeline':PIPELINE}
    return config


def ocr_binary():
    if sys.platform != "darwin" or not shutil.which("swiftc"):
        raise ValueError("Vision requires macOS and Xcode Command Line Tools; use PIU_OCR_BACKEND=paddleocr on Linux")
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
        raise ValueError('Legacy EasyOCR requires easyocr==1.7.2; install it explicitly or use the default paddleocr backend') from error
    return easyocr.Reader(["en"] if english else ["ko", "en"],
                          gpu=False if device == "cpu" else True if device == "auto" else device,
                          model_storage_directory=str(ROOT / ".local/cache/easyocr/models"),
                          user_network_directory=str(ROOT / ".local/cache/easyocr/network"),
                          verbose=False)


def normalized_line(points, text, confidence, width, height):
    xs, ys = zip(*points)
    x0, x1 = float(max(0, min(xs))), float(min(width, max(xs)))
    y0, y1 = float(max(0, min(ys))), float(min(height, max(ys)))
    return {"text": text, "confidence": float(confidence),
            "box": [x0 / width, y0 / height, (x1 - x0) / width, (y1 - y0) / height]}


def _ocr_images_uncached(paths, english=False, single_line=False):
    paths = list(paths)
    if not paths:
        return []
    config = configuration()
    if config['backend']=='paddleocr':
        from piu_timeline.vision.paddle import read_image
        return [{'path':str(path),'lines':read_image(path,english,config['device'], single_line=single_line)} for path in paths]
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
        # EasyOCR 1.7.2 hardcodes pin_memory=True, including CPU inference.
        # PyTorch already disables pinning without an accelerator; hide only that notice.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r"^'pin_memory' argument is set as true but no accelerator is found, "
                        r"then device pinned memory won't be used\.$",
                category=UserWarning,
                module=r"^torch\.utils\.data\.dataloader$",
            )
            lines = [normalized_line(points, text, confidence, width, height)
                     for points, text, confidence in engine.readtext(str(path), detail=1, paragraph=False)]
        results.append({"path": str(path), "lines": lines})
    return results


_IMAGE_CACHE = OrderedDict()
_METRICS = {"requested_images": 0, "inferred_images": 0, "cached_images": 0, "seconds": 0.0}


def ocr_metrics():
    """Process-local counts of OCR input images (including focused crops)."""
    return dict(_METRICS)


def ocr_images(paths, english=False, single_line=False):
    paths = list(paths)
    if not paths:
        return []
    started = perf_counter()
    config = cache_identity()
    keys, missing = [], {}
    for path in paths:
        key = (json.dumps(config,sort_keys=True), english, single_line, sha256(Path(path).read_bytes()).digest())
        keys.append(key)
        if key not in _IMAGE_CACHE:
            missing.setdefault(key, path)
    fresh = {}
    if missing:
        options = {'english': english, **({'single_line': True} if single_line else {})}
        fresh = {key: result["lines"] for key, result in
                 zip(missing, _ocr_images_uncached(list(missing.values()), **options))}
    results = []
    for path, key in zip(paths, keys):
        lines = fresh[key] if key in fresh else _IMAGE_CACHE[key]
        results.append({"path": str(path), "lines": deepcopy(lines)})
    for key in keys:
        if key in fresh:
            _IMAGE_CACHE[key] = fresh[key]
        _IMAGE_CACHE.move_to_end(key)
    while len(_IMAGE_CACHE) > 512:
        _IMAGE_CACHE.popitem(last=False)
    _METRICS["requested_images"] += len(paths)
    _METRICS["inferred_images"] += len(missing)
    _METRICS["cached_images"] += len(paths) - len(missing)
    _METRICS["seconds"] += perf_counter() - started
    return results
