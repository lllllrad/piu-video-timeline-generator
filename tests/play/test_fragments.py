import unittest
from copy import deepcopy

from piu_timeline.play.tracking import Track, fit_track
from piu_timeline.play.fragments import stitch_tracks


class FragmentTest(unittest.TestCase):
    def test_hud_shifted_centers_do_not_override_the_intact_approach(self):
        layout = {'receptor_y': .1, 'note_y_max': .95, 'combo_roi': [.4, .5, .2, .1],
                  'lanes': [{'x': .5}]}
        points = [(i*.025, 430-400*i*.025+(8 if i*.025 >= .3 else 0)) for i in range(17)]
        first = Track(0, points)
        second = Track(0, [(t, 430-400*t) for t in (.7, .72, .74, .76, .78, .8, .82)])
        original = deepcopy([first, second])
        result = stitch_tracks([first, second], 50, 40, layout=layout)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0].points, points+second.points)
        self.assertEqual([first, second], original)
        # A competing continuation keeps the gap unresolved.
        competitor = Track(0, [(t, y+1) for t, y in second.points])
        self.assertEqual(len(stitch_tracks([first, second, competitor], 50, 40, layout=layout)), 3)

    def test_head_hidden_between_two_linear_native_observations_is_recovered(self):
        # The first part is too far from the receptor; the last three points
        # cannot independently establish a trajectory. Their shared path can.
        tracks = [Track(0, [(i*.02, 230-300*i*.02) for i in range(8)]),
                  Track(0, [(t, 230-300*t) for t in (.4, .42, .44)])]
        original = deepcopy(tracks)
        self.assertTrue(all(fit_track(t, 50, 40)['status'] == 'excluded' for t in tracks))
        result = stitch_tracks(tracks, 50, 40)
        self.assertEqual(len(result), 1)
        fitted = fit_track(result[0][0], 50, 40)
        self.assertEqual(fitted['status'], 'estimated')
        self.assertAlmostEqual(fitted['target_seconds'], .6)
        self.assertEqual(result[0][1], [0, 1])
        self.assertEqual(result[0][0].points, tracks[0].points+tracks[1].points)
        self.assertEqual(tracks, original)

    def test_different_head_and_competing_paths_are_not_joined(self):
        first = Track(0, [(i*.02, 230-300*i*.02) for i in range(8)])
        other = Track(0, [(t, 290-300*t) for t in (.4, .42, .44)])
        self.assertEqual(len(stitch_tracks([first, other], 50, 40)), 2)
        continuation = Track(0, [(t, 230-300*t) for t in (.4, .42, .44)])
        duplicate = Track(0, [(t, 231-300*t) for t in (.4, .42, .44)])
        self.assertEqual(len(stitch_tracks([first, continuation, duplicate], 50, 40)), 3)

    def test_other_lane_and_long_time_gap_do_not_establish_continuity(self):
        first = Track(0, [(i*.02, 230-300*i*.02) for i in range(8)])
        for other in (Track(1, [(t, 230-300*t) for t in (.4, .42, .44)]),
                      Track(0, [(t, 230-300*t) for t in (.6, .62, .64)])):
            self.assertEqual(len(stitch_tracks([first, other], 50, 40)), 2)

    def test_native_frame_interleaving_requires_unique_registered_identity(self):
        from piu_timeline.play.fragments import interleaved_tracks
        from piu_timeline.play.shared_timing import registered_motion
        timeline=[{'time':i/60,'source_pts':100+i/60} for i in range(80)]
        first=Track(0,[(f['time'],300-240*f['time']) for f in timeline if f['time']<=.3 or abs(f['time']-1/3)<1e-6])
        second=Track(0,[(f['time'],300-240*f['time']) for f in timeline if .3<f['time']<1 and abs(f['time']-1/3)>1e-6])
        peers=[Track(lane,[(f['time'],330-240*f['time']) for f in timeline]) for lane in (1,2)]
        tracks=[first,second,*peers];original=deepcopy(tracks)
        motion=registered_motion(tracks,timeline,400,40,40,380)
        joined,origins=interleaved_tracks(tracks,40,motion)
        self.assertEqual(len(joined),3)
        self.assertEqual(origins[0],[0,1])
        self.assertEqual(joined[0].points,sorted(first.points+second.points))
        self.assertEqual(tracks,original)
        reversed_tracks=[second,first,*peers]
        reversed_joined,reversed_origins=interleaved_tracks(reversed_tracks,40,motion)
        self.assertEqual(len(reversed_joined),3)
        self.assertEqual(reversed_origins[0],[1,0])
        self.assertEqual(len(interleaved_tracks(tracks,40,None)[0]),4)
        competitor=Track(0,[(t,y+1) for t,y in second.points])
        self.assertEqual(len(interleaved_tracks([*tracks,competitor],40,motion)[0]),5)
        simultaneous=Track(0,second.points+[(first.points[-1][0],first.points[-1][1]+1)])
        simultaneous.points.sort()
        self.assertEqual(len(interleaved_tracks([first,simultaneous,*peers],40,motion)[0]),4)
        different=Track(0,[(t,y+40) for t,y in second.points])
        self.assertEqual(len(interleaved_tracks([first,different,*peers],40,motion)[0]),4)

    def test_supported_first_fragment_can_rejoin_its_unique_later_appearance(self):
        first=Track(0,[(i*.02,260-300*i*.02) for i in range(26)])
        second=Track(0,[(t,260-300*t) for t in (.55,.57,.59,.61)])
        self.assertEqual(fit_track(first,50,40)['status'],'estimated')
        joined=stitch_tracks([first,second],50,40)
        self.assertEqual(len(joined),1)
        self.assertEqual(joined[0][0].points,first.points+second.points)
        self.assertEqual(joined[0][1],[0,1])
