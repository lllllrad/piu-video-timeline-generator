"""Explicit host-side OCR smoke check; not part of sandbox-only unit checks."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from piu_timeline.recognition import focused_lines, frame_labels, ocr_images
from piu_timeline.result_stats import focused_stats, parse_result, COUNT_FIELDS, ROW_Y


class VisionIntegrationTest(unittest.TestCase):
    def test_two_player_result_keeps_counts_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "two-player.png"
            filters = []
            def label(text, x, y, size=24):
                filters.append(f"drawtext=text='{text}':fontsize={size}:fontcolor=white:x={x}:y={y}")
            for cx, score_x, base in ((.335, .185, 100), (.665, .815, 200)):
                label("DOUBLE", round(cx * 1300 - 35), 207, 17)
                label("23", round(cx * 1300 - 18), 230, 26)
                label("SCORE", round(score_x * 1300 - 30), 254, 18)
                label("0987654", round(score_x * 1300 - 87), 288, 32)
                for i, y in enumerate(ROW_Y.values()):
                    label(str(base + i), round(cx * 1300 - 25), round(y * 730 - 10), 24)
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=1300x730",
                            "-vf", ",".join(filters), "-frames:v", "1", str(image)], check=True)
            lines = focused_stats(image, root, 0, 1300, 730)
            parsed = parse_result(lines)
            for player, base in (("p1", 100), ("p2", 200)):
                self.assertTrue(parsed[player]["present"])
                for i, field in enumerate(COUNT_FIELDS):
                    self.assertEqual(parsed[player]["fields"][field]["value"], base + i)

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
