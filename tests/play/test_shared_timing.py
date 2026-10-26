"""Song-independent geometry, clock support and explicit reconstruction failure."""
import unittest
import math
from copy import deepcopy

from piu_timeline.play.tracking import Track, fit_track
from piu_timeline.play.shared_timing import restore
from piu_timeline.play.spacing_checks import spacing_failures

LAYOUT={'receptor_y':.1,'note_y_max':.95,'lanes':[{'x':.1+.15*i} for i in range(5)]}


def scenario():
    timeline=[{'time':i/60,'source_pts':100+i/60} for i in range(150)]
    tracks=[Track(i%5,[(f['time'],40+240*(target-f['time'])) for f in timeline
                         if 80<40+240*(target-f['time'])<350])
            for i,target in enumerate([.7+.125*i for i in range(12)])]
    notes=[fit_track(t,40,40) for t in tracks]
    return tracks,notes,timeline


class SharedTimingTest(unittest.TestCase):
    def test_equal_spacing_uses_registered_peer_clock_and_original_times(self):
        tracks,notes,timeline=scenario();original=deepcopy(tracks)
        motion,result=restore(notes,tracks,timeline,LAYOUT,400,400)
        restored=[n for n in notes if n['status']=='estimated']
        self.assertGreater(len(restored),5)
        for n in restored:self.assertAlmostEqual(n['target_seconds'],.7+.125*notes.index(n),delta=.012)
        for a,b in zip(restored,restored[1:]):self.assertAlmostEqual(b['target_seconds']-a['target_seconds'],.125,delta=.001)
        self.assertEqual(tracks,original)
        self.assertEqual(motion.samples[0]['source_pts'],100.)

    def test_missing_shared_support_is_a_failed_result_without_local_fallback(self):
        tracks,notes,timeline=scenario()
        # Competing tracks move differently, so no common displacement exists.
        for i,track in enumerate(tracks):track.points=[(t,y+20*i*t) for t,y in track.points]
        motion,result=restore(notes,tracks,timeline,LAYOUT,400,400)
        self.assertEqual(result['status'],'failed')
        self.assertTrue(result['warnings'])
        for record in result['warnings']:
            note=notes[record['note']]
            self.assertEqual(note['status'],'excluded')
            self.assertIsNone(note['target_seconds'])
            self.assertEqual(note['timing_reconstruction']['status'],'failed')

    def test_isolated_observed_track_has_explicit_standalone_provenance(self):
        tracks,notes,timeline=scenario();tracks=tracks[:1];notes=notes[:1]
        _,result=restore(notes,tracks,timeline,LAYOUT,400,400)
        self.assertEqual(notes[0]['fit_method'],'isolated_native_track')
        self.assertEqual(result['status'],'restored')

    def test_small_clock_disagreement_is_checked_in_measured_pixel_units(self):
        tracks,notes,timeline=scenario()
        for i,n in enumerate(notes):n.update(fit_method='shared_scroll_clock',motion_clock={'velocity':240},target_seconds=.7+.125*i)
        self.assertEqual(spacing_failures(notes,40),[])
        notes[3]['target_seconds']+=.05
        conflicts=spacing_failures(notes,40)
        self.assertTrue(any(r['note']==3 for r in conflicts))

    def test_large_recording_timestamp_does_not_turn_boundary_roundoff_into_conflict(self):
        tracks,notes,_=scenario()
        for i,n in enumerate(notes):
            n.update(fit_method='shared_scroll_clock',motion_clock={'velocity':240},target_seconds=1000+.125*i)
        # One physical pixel is admissible. Subtracting large source times
        # introduces a few picopixels of floating-point error at this boundary.
        notes[1]['target_seconds']=1000+29/240
        self.assertEqual(spacing_failures(notes,40),[])
        notes[1]['target_seconds']-=.001/240
        self.assertTrue(spacing_failures(notes,40))

    def test_corroborated_identity_carries_short_peer_loss_without_filling_empty_frames(self):
        from piu_timeline.play.shared_timing import registered_motion
        timeline=[{'time':i/60,'source_pts':100+i/60} for i in range(61)]
        first=Track(0,[(f['time'],300-120*f['time']) for f in timeline])
        peer=Track(1,[(f['time'],280-120*f['time']) for f in timeline if f['time']<=.5])
        motion=registered_motion([first,peer],timeline,400,40,40,380)
        self.assertAlmostEqual(motion.distance(.5,.7),24)
        self.assertEqual(motion.at_time[.7]['displacement_basis'],'registered_identity_continuation')
        self.assertEqual(motion.at_time[.7]['source_pts'],100.7)
        self.assertIsNone(motion.distance(.5,.8))
        alone=registered_motion([first],timeline,400,40,40,380)
        self.assertIsNone(alone.distance(.5,.7))
        first.points=[p for p in first.points if p[0]!=.6]
        broken=registered_motion([first,peer],timeline,400,40,40,380)
        self.assertIsNone(broken.distance(.5,.7))

    def test_simultaneous_heads_leaving_detector_boundary_keep_a_bounded_shared_clock(self):
        layout={'receptor_y':.1,'note_y_max':.95,'lanes':[{'x':.1+.1*i} for i in range(5)]}
        timeline=[{'time':i/60,'source_pts':800+i/60} for i in range(73)]
        tracks=[Track(lane,[(f['time'],280-240*f['time']) for f in timeline if f['time']<=.85]) for lane in (0,4)]
        notes=[fit_track(track,40,40) for track in tracks]
        _,result=restore(notes,tracks,timeline,layout,400,400)
        self.assertEqual(result['status'],'restored')
        for note in notes:
            self.assertEqual(note['fit_method'],'shared_scroll_clock_extrapolation')
            self.assertAlmostEqual(note['target_seconds'],1)
            self.assertGreater(note['extrapolation_seconds'],0)
            self.assertAlmostEqual(note['crossing_source_pts_seconds'][0]-note['crossing_frame_seconds'][0],800)
        # A clipped source, a recording gap or a changed velocity is not an
        # authorization to project the same chord through missing evidence.
        for clipped in (timeline[:55],[f for f in timeline if not .87<f['time']<.99]):
            rejected=[fit_track(track,40,40) for track in tracks]
            restore(rejected,tracks,clipped,layout,400,400)
            self.assertTrue(all(n['status']=='excluded' for n in rejected))
        unstable=[Track(t.lane,[(time,y+12*math.sin(20*time)) for time,y in t.points]) for t in tracks]
        rejected=[fit_track(track,40,40) for track in unstable]
        restore(rejected,unstable,timeline,layout,400,400)
        self.assertTrue(all(n['status']=='excluded' for n in rejected))

    def test_new_motion_after_the_target_does_not_invalidate_the_preceding_clock(self):
        layout={'receptor_y':.1,'note_y_max':.95,'lanes':[{'x':.1+.1*i} for i in range(5)]}
        timeline=[{'time':i/60,'source_pts':800+i/60} for i in range(73)]
        heads=[Track(lane,[(f['time'],40+240*(1.008-f['time'])) for f in timeline if f['time']<=.85]) for lane in (0,4)]
        for start,expected in ((1.,'estimated'),(.9,'excluded')):
            following=[Track(lane,[(f['time'],300-240*(f['time']-start)) for f in timeline if f['time']>=start]) for lane in (1,2)]
            tracks=heads+following;notes=[fit_track(t,40,40) for t in tracks]
            restore(notes,tracks,timeline,layout,400,400)
            self.assertEqual([n['status'] for n in notes[:2]],[expected,expected])
            if expected=='estimated':
                self.assertAlmostEqual(notes[0]['target_seconds'],1.008)
                self.assertLess(notes[0]['target_seconds'],notes[0]['crossing_frame_seconds'][1])

    def test_short_peer_loss_preserves_clock_only_with_confirming_native_head_positions(self):
        layout={'receptor_y':.1,'note_y_max':.95,'lanes':[{'x':.1+.1*i}for i in range(5)]}
        timeline=[{'time':i/60,'source_pts':800+i/60}for i in range(73)]
        from piu_timeline.play.shared_timing import registered_motion
        for delta,expected in ((0,True),(12,False)):
            head=Track(0,[(f['time'],284.8-240*f['time']+(delta if f['time']>.85 else 0))
                          for f in timeline if f['time']<=.88])
            peer=Track(4,[(f['time'],284.8-240*f['time'])for f in timeline if f['time']<=.6])
            motion=registered_motion([head,peer],timeline,400,40,40,380);motion.strict_clock=True
            before=deepcopy(head.points);result=motion.fit(head,40,layout)
            self.assertEqual(result is not None,expected)
            if result:
                self.assertAlmostEqual(result['target_seconds'],1.02)
                self.assertGreater(result['validated_later_observations'],0)
                self.assertEqual(result['fit_method'],'shared_scroll_clock_extrapolation')
            self.assertEqual(head.points,before)
        # A fresh independently supported block, including a changed speed,
        # cannot be replaced by the older clock.
        following=[Track(lane,[(f['time'],300-300*(f['time']-.86))for f in timeline if f['time']>=.86])
                   for lane in (1,2)]
        head=Track(0,[(f['time'],284.8-240*f['time'])for f in timeline if f['time']<=.88])
        motion=registered_motion([head,peer]+following,timeline,400,40,40,380);motion.strict_clock=True
        self.assertIsNone(motion.fit(head,40,layout))
