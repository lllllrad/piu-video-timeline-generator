import unittest
from copy import deepcopy

from piu_timeline.play.tracking import Track, fit_track
from piu_timeline.play.fragments import stitch_tracks


class FragmentTest(unittest.TestCase):
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
