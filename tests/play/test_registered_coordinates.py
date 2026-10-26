"""Subpixel translation is constrained by identities, never a musical grid."""
from copy import deepcopy
import unittest

import numpy as np

from piu_timeline.play.motion import ScrollMotion
from piu_timeline.play.registered_coordinates import refine
from piu_timeline.play.shared_timing import registered_motion
from piu_timeline.play.tracking import Track


class RegisteredCoordinatesTest(unittest.TestCase):
    def scenario(self,phase):
        timeline=[{'time':1000+i/60,'source_pts':9000+i/60} for i in range(301)]
        tracks=[]
        for index in range(50):
            points=[]
            for i,frame in enumerate(timeline):
                y=round(2*(100+index*32.37-phase(i/60)))/2
                if 80<y<340:points.append((frame['time'],y))
            if points:tracks.append(Track(index%5,points))
        return tracks,timeline

    def test_joint_offsets_remove_quantized_median_drift_under_peer_turnover(self):
        tracks,timeline=self.scenario(lambda t:233.137*t);original=deepcopy((tracks,timeline))
        positions={f['time']:{i:y for i,track in enumerate(tracks) for t,y in track.points if t==f['time']} for f in timeline}
        integrated=0
        for first,last in zip(timeline,timeline[1:]):
            a,b=positions[first['time']],positions[last['time']]
            integrated+=float(np.median([a[i]-b[i] for i in a.keys()&b.keys()]))
        self.assertGreater(abs(integrated-233.137*5),3)
        motion=registered_motion(tracks,timeline,400,40,40,380)
        self.assertFalse(motion.coordinate_failures)
        self.assertAlmostEqual(motion.distance(1000,1005),233.137*5,delta=.5)
        self.assertAlmostEqual(motion.samples[-1]['pairwise_phase_pixels'],integrated)
        self.assertEqual((tracks,timeline),original)
        self.assertEqual([s['source_pts'] for s in motion.samples],[f['source_pts'] for f in timeline])
        self.assertTrue(all(r['status']=='fitted' for r in motion.coordinate_registration['chunks']))

    def test_stop_and_noninteger_speed_ratio_remain_observed_instead_of_becoming_a_linear_clock(self):
        def phase(t):return 180*min(t,1)+180*1.73*max(0,t-1.3)
        tracks,timeline=self.scenario(phase)
        motion=registered_motion(tracks,timeline,400,40,40,380)
        self.assertFalse(motion.coordinate_failures)
        self.assertAlmostEqual(motion.distance(1001,1001.25),0,delta=.01)
        before=motion.distance(1000.5,1001)/.5
        after=motion.distance(1001.5,1002)/.5
        self.assertAlmostEqual(after/before,1.73,delta=.01)

    def test_disconnected_coordinates_fail_and_cannot_supply_distance(self):
        motion=ScrollMotion(400,40)
        motion.samples=[{'time':i/60,'source_pts':100+i/60,'chunk':0,'phase':4*i,'support':2} for i in range(12)]
        motion.chunks=[motion.samples];motion.at_time={s['time']:s for s in motion.samples}
        tracks=[Track(0,[(s['time'],200-4*i) for i,s in enumerate(motion.samples[:6])]),
                Track(1,[(s['time'],200-4*i) for i,s in enumerate(motion.samples[6:])])]
        original=deepcopy(tracks);refine(motion,tracks,40,40,380)
        self.assertEqual(motion.coordinate_failures[0],'disconnected_registered_identities')
        self.assertIsNone(motion.distance(0,11/60))
        self.assertTrue(all(s['coordinate_status']=='failed' for s in motion.samples))
        self.assertEqual(tracks,original)

    def test_robust_reference_retains_contradictory_native_positions_as_warnings(self):
        timeline=[{'time':i/60,'source_pts':100+i/60} for i in range(37)]
        tracks=[Track(lane,[(f['time'],180+20*lane-100*f['time']) for f in timeline]) for lane in range(4)]
        tracks.append(Track(4,[(f['time'],250) for f in timeline]))
        original=deepcopy(tracks);motion=registered_motion(tracks,timeline,400,40,40,380)
        self.assertTrue(any(r['note']==4 for r in motion.coordinate_conflicts))
        self.assertAlmostEqual(motion.distance(0,.6),60,delta=1.)
        self.assertTrue(all(r['reason']=='shared_motion_observation_conflict' for r in motion.coordinate_conflicts))
        self.assertEqual(tracks,original)
