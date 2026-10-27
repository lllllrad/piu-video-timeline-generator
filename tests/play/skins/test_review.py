"""Reference review must show real geometry and exclude unsupported pixels."""
from base64 import b64encode
from pathlib import Path
import tempfile
import unittest

from piu_timeline.play.skins.review import review_bank
from tests.play.skins.test_detector import examples


class ReferenceReviewTest(unittest.TestCase):
    def test_original_alpha_and_region_geometry_survive_the_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            examples(root)
            output = review_bank(root/'bank.json', root/'review.html', lane_kind=0)
            html = output.read_text()
            self.assertIn('viewBox="0 0 20 35"', html)
            self.assertIn('<rect x="6" y="22" width="8" height="13"', html)
            self.assertIn('M 8 10 h 4 M 10 8 v 4', html)
            self.assertIn(b64encode((root/'hold_start.png').read_bytes()).decode('ascii'), html)
            self.assertIn('cap: [0, 0, 20, 20]', html)
            with self.assertRaisesRegex(ValueError, 'No skin references'):
                review_bank(root/'bank.json', root/'empty.html', lane_kind=2)
            self.assertFalse((root/'empty.html').exists())
