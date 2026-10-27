"""Coordinate transfer needs shared identities and intact native observations."""
from copy import deepcopy
import unittest

from piu_timeline.play.motion import ScrollMotion


def fixture(ratio=1):
    motion=ScrollMotion(400,40);motion.strict_clock=True
    motion.chunks=[[],[],[]];positions={}
    for i in range(85):
        t=i/60;chunk=0 if i<=30 else 1 if i<34 else 2
        phase=240*t if chunk==0 else 0 if chunk==1 else 240*ratio*(t-34/60)
        global_phase=240*t if i<34 else 240*34/60+phase
        sample={'time':t,'source_pts':800+t,'phase':phase,'variance':0,'chunk':chunk,'support':2,'lanes':2}
        motion.samples.append(sample);motion.chunks[chunk].append(sample);motion.at_time[t]=sample
        positions[t]={j:(j,offset-global_phase)for j,offset in enumerate((280,340))}
    motion.registered_positions=positions
    motion.coordinate_registration={'chunks':[{'chunk':c,'status':'fitted','head_offsets':[
        {'note':j,'offset_pixels':offset-(0 if c==0 else 240*34/60)}for j,offset in enumerate((280,340))]}
        for c in (0,2)]}
    return motion


class MotionBridgeTest(unittest.TestCase):
    def test_uses_destination_velocity_and_retains_native_brackets(self):
        for ratio in (1,2):
            motion=fixture(ratio);original=deepcopy(motion.registered_positions)
            result=motion.crossing(motion.at_time[.45],144,.75)
            self.assertIsNotNone(result)
            self.assertAlmostEqual(result['target_seconds'],34/60+(144-240*34/60)/(240*ratio))
            self.assertEqual(result['fit_method'],'shared_scroll_registered_block_transfer')
            self.assertEqual(result['coordinate_bridge']['anchor_notes'],[0,1])
            self.assertAlmostEqual(result['crossing_source_pts_seconds'][0]-result['crossing_frame_seconds'][0],800)
            self.assertEqual(motion.registered_positions,original)

    def test_missing_frames_single_anchor_and_inconsistent_offsets_cannot_transfer(self):
        for kind in ('capture_gap','missing_position','one_anchor','wrong_offset'):
            motion=fixture()
            if kind=='capture_gap':motion.samples=[s for s in motion.samples if not .5<s['time']<34/60]
            if kind=='missing_position':motion.registered_positions[32/60]={}
            if kind=='one_anchor':motion.coordinate_registration['chunks'][1]['head_offsets'].pop()
            if kind=='wrong_offset':motion.coordinate_registration['chunks'][1]['head_offsets'][1]['offset_pixels']+=8
            with self.subTest(kind=kind):self.assertIsNone(motion.crossing(motion.at_time[.45],144,.75))

    def test_processing_pixels_follow_the_transferred_phase_and_velocity(self):
        from piu_timeline.play.processing.motion import observed_path
        motion=fixture(2);result=motion.crossing(motion.at_time[.45],144,.75)
        note={**result,'lane':0,'points':[(t,40+240*(.6-t))for t in (.2,.3,.4,.45)],
              'motion_target_phase':144,'motion_chunk':0,'velocity_pixels_per_second':-240,
              'timing_reconstruction':{'status':'restored'}}
        path=observed_path(note,{'scroll_motion':motion.evidence()},40,40,1)
        self.assertEqual(path['basis'],'registered_native_displacement')
        self.assertAlmostEqual(path['velocity'],-480)
        self.assertAlmostEqual(path['position'](.4),88)
        self.assertAlmostEqual(path['position'](35/60),40)
        self.assertIsNone(path['position'](32/60))
