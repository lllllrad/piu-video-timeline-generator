import unittest

import cv2
import numpy as np

from piu_timeline.play_tracking import Track, fit_track, DigitReader, ComboTracker, associate


class TrackingTest(unittest.TestCase):
    def test_linear_note_predicts_receptor_crossing(self):
        track = Track(2, [(i / 60, 180 - 300 * i / 60) for i in range(12)])
        result = fit_track(track, 100, 40)
        self.assertEqual(result['status'], 'estimated')
        self.assertAlmostEqual(result['target_seconds'], 80 / 300)

    def test_acceleration_stop_reverse_and_distant_tracks_are_excluded(self):
        tracks = [Track(0, [(i / 60, 180 - 1000 * (i / 60) ** 2) for i in range(12)]),
                  Track(0, [(i / 60, 180) for i in range(12)]),
                  Track(0, [(i / 60, 180 + 300 * i / 60) for i in range(12)]),
                  Track(0, [(i / 60, 500 - 300 * i / 60) for i in range(12)])]
        for track in tracks:
            self.assertEqual(fit_track(track, 100, 40)['status'], 'excluded')

    def test_combo_updates_keep_the_first_changed_frame_bracket(self):
        tracker = ComboTracker()
        for t, value in [(0, 20), (.02, 20), (.04, 21), (.06, 21), (.08, 21), (.10, 24), (.12, 24)]:
            tracker.update(t, value)
        event, jump = tracker.events
        self.assertEqual((event['lower_seconds'], event['upper_seconds']), (.02, .04))
        self.assertEqual(event['delta'], 1)
        self.assertEqual(jump['status'], 'excluded')

    def test_association_never_assigns_one_combo_to_multiple_notes(self):
        notes = [{'status': 'estimated', 'target_seconds': 1.0, 'lane': 0},
                 {'status': 'estimated', 'target_seconds': 1.0, 'lane': 1}]
        events = [{'status': 'candidate', 'lower_seconds': .99, 'upper_seconds': 1.02}]
        self.assertEqual(associate(notes, events), [])
        self.assertEqual(events[0]['reason'], 'chord_or_duplicate_track')

    def test_digit_templates_abstain_until_corroborated(self):
        def draw(text):
            image = np.zeros((60, 150, 3), dtype='uint8')
            cv2.putText(image, text, (5, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
            return image
        reader = DigitReader()
        self.assertIsNone(reader.read(draw('12'))[0])
        reader.train(draw('12'), 12)
        self.assertIsNone(reader.read(draw('12'))[0])
        reader.train(draw('12'), 12)
        self.assertEqual(reader.read(draw('12'))[0], 12)
        self.assertIsNone(reader.read(draw('13'))[0])
