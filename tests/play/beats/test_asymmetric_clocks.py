"""A nearby stop cannot erase a fully observed moving crossing on either side."""
from copy import deepcopy
import unittest

from piu_timeline.play.motion import ScrollMotion


def stopped_motion():
    motion=ScrollMotion(400,40);motion.strict_clock=True;motion.chunks=[[]]
    for i in range(121):
        time=i/60;pause=min(.1,max(0,time-1.))
        sample={'time':time,'source_pts':800+time,'phase':240*(time-pause),
                'chunk':0,'variance':0,'support':2,'lanes':2}
        motion.samples.append(sample);motion.chunks[0].append(sample);motion.at_time[time]=sample
    return motion


class AsymmetricClockTest(unittest.TestCase):
    def test_full_bracket_can_be_near_either_end_of_an_observed_constant_speed_window(self):
        for target,pause in ((.95,0),(1.15,.1)):
            motion=stopped_motion();original=deepcopy(motion.samples)
            self.assertIsNone(motion._clock(motion.chunks[0]))
            sample=min(motion.samples,key=lambda s:abs(s['time']-(target-.05)))
            result=motion.crossing(sample,240*(target-pause),.75)
            with self.subTest(target=target):
                self.assertIsNotNone(result)
                self.assertLessEqual(abs(result['target_seconds']-target)*240,.75)
                self.assertLessEqual(result['motion_clock']['residual'],.75)
                lo,hi=result['motion_clock']['window']
                if pause:self.assertGreaterEqual(lo,1.1-1/60-1e-8)
                else:self.assertLessEqual(hi,1.+1/60+1e-8)
                before,after=result['crossing_frame_seconds']
                self.assertLessEqual(lo,before);self.assertGreaterEqual(hi,after)
                self.assertGreaterEqual(hi-lo,.3)
                self.assertEqual(result['crossing_source_pts_seconds'],[800+before,800+after])
                self.assertEqual(motion.samples,original)

    def test_missing_source_frames_inside_the_crossing_cannot_be_bridged_by_a_flank(self):
        motion=stopped_motion()
        motion.samples=[s for s in motion.samples if not .85<s['time']<1.04]
        motion.chunks=[motion.samples];motion.at_time={s['time']:s for s in motion.samples}
        self.assertIsNone(motion.crossing(motion.at_time[.8],240*.95,.75))
