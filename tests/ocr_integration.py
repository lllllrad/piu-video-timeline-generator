"""Explicit host-side OCR smoke check; not part of sandbox-only unit checks."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from recognition import focused_lines, frame_labels, ocr_images


class VisionIntegrationTest(unittest.TestCase):
    def test_result_title_does_not_include_dim_background_credits(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "result.png"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=1300x730",
                            "-vf", "drawtext=text='SAMPLE':fontsize=28:fontcolor=white:x=590:y=122,"
                            "drawtext=text='BACKGROUND CREDITS':fontsize=24:fontcolor=gray:x=730:y=122",
                            "-frames:v", "1", str(image)], check=True)
            lines = focused_lines(image, "result", 1300, 730)
            self.assertEqual(frame_labels(lines, "result")["song"]["text"], "SAMPLE")
            # Raw OCR evidence may retain credits; the selected title must not.

    def test_real_ocr_recognizes_rendered_mode_and_level(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "label.png"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=1200x200",
                            "-vf", "drawtext=text='SINGLE 21':fontsize=96:fontcolor=white:x=40:y=40",
                            "-frames:v", "1", str(image)], check=True)
            lines = ocr_images([image], english=True)[0]["lines"]
            self.assertIn("SINGLE 21", " ".join(line["text"] for line in lines))


if __name__ == "__main__":
    unittest.main()
