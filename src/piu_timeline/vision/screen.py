"""Read fixed UI anchors for scene routing, independently of gameplay frames."""
from pathlib import Path
import subprocess

from piu_timeline.vision.ocr import ocr_images, configuration

# Screen routing needs UI words/numeric rows, not song art or BGA credits.
REGIONS = (("panel", .20, .08, .60, .66),
           ("charts", .05, .82, .90, .15),
           ("accounts", .14, .005, .72, .085))
VERSION = 1


def screen_lines(frame, width, height, controls_only=False):
    """Return English UI anchors mapped into the original game coordinates."""
    frame = Path(frame)
    paths, regions = [], []
    # Linux image processing uses Pillow. Decode once and crop in memory;
    # Vision keeps the FFmpeg path.
    image = None
    if configuration()["backend"] != "vision":
        from PIL import Image
        with Image.open(frame) as source:
            image = source.convert("RGB")
    command = ["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(frame)]
    needs_crops = False
    regions_to_read = (("controls", .20, .08, .60, .66),) if controls_only else REGIONS
    for name, x, y, w, h in regions_to_read:
        px, py, pw, ph = int(x * width), int(y * height), int(w * width), int(h * height)
        path = frame.with_name(frame.stem + f"-scene-v{VERSION}-{name}.png")
        if not path.is_file():
            if image is not None:
                crop = image.crop((px, py, px + pw, py + ph))
                if controls_only and crop.width > 400:
                    crop = crop.resize((400, max(1, round(crop.height * 400 / crop.width))))
                crop.save(path)
            else:
                needs_crops = True
                processing = f"crop={pw}:{ph}:{px}:{py}" + (r",scale=min(400\,iw):-1" if controls_only else "")
                command += ["-vf", processing, "-frames:v", "1", str(path)]
        paths.append(path)
        regions.append((px / width, py / height, pw / width, ph / height))
    if needs_crops:
        subprocess.run(command, check=True, capture_output=True)
    lines = []
    for result, (x, y, w, h) in zip(ocr_images(paths, english=True), regions):
        for line in result["lines"]:
            bx, by, bw, bh = line["box"]
            lines.append({**line, "box": [x + bx * w, y + by * h, bw * w, bh * h],
                          "image": result["path"], "scene_anchor": True})
    return lines


class SceneRouter:
    """Reuse only a directly observed UI layout; never copy text or numbers."""

    def __init__(self):
        self.templates = []

    @staticmethod
    def signatures(frame):
        if configuration()["backend"] == "vision":
            return None
        import numpy as np
        from PIL import Image
        with Image.open(frame) as image:
            pixels = np.asarray(image.convert("RGB"))
        height, width = pixels.shape[:2]
        masks = []
        # Different-colored, fixed judgment captions. BGA colors may prevent a
        # match, but must not become copied OCR or numeric result evidence.
        for y, color in ((.434, "cyan"), (.487, "green"), (.540, "yellow"),
                         (.593, "magenta"), (.646, "orange")):
            crop = pixels[int((y - .014) * height):int((y + .014) * height),
                          int(.42 * width):int(.58 * width)].astype(int)
            r, g, b = crop[..., 0], crop[..., 1], crop[..., 2]
            conditions = {"cyan": (g > 140) & (b > 140) & (r < 180),
                          "green": (g > 140) & (r < 180) & (b < 180),
                          "yellow": (r > 140) & (g > 140) & (b < 180),
                          "magenta": (r > 140) & (b > 140) & (g < 180),
                          "orange": (r > 140) & (g > 40) & (g < 170) & (b < 160)}
            masks.append(conditions[color])
        band = pixels[int(.84 * height):int(.94 * height), int(.05 * width):int(.95 * width)].astype(int)
        browsing = (band.max(axis=2) > 140) & (band.max(axis=2) - band.min(axis=2) > 80)
        header = False
        for x in (.20, .64):
            name = pixels[int(.055 * height):int(.075 * height), int(x * width):int((x + .16) * width)]
            rank = pixels[int(.019 * height):int(.039 * height), int(x * width):int((x + .16) * width)]
            if name.size and rank.size:
                header |= (name.min(axis=2) > 180).mean() > .55 and (rank.max(axis=2) < 120).mean() > .5
        return masks, browsing, bool(header)

    @staticmethod
    def needs_ui(signature):
        return signature is None or signature[2] or sum(mask.sum() >= 25 for mask in signature[0]) >= 3

    def match(self, signature):
        if signature is None:
            return None
        import numpy as np
        masks, browsing, _ = signature
        for template in reversed(self.templates):
            previous, old_browsing, _ = template["signature"]
            if template["scene"] == "result":
                agreements = 0
                for current, old in zip(masks, previous):
                    if current.shape != old.shape or min(current.sum(), old.sum()) < 25:
                        continue
                    dice = 2 * np.count_nonzero(current & old) / (current.sum() + old.sum())
                    agreements += dice >= .90
                if agreements >= 3:
                    return {"scene": "result", "method": "visual_template", "source": template["source"]}
            elif browsing.shape == old_browsing.shape and min(browsing.sum(), old_browsing.sum()) >= 500:
                dice = 2 * np.count_nonzero(browsing & old_browsing) / (browsing.sum() + old_browsing.sum())
                if dice >= .85:
                    return {"scene": "browse", "method": "visual_template", "source": template["source"]}
        return None

    def remember(self, frame, scene, signature):
        if signature is not None and scene in {"result", "browse"}:
            self.templates.append({"source": str(frame), "scene": scene, "signature": signature})
            self.templates = self.templates[-12:]
