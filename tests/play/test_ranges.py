"""Native JSONL adapter preserves counter observation brackets."""
import unittest
import json
import tempfile
from pathlib import Path
from piu_timeline.play.ranges import counter_frame_ranges


class CounterFrameAdapterTest(unittest.TestCase):
    def test_native_counter_changes_keep_pts_and_reject_reset_and_long_gap(self):
        frames = [{'playback_seconds': time, 'source_pts_seconds': time + 100,
                   'combo': value, 'combo_confidence': confidence}
                  for time, value, confidence in ((1, 5, .99), (1.01, None, 0), (1.02, 6, .9),
                                                   (1.03, 4, .95), (2.1, 7, .99),
                                                   (2.15, 8, .2), (2.2, 8, .9))]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'frames.jsonl'
            path.write_text(''.join(json.dumps(frame) + '\n' for frame in frames))
            events = counter_frame_ranges(path)
        self.assertEqual([(event['before'], event['after']) for event in events], [(5, 6), (7, 8)])
        self.assertEqual(events[0]['source_pts_seconds'], [101, 101.02])
        self.assertEqual((events[0]['lower_seconds'], events[0]['upper_seconds']), (1, 1.02))
