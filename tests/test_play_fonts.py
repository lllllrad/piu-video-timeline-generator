import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from piu_timeline.play_fonts import validated_reader, cache_current, refresh_reader
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
    def test_broadly_validated_font_can_repair_sparse_crops_of_unchanged_recording(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive=root/'source/play/segment-001/evidence';archive.mkdir(parents=True)
            complete_reader().save(archive/'digit-templates.npz')
            record={'path':'source.mkv','size_bytes':100,'mtime_ns':123}
            settings={'game_roi':[0,0,100,100],'analysis_width':650}
            metadata={'media':record,**settings,'bootstrap':{'reused_from':{
                'kind':'pixel_validated_font','validation_frames':12,'validation_digit_classes':10}}}
            path=archive.parent/'analysis.json';path.write_text(json.dumps(metadata))
            images=[image('123'),image('456')]
            result,provenance=validated_reader(DigitReader(),images,root,record,None,settings)
            self.assertIsNotNone(provenance)
            self.assertEqual(provenance['kind'],'recording_validated_font')
            self.assertEqual(result.read(image('789'))[0],789)
            # Sparse observations cannot validate unrelated media or a changed ROI.
            for other_record,other_settings in [({**record,'mtime_ns':124},settings),
                                                (record,{**settings,'game_roi':[0,0,200,100]})]:
                _,rejected=validated_reader(DigitReader(),images,root,other_record,None,other_settings)
                self.assertIsNone(rejected)
            # A sparse within-recording validation cannot seed another sparse import.
            metadata['bootstrap']['reused_from']['kind']='recording_validated_font'
            path.write_text(json.dumps(metadata))
            _,rejected=validated_reader(DigitReader(),images,root,record,None,settings)
            self.assertIsNone(rejected)

    def test_new_pixel_validated_font_invalidates_weak_saved_reader_without_mutating_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);out=root/'current/play/segment-001';evidence=out/'evidence'
            evidence.mkdir(parents=True)
            bank=evidence/'digit-templates.npz';DigitReader().save(bank)
            for i in range(10):cv2.imwrite(str(evidence/f'combo-{i:02}.png'),image(i))
            cached={'media':{'path':'current.mkv'}}
            self.assertTrue(cache_current(cached,out,root))
            original=bank.read_bytes()
            reference=root/'new-recording/play/segment-001/evidence';reference.mkdir(parents=True)
            complete_reader().save(reference/'digit-templates.npz')
            reference.parent.joinpath('analysis.json').write_text(json.dumps({'media':{'path':'new.mkv'}}))
            self.assertFalse(cache_current(cached,out,root))
            self.assertEqual(bank.read_bytes(),original)
            self.assertFalse((evidence/'validated-font.npz').exists())
            self.assertTrue(refresh_reader(cached,out,root))
            self.assertTrue(cache_current(cached,out,root))
            self.assertEqual(cached['bootstrap']['missing_digits'],[])

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
