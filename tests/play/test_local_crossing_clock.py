"""A block-average clock cannot veto a separately supported local crossing."""
from copy import deepcopy
import unittest

from piu_timeline.play.motion import ScrollMotion


def fixture(sparse=False):
    motion=ScrollMotion(400,40);motion.strict_clock=True;motion.chunks=[[]]
    for i in range(601):
        time=i/60
        if sparse and 5<time<6.02 and i not in (318,330,331):continue
        # A remote capture-phase discontinuity biases the block average, while
        # the target's neighborhood has a fully observed constant displacement.
        sample={'time':time,'source_pts':800+time,'phase':240*time+(9 if time>=5 else 0),
                'chunk':0,'variance':0,'support':2,'lanes':2}
        motion.chunks[0].append(sample);motion.samples.append(sample);motion.at_time[time]=sample
    return motion


class LocalCrossingClockTest(unittest.TestCase):
    def test_local_clock_keeps_observed_bracket_after_rejecting_remote_average(self):
        motion=fixture();original=deepcopy(motion.samples)
        result=motion.crossing(motion.at_time[5.3],240*5.516+9,.75)
        self.assertIsNotNone(result)
        self.assertEqual(result['fit_method'],'shared_scroll_clock')
        self.assertAlmostEqual(result['target_seconds'],5.516)
        self.assertEqual(result['crossing_frame_seconds'],[5.5,331/60])
        self.assertEqual(result['crossing_source_pts_seconds'],[805.5,800+331/60])
        lo,hi=result['crossing_capture_range']
        self.assertGreater(result['rejected_chunk_clock']['target_seconds'],hi)
        self.assertTrue(lo<=result['target_seconds']<=hi)
        self.assertGreater(result['motion_clock']['window'][0],5)
        self.assertEqual(motion.samples,original)

    def test_sparse_local_support_cannot_replace_the_rejected_block_average(self):
        motion=fixture(sparse=True)
        self.assertIsNotNone(motion._clock(motion.chunks[0]))
        self.assertIsNone(motion.crossing(motion.at_time[5.3],240*5.516+9,.75))

    def test_crossing_inside_the_remote_phase_discontinuity_remains_unresolved(self):
        motion=fixture()
        # The phase jump itself is not a measured constant-speed crossing.
        self.assertIsNone(motion.crossing(motion.at_time[4.8],1208,.75))
