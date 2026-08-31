import copy
import unittest

from piu_timeline import result_stats as stats


def line(text, cx, cy, width=.03, height=.02):
    return {"text": text, "confidence": 1., "box": [cx - width / 2, cy - height / 2, width, height]}


def result_lines(side="right", base=100):
    cx = .665 if side == "right" else .335
    lines = [line("DOUBLE", cx, .295), line("23", cx, .33)]
    lines += [line(str(base + i).zfill(3), cx, y) for i, y in enumerate(stats.ROW_Y.values())]
    lines += [line("SCORE", .815 if side == "right" else .185, .36),
              line("0987654", .815 if side == "right" else .185, .414)]
    return lines


class ResultStatsTest(unittest.TestCase):
    def test_per_player_numbers_do_not_mix_or_become_chart_levels(self):
        parsed = stats.parse_result(result_lines("left", 100) + result_lines("right", 200))
        self.assertEqual(parsed["p1"]["fields"]["perfect"]["value"], 100)
        self.assertEqual(parsed["p2"]["fields"]["perfect"]["value"], 200)
        self.assertEqual(parsed["p1"]["fields"]["score"]["value"], 987654)
        self.assertEqual(parsed["p2"]["fields"]["chart"]["value"], "D23")

    def test_stray_digits_do_not_establish_a_player(self):
        parsed = stats.parse_result([line("123", .665, .434)])
        self.assertFalse(parsed["p2"]["present"])

    def test_missing_zero_and_invalid_glyph_are_distinct(self):
        self.assertEqual(stats.number_at([line("000", .665, .434)], .665, .434, .04, .02, 999)["value"], 0)
        for text in ("OOO", "-1", "+12", "12.3", "1,200"):
            self.assertIsNone(stats.number_at([line(text, .665, .434)], .665, .434, .04, .02, 999))

    def test_consensus_and_uncertain_presence(self):
        parsed = stats.parse_result(result_lines())
        first = stats.aggregate_frames([{"players": parsed}])
        self.assertEqual(first["players"]["p2"]["presence"], "uncertain")
        self.assertIsNone(first["players"]["p2"]["perfect"])
        result = stats.aggregate_frames([{"players": parsed}, {"players": parsed}])
        self.assertEqual(result["players"]["p2"]["perfect"], 100)
        self.assertNotIn("p1", result["players"])
        different = copy.deepcopy(parsed)
        different["p2"]["fields"]["perfect"]["value"] = 999
        result = stats.aggregate_frames([{"players": parsed}, {"players": different}])
        self.assertEqual(result["players"]["p2"]["fields"]["perfect"]["status"], "conflict")
        self.assertIsNone(result["players"]["p2"]["perfect"])

    def test_no_result_remains_unknown(self):
        result = stats.aggregate_frames([])
        self.assertEqual(result["players"], {})
        self.assertTrue(result["needs_review"])


if __name__ == "__main__":
    unittest.main()
