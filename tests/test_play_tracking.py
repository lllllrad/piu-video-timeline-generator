import unittest
from pathlib import Path
import tempfile

import cv2
import numpy as np

from piu_timeline.play_tracking import Track, fit_track, DigitReader, ComboTracker, NoteTracker, associate


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
        self.assertEqual(jump['status'], 'candidate')

    def test_one_combo_increment_matches_a_chord_row(self):
        notes = [{'status': 'estimated', 'target_seconds': 1.0, 'lane': 0},
                 {'status': 'estimated', 'target_seconds': 1.0, 'lane': 1}]
        events = [{'status': 'candidate', 'lower_seconds': .99, 'upper_seconds': 1.02}]
        self.assertEqual(len(associate(notes, events)), 2)
        self.assertEqual(events[0]['status'], 'matched')

    def test_clipped_head_centers_do_not_look_like_deceleration(self):
        points = [(i / 60, 250 - 500 * i / 60) for i in range(23)]
        points += [(23 / 60, 74), (24 / 60, 73), (25 / 60, 72)]
        result = fit_track(Track(0, points), 50, 40)
        self.assertEqual(result['status'], 'estimated')
        self.assertAlmostEqual(result['target_seconds'], .4)

    def test_repeated_render_frames_are_not_a_scroll_gimmick(self):
        track = Track(0, [(i/60, 200-500*(i//2)/30) for i in range(20)])
        result = fit_track(track, 50, 40)
        self.assertEqual(result['status'], 'estimated')
        self.assertAlmostEqual(result['target_seconds'], .3, delta=.02)
        self.assertGreaterEqual(result['prediction_uncertainty_seconds'], .015)

    def test_counter_jump_retains_one_aggregate_bracket_for_two_rows(self):
        notes = [{'status':'estimated','target_seconds':t,'lane':0} for t in (1.02,1.08)]
        event = {'status':'candidate','delta':2,'lower_seconds':1.,'upper_seconds':1.1}
        matches = associate(notes,[event])
        self.assertEqual(len(matches),2)
        self.assertEqual({m['aggregate_row_count'] for m in matches},{2})
        self.assertEqual({(m['combo_lower_seconds'],m['combo_upper_seconds']) for m in matches},{(1.,1.1)})

    def test_prediction_survives_combo_overlay_occlusion(self):
        layout = {'lanes':[{'x':.1+.2*i} for i in range(5)],'receptor_y':.2,
                  'combo_roi':[.4,.52,.2,.075]}
        tracker = NoteTracker(layout,320,180)
        for t in (0,.05,.10,.15,.20,.25,.30,.35):
            visible = t <= .15 or t >= .35
            tracker.update(t,[{'lane':2,'y':(180-400*t)/180}] if visible else [])
        self.assertEqual(len(tracker.active),1)
        self.assertEqual(len(tracker.finished),0)
        self.assertEqual(len(tracker.active[0].points),5)

    def test_counter_jump_cannot_be_explained_by_head_count(self):
        notes = [{'status': 'estimated', 'target_seconds': 1., 'lane': lane} for lane in (0, 1)]
        event = {'status': 'candidate', 'delta': 2, 'lower_seconds': .99, 'upper_seconds': 1.02}
        self.assertEqual(associate(notes, [event]), [])

    def test_monotone_alignment_recovers_close_successive_inputs(self):
        notes = [{'status': 'estimated', 'target_seconds': t, 'lane': 0} for t in (1 + i*.06 for i in range(300))]
        events = [{'status': 'candidate', 'delta': 1, 'lower_seconds': t+.01, 'upper_seconds': t+.03}
                  for t in (1 + i*.06 for i in range(300))]
        matches = associate(notes, events)
        self.assertEqual([m['note'] for m in matches], list(range(300)))

    def test_equal_cost_competing_alignments_remain_ambiguous(self):
        notes = [{'status': 'estimated', 'target_seconds': t, 'lane': 0} for t in (.97, 1.03)]
        event = {'status': 'candidate', 'delta': 1, 'lower_seconds': .99, 'upper_seconds': 1.01}
        self.assertEqual(associate(notes, [event]), [])

    def test_implausible_counter_read_does_not_corrupt_baseline(self):
        tracker = ComboTracker()
        for t, value in [(0, 140), (.02, 140), (.04, 4140), (.06, 4140), (.08, 141), (.10, 141)]:
            tracker.update(t, value)
        self.assertEqual(len(tracker.events), 1)
        self.assertEqual((tracker.events[0]['before'], tracker.events[0]['after']), (140, 141))

    def test_same_lane_head_fragments_are_not_counted_as_chords(self):
        layout = {'lanes': [{'x': .1+.2*i} for i in range(5)], 'receptor_y': .2}
        tracker = NoteTracker(layout, 320, 180)
        tracker.finished = [Track(0, [(i/60, y-500*i/60) for i in range(12)]) for y in (180, 184)]
        notes = tracker.finish()
        self.assertEqual(sum(n['status'] == 'estimated' for n in notes), 1)
        self.assertEqual(sum(n['reason'] == 'duplicate_head_component' for n in notes), 1)

    def test_repeated_digit_in_one_source_is_not_corroboration(self):
        image=np.zeros((60,180,3),dtype='uint8')
        cv2.putText(image,'111',(5,45),cv2.FONT_HERSHEY_SIMPLEX,1.5,(255,255,255),3)
        reader=DigitReader();reader.train(image,111,source=1);reader.train(image,111,source=1)
        self.assertIsNone(reader.read(image)[0])
        reader.train(image,111,source=2)
        self.assertEqual(reader.read(image)[0],111)

    def test_long_component_at_receptor_blocks_hold_timing(self):
        layout={'lanes':[{'x':.1+.2*i,'color':('blue','red','yellow','red','blue')[i]} for i in range(5)],
                'receptor_y':.2,'note_y_max':.95}
        tracker=NoteTracker(layout,320,180)
        image=np.zeros((180,320,3),dtype='uint8')
        cv2.rectangle(image,(22,60),(42,170),(0,200,255),-1)
        notes=tracker.detect(image);tracker.update(.1,notes)
        self.assertTrue(tracker.hold_candidate)
        self.assertEqual(len(tracker.unsupported_intervals),1)
        tracker.detect(np.zeros_like(image))
        self.assertFalse(tracker.hold_candidate)

    def test_external_display_delay_changes_association_not_raw_evidence(self):
        notes=[{'status':'estimated','target_seconds':1,'lane':0}]
        event={'status':'candidate','lower_seconds':1.10,'upper_seconds':1.12}
        self.assertEqual(associate(notes,[dict(event)]),[])
        matched=associate(notes,[dict(event)],display_delay=.1)
        self.assertEqual(len(matched),1)
        self.assertAlmostEqual(matched[0]['raw_offset_lower_ms'],100)

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

    def test_digit_bank_preserves_predictions_and_distinct_source_confirmation(self):
        image=np.zeros((60,150,3),dtype='uint8')
        cv2.putText(image,'12',(5,45),cv2.FONT_HERSHEY_SIMPLEX,1.5,(255,255,255),3)
        reader=DigitReader();reader.train(image,12,source=1);reader.train(image,12,source=2)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'templates.npz';reader.save(path)
            restored=DigitReader.load(path)
        self.assertEqual(restored.read(image),reader.read(image))
        self.assertEqual(restored.sources,reader.sources)
        self.assertIsNone(restored.read(np.zeros_like(image),expected=12)[0])
