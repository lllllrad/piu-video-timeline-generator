import unittest

from piu_timeline.play.skins.partial_caps import persistent


class PartialCapTest(unittest.TestCase):
    def test_dense_positions_require_unique_matches_on_both_sides(self):
        def frame(*positions):
            return [{'y': position / 365} for position in positions]
        before, current, after = frame(100,114,128), frame(99,113,127), frame(98,112,126)
        self.assertEqual(persistent([before,current,after],365),current)
        self.assertEqual(persistent([frame(100,102,114,128),current,after],365),[])
        self.assertEqual(persistent([before,current,frame(98,112)],365),[])
        self.assertEqual(persistent([before,current,frame(105,119,133)],365),[])
