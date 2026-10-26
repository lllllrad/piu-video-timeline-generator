import math
import unittest

from piu_timeline.play.motion import ScrollMotion
from piu_timeline.play.tracking import NoteTracker, Track


HEIGHT = 400
SPACING = 40
LAYOUT = {'receptor_y': .1, 'note_y_max': .95, 'combo_roi': [.15,.35,.7,.3],
          'lanes': [{'x': .2+.1*lane, 'color':'blue'} for lane in range(4)]}


def observations(i):
    # A 30 Hz game image captured at 60 Hz: repeated renders are real
    # observations, not accelerating/decelerating notes.
    time = i/60
    phase = (i//2)*8
    peers = []
    for lane in range(3):
        for row in range(12):
            y = 100+row*60-phase
            if 60 < y < 380:
                peers.append({'lane':lane,'x':LAYOUT['lanes'][lane]['x'],'y':y/HEIGHT})
    return time, phase, peers


class SharedMotionTest(unittest.TestCase):
    def test_equal_pixel_spacing_uses_one_subframe_clock_despite_repeated_renders(self):
        motion = ScrollMotion(HEIGHT, SPACING)
        for i in range(150):
            time, phase, peers = observations(i)
            motion.update(time, peers, time+100)
        results = []
        for target in (1.263, 1.347, 1.431):
            points = []
            for i in range(150):
                time, phase, _ = observations(i)
                y = 40+target*240-phase
                if .3 < time and 80 < y < 320:
                    points.append((time,y))
            result = motion.fit(Track(3,points),40,LAYOUT)
            self.assertIsNotNone(result)
            self.assertEqual(result['fit_method'],'shared_scroll_clock')
            self.assertAlmostEqual(result['target_seconds'], target, delta=.012)
            self.assertGreater(result['prediction_uncertainty_seconds'],0)
            self.assertLessEqual(abs(result['target_seconds']-target),result['prediction_uncertainty_seconds'])
            self.assertAlmostEqual(result['crossing_source_pts_seconds'][0]-result['crossing_frame_seconds'][0],100)
            results.append(result['target_seconds'])
        self.assertAlmostEqual(results[1]-results[0],results[2]-results[1],places=10)
        self.assertAlmostEqual(results[1]-results[0],.084,delta=.001)
        self.assertTrue(any(abs(value*60-round(value*60))>.1 for value in results))

    def test_occluded_head_reconnects_using_peer_displacement_and_original_times(self):
        tracker = NoteTracker(LAYOUT,400,400)
        for i in range(120):
            time, phase, peers = observations(i)
            y = 40+1.2*240-phase
            if 63 < y < 380 and not .7 <= time <= .95:
                peers.append({'lane':3,'x':LAYOUT['lanes'][3]['x'],'y':y/400})
            tracker.update(time,peers,time+100)
        notes = [note for note in tracker.finish() if note['lane']==3 and note['status']=='estimated']
        self.assertEqual(len(notes),1)
        self.assertTrue(any(b[0]-a[0]>.2 for a,b in zip(notes[0]['points'],notes[0]['points'][1:])))
        self.assertAlmostEqual(notes[0]['target_seconds'],1.2,delta=.015)

    def test_one_lane_cannot_establish_shared_motion_or_bridge_a_gap(self):
        motion = ScrollMotion(400,40)
        for i in range(40):
            time, _, peers = observations(i)
            motion.update(time,[note for note in peers if note['lane']==0])
        self.assertIsNone(motion.distance(0,39/60))

    def test_unobserved_step_breaks_shared_motion_and_individual_motion_is_not_forced(self):
        motion = ScrollMotion(400,40)
        points = []
        for i in range(100):
            time, phase, peers = observations(i)
            motion.update(time,peers if i!=50 else [],time+100)
            if i>55:points.append((time,200-.5*(phase-220)))
        self.assertIsNone(motion.distance(49/60,51/60))
        self.assertIsNone(motion.fit(Track(3,points),40,LAYOUT))

    def test_close_target_times_do_not_delete_separately_observed_heads(self):
        tracker=NoteTracker(LAYOUT,400,400)
        for i in range(150):
            time,phase,peers=observations(i)
            for target in (1.263,1.293):
                y=40+target*240-phase
                if 80<y<320:peers.append({'lane':3,'x':LAYOUT['lanes'][3]['x'],'y':y/400})
            tracker.update(time,peers,time+100)
        notes=[n for n in tracker.finish() if n['lane']==3 and n['status']=='estimated']
        self.assertEqual(len(notes),2)
        self.assertAlmostEqual(abs(notes[0]['target_seconds']-notes[1]['target_seconds']),.03,delta=.001)
