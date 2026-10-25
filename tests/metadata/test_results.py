import copy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest

from piu_timeline.metadata import results as stats


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

    def test_dense_result_observations_need_only_six_numeric_reads(self):
        with tempfile.TemporaryDirectory() as temporary:
            observations = [{"file": f"{pts}.png", "source_pts_seconds": pts, "playback_seconds": pts,
                             "phase": "result", "eligible_screen": True,
                             "ocr": result_lines() + [line("PERFECT", .5, .4)]}
                            for pts in range(100)]
            original = copy.deepcopy(observations)
            with patch.object(stats, "focused_stats", return_value=result_lines()) as focused:
                result = stats.extract_stats(observations, Path(temporary), 1300, 730)
                repeated = stats.extract_stats(observations, Path(temporary), 1300, 730)
            self.assertEqual(focused.call_count, 6)
            frames = json.loads((Path(temporary) / "frames.json").read_text())
            self.assertEqual([f["source_pts_seconds"] for f in frames], [0, 20, 40, 59, 79, 99])
            self.assertEqual(observations, original)
            self.assertEqual(result, repeated)
            self.assertEqual(result["players"]["p2"]["score"], 987654)

    def test_visual_layout_never_copies_a_rival_or_result_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw = result_lines("left", 100) + result_lines("right", 200) + [line("RIVAL", .72, .02)]
            observations = [{"file": f"{pts}.png", "source_pts_seconds": pts, "phase": "result",
                             "eligible_screen": True, "ocr": [], "screen_ocr": [],
                             "scene_routing": {"method": "visual_template", "source": "template.png"}}
                            for pts in (1, 2)]
            with patch.object(stats, "screen_lines", return_value=raw) as direct, \
                    patch.object(stats, "focused_stats", return_value=result_lines("left", 100) + result_lines("right", 200)):
                result = stats.extract_stats(observations, Path(temporary), 1300, 730)
            self.assertEqual(direct.call_count, 2)
            self.assertIn("p1", result["players"])
            self.assertNotIn("p2", result["players"])
            self.assertEqual(result["players"]["p1"]["perfect"], 100)

    def test_result_entrance_animation_does_not_consume_numeric_reads(self):
        with tempfile.TemporaryDirectory() as temporary:
            markers = [line("SCORE", .815, .36), line("PERFECT", .5, .434)]
            observations = [{"file": f"{pts}.png", "source_pts_seconds": pts, "phase": "result",
                             "eligible_screen": True, "ocr": markers if pts < 8 else result_lines() + markers}
                            for pts in range(10)]
            with patch.object(stats, "focused_stats", return_value=result_lines()) as focused:
                result = stats.extract_stats(observations, Path(temporary), 1300, 730)
            self.assertEqual(focused.call_count, 2)
            self.assertEqual(result["players"]["p2"]["score"], 987654)

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

    def test_new_short_result_combines_with_retained_frame_without_reprocessing(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            parsed = stats.parse_result(result_lines())
            old = {"file": "old.png", "source_pts_seconds": 1, "players": parsed}
            saved = directory / "frames.json"
            saved.write_text(json.dumps([old]))
            observations = [{"file": f"{pts}.png", "source_pts_seconds": pts, "phase": "result",
                             "eligible_screen": True, "ocr": result_lines() + [line("PERFECT", .5, .4)]}
                            for pts in (1, 2)]
            with patch.object(stats, "focused_stats", return_value=result_lines()) as focused:
                result = stats.extract_stats(observations, directory, 1300, 730)
                repeated = stats.extract_stats(observations, directory, 1300, 730)
            focused.assert_called_once()
            self.assertEqual(result["players"]["p2"]["score"], 987654)
            self.assertEqual(repeated, result)
            self.assertEqual(len(json.loads(saved.read_text())), 2)

    def test_retained_ocr_can_resolve_a_newly_supported_chart_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            lines = result_lines()
            lines[0]["text"], lines[1]["text"] = "HDOUBLE", "17"
            parsed = stats.parse_result(lines)
            parsed["p2"]["fields"]["chart"] = None
            (directory / "frames.json").write_text(json.dumps([{
                "file": "retained.png", "source_pts_seconds": pts, "players": parsed, "ocr": lines}
                for pts in (1, 2)]))
            with patch.object(stats, "focused_stats") as focused:
                result = stats.extract_stats([], directory, 1300, 730)
            focused.assert_not_called()
            self.assertEqual(result["players"]["p2"]["chart"], "HD17")

    def test_caption_context_resolves_rotated_digit_conflict(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            upright = result_lines()
            rotated = copy.deepcopy(upright)
            rotated[-1]["text"] = "4567890"
            frames = [{"file": "existing.png", "source_pts_seconds": pts,
                       "ocr": lines, "players": stats.parse_result(lines)}
                      for pts, lines in ((1, upright), (2, rotated))]
            (directory / "frames.json").write_text(json.dumps(frames))
            with patch.object(stats, "contextual_stats", return_value=upright) as contextual:
                result = stats.extract_stats([], directory, 1300, 730)
                again = stats.extract_stats([], directory, 1300, 730)
            self.assertEqual(contextual.call_count, 2)
            self.assertEqual(result["players"]["p2"]["score"], 987654)
            self.assertEqual(result, again)
            self.assertEqual(result["players"]["p2"]["fields"]["score"]["method"], "caption_context_ocr")

    def test_life_loss_does_not_claim_missing_visible_statistics(self):
        with tempfile.TemporaryDirectory() as temporary:
            frames = [{"window": "result", "identity_eligible": True, "source_pts_seconds": pts,
                       "file": "failure.png", "ocr": [line("HEY", .5, .15), line("IS THIS", .5, .3),
                                                       line("REALLY", .5, .5), line("YOUR BEST", .5, .7)]}
                      for pts in (1, 2)]
            result = stats.extract_stats(frames, Path(temporary), 1300, 730)
            self.assertEqual(result["status"], "not_displayed")
            self.assertFalse(result["needs_review"])
            self.assertEqual(result["players"], {})

    def test_recovery_ocr_is_bounded_across_a_long_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            upright = result_lines()
            rotated = copy.deepcopy(upright)
            rotated[-1]["text"] = "4567890"
            frames = [{"file": "existing.png", "source_pts_seconds": pts,
                       "ocr": lines, "players": stats.parse_result(lines)}
                      for pts, lines in ((i, upright if i % 2 else rotated) for i in range(20))]
            (directory / "frames.json").write_text(json.dumps(frames))
            with patch.object(stats, "contextual_stats", return_value=upright) as contextual:
                result = stats.extract_stats([], directory, 1300, 730)
            self.assertLessEqual(contextual.call_count, 6)
            self.assertEqual(result["players"]["p2"]["score"], 987654)
            retained = json.loads((directory / "frames.json").read_text())
            self.assertEqual([f["source_pts_seconds"] for f in retained], list(range(20)))

    def test_agreed_rotated_numbers_are_checked_against_upright_screen(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            upright = result_lines()
            rotated = copy.deepcopy(upright)
            rotated[-1]["text"] = "4567890"
            frames = [{"file": "existing.png", "source_pts_seconds": pts, "source_ocr": upright,
                       "ocr": rotated, "players": stats.parse_result(rotated)} for pts in (1, 2)]
            (directory / "frames.json").write_text(json.dumps(frames))
            with patch.object(stats, "contextual_stats", return_value=upright) as contextual:
                result = stats.extract_stats([], directory, 1300, 730)
            self.assertEqual(contextual.call_count, 2)
            self.assertEqual(result["players"]["p2"]["score"], 987654)

    def test_two_established_numeric_panels_can_use_one_shared_badge(self):
        lines = result_lines("left", 100) + result_lines("right", 200)[2:]
        parsed = stats.parse_result(lines)
        self.assertEqual(parsed["p2"]["fields"]["chart"]["value"], "D23")
        self.assertEqual(parsed["p2"]["fields"]["chart"]["shared_from"], "p1")
        self.assertEqual(parsed["p2"]["fields"]["perfect"]["value"], 200)
        # A visible separate mode whose digits failed is still unresolved.
        separate = stats.parse_result(lines + [line("SINGLE", .665, .295)])
        self.assertIsNone(separate["p2"]["fields"]["chart"])

    def test_score_contrast_channel_requires_repeated_source_frames(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            upright = result_lines()
            letters = copy.deepcopy(upright)
            letters[-1]["text"] = "2hEh260"
            (directory / "frames.json").write_text(json.dumps([
                {"file": "existing.png", "source_pts_seconds": pts, "ocr": letters,
                 "players": stats.parse_result(letters)} for pts in (1, 2)]))
            with patch.object(stats, "contextual_stats", return_value=letters), \
                 patch.object(stats, "contrast_score", return_value=upright) as contrast:
                result = stats.extract_stats([], directory, 1300, 730)
                repeated = stats.extract_stats([], directory, 1300, 730)
            self.assertEqual(contrast.call_count, 2)
            self.assertEqual(result, repeated)
            self.assertEqual(result["players"]["p2"]["score"], 987654)
            self.assertEqual(result["players"]["p2"]["fields"]["score"]["method"], "caption_contrast_ocr")

    def test_rival_score_panel_is_not_a_participant(self):
        lines = result_lines("left", 100) + result_lines("right", 200)
        parsed = stats.parse_result(lines + [line("RIVAL", .665, .03)])
        self.assertTrue(parsed["p1"]["present"])
        self.assertFalse(parsed["p2"]["present"])
        self.assertEqual(parsed["p2"]["role"], "rival")
        result = stats.aggregate_frames([{"players": parsed}] * 2)
        self.assertEqual(set(result["players"]), {"p1"})
        # Without the header, both independent numeric panels remain players.
        self.assertTrue(stats.parse_result(lines)["p2"]["present"])

    def test_no_result_remains_unknown(self):
        result = stats.aggregate_frames([])
        self.assertEqual(result["players"], {})
        self.assertTrue(result["needs_review"])


if __name__ == "__main__":
    unittest.main()
