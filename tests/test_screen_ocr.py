"""UI crop geometry and source preservation, without loading OCR models."""
from importlib.util import find_spec
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline import screen_ocr


@unittest.skipUnless(find_spec("PIL"), "EasyOCR image dependency is not installed")
class ScreenOCRTest(unittest.TestCase):
    def test_anchors_are_mapped_back_and_source_is_unchanged(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temporary:
            frame = Path(temporary) / "frame.png"
            Image.new("RGB", (1300, 730), (15, 35, 55)).save(frame)
            original = frame.read_bytes(), frame.stat().st_mtime_ns
            def recognize(paths, english=False):
                self.assertTrue(english)
                return [{"path": str(p), "lines": [{"text": "Anchor", "confidence": .9,
                                                     "box": [0, 0, 1, 1]}]} for p in paths]
            with patch.object(screen_ocr, "configuration", return_value={"backend": "easyocr"}), \
                    patch.object(screen_ocr, "ocr_images", side_effect=recognize):
                lines = screen_ocr.screen_lines(frame, 1300, 730)
            self.assertEqual(len(lines), len(screen_ocr.REGIONS))
            for line, (_, x, y, w, h) in zip(lines, screen_ocr.REGIONS):
                self.assertEqual(line["box"], [int(x * 1300) / 1300, int(y * 730) / 730,
                                               int(w * 1300) / 1300, int(h * 730) / 730])
                with Image.open(line["image"]) as crop:
                    self.assertEqual(crop.size, (int(w * 1300), int(h * 730)))
            self.assertEqual((frame.read_bytes(), frame.stat().st_mtime_ns), original)

    def test_visual_routing_keeps_layout_separate_from_changing_numbers(self):
        from PIL import Image, ImageDraw
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, changed, absent = (root / name for name in ("first.png", "changed.png", "absent.png"))
            def image(path, background, number):
                canvas = Image.new("RGB", (1300, 730), background)
                draw = ImageDraw.Draw(canvas)
                for y, color in ((.434, "cyan"), (.487, "lime"), (.540, "yellow"),
                                 (.593, "magenta"), (.646, "orange")):
                    draw.rectangle((600, int(y * 730) - 4, 700, int(y * 730) + 4), fill=color)
                draw.text((850, 320), number, fill="white")
                canvas.save(path)
            image(first, (10, 10, 10), "123")
            image(changed, (70, 70, 70), "987")
            Image.new("RGB", (1300, 730), (70, 70, 70)).save(absent)
            with patch.object(screen_ocr, "configuration", return_value={"backend": "easyocr"}):
                router = screen_ocr.SceneRouter()
                router.remember(first, "result", router.signatures(first))
                match = router.match(router.signatures(changed))
                self.assertEqual(match, {"scene": "result", "method": "visual_template", "source": str(first)})
                self.assertIsNone(router.match(router.signatures(absent)))
                self.assertEqual(set(match), {"scene", "method", "source"})

    def test_control_only_probe_keeps_original_coordinates_after_downscaling(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temporary:
            frame = Path(temporary) / "frame.png"
            Image.new("RGB", (1300, 730), "black").save(frame)
            def recognize(paths, english=False):
                self.assertTrue(english)
                self.assertEqual(len(paths), 1)
                with Image.open(paths[0]) as crop:
                    self.assertEqual(crop.width, 400)
                return [{"path": str(paths[0]), "lines": [{"text": "BASIC", "confidence": 1,
                                                          "box": [0, 0, 1, 1]}]}]
            with patch.object(screen_ocr, "configuration", return_value={"backend": "easyocr"}), \
                    patch.object(screen_ocr, "ocr_images", side_effect=recognize):
                lines = screen_ocr.screen_lines(frame, 1300, 730, controls_only=True)
            self.assertEqual(lines[0]["box"], [260 / 1300, 58 / 730, 780 / 1300, 481 / 730])
