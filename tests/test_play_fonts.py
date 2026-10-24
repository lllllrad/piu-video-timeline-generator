import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from piu_timeline.play_fonts import validated_reader
from piu_timeline.play_tracking import DigitReader


def image(digit):
    rgb = np.zeros((45, 80, 3), dtype='uint8')
    cv2.putText(rgb, str(digit), (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    return rgb


def complete_reader():
    reader = DigitReader()
    for digit in range(10):
        for source in ('reference-frame-a', 'reference-frame-b'):
            reader.train(image(digit), str(digit), source=source)
    return reader


class FontTest(unittest.TestCase):
    def test_shapes_transfer_only_after_broad_agreement_with_current_pixels(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'reference/play/segment-001/evidence'
            archive.mkdir(parents=True)
            complete_reader().save(archive / 'digit-templates.npz')
            archive.parent.joinpath('analysis.json').write_text(json.dumps({'media': {'path': 'reference.mkv'}}))
            out = root / 'current'
            out.mkdir()
            current = DigitReader()
            result, provenance = validated_reader(current, [image(i) for i in range(10)], root, {'path': 'current.mkv'}, out)
            self.assertIsNotNone(provenance)
            self.assertEqual(provenance['validation_frames'], 10)
            self.assertEqual(provenance['source_media'], 'reference.mkv')
            self.assertTrue((out / 'validated-font.npz').is_file())
            self.assertEqual([result.read(image(i))[0] for i in range(10)], list(range(10)))
            self.assertTrue(all(not sources for sources in current.sources.values()))
            self.assertNotIn('counter_values', provenance)
            # Copies of one glyph cannot validate an entire font.
            _, rejected = validated_reader(current, [image(1)] * 12, root, {'path': 'current.mkv'}, out)
            self.assertIsNone(rejected)

    def test_complete_local_font_is_reused_without_importing_other_recordings(self):
        with tempfile.TemporaryDirectory() as temporary:
            current = complete_reader()
            result, provenance = validated_reader(current, [image(i) for i in range(10)], Path(temporary), {'path': 'current.mkv'}, Path(temporary))
            self.assertIs(result, current)
            self.assertIsNone(provenance)

    def test_ocr_label_cannot_overwrite_a_strongly_known_digit_shape(self):
        reader = DigitReader()
        for source in ('one', 'two'):
            self.assertTrue(reader.train(image(4), '4', source=source))
        self.assertFalse(reader.train(image(4), '9', source='wrong-neural-ocr'))
        self.assertEqual(reader.sources['9'], set())
        self.assertEqual(reader.read(image(4))[0], 4)
