"""Pure OCR parsing tests; real Vision checks are run separately on a host."""
import unittest
from .fixtures import glyph as line

from piu_timeline.metadata import recognition


class RecognitionTest(unittest.TestCase):
    def test_result_caption_typos_and_aligned_rows_still_identify_result(self):
        lines = [line("SCORE", .15, .345), line("PERFEST", .46, .42),
                 line("MAX COMBD", .45, .683)]
        self.assertTrue(recognition.is_result_screen(lines))
        self.assertFalse(recognition.is_result_screen([line("SCORE", .15, .345)]))
        rows = [line("123", .315, y - .01) for y in (.434, .487, .540)]
        self.assertTrue(recognition.is_result_screen([line("SCORE", .15, .345), *rows]))

    def test_result_anchors_do_not_need_the_animated_score_heading(self):
        rows = [line("123", .64, y - .01) for y in (.434, .487, .540)]
        caption = line("GOOD", .47, .527)
        self.assertEqual(recognition.scene_kind([caption, *rows]), "result")
        self.assertEqual(recognition.scene_kind(rows), "unknown")
        self.assertEqual(recognition.scene_kind([caption]), "unknown")

    def test_carousel_levels_are_browsing_not_a_selected_chart(self):
        levels = [line(str(10 + i), .1 + i * .13, .87) for i in range(6)]
        self.assertEqual(recognition.scene_kind(levels), "browse")
        self.assertIsNone(recognition.frame_labels(levels, "selection")["chart"])
        self.assertEqual(recognition.scene_kind(levels[:2]), "unknown")
        self.assertEqual(recognition.scene_kind([{**l, "box": [l["box"][0], .4, .05, .025]}
                                                for l in levels]), "unknown")

    def test_stage_hud_confusable_glyph_is_anchored_to_label(self):
        lines = [line("ISTAGE", .14, .005), line("0Ч", .14, .03)]
        self.assertEqual(recognition.stage_number(lines)["value"], 4)
        self.assertIsNone(recognition.stage_number(lines[1:]))

    def test_stage_break_taunts_and_game_over_are_distinct(self):
        first = [line(t, .25, y) for t, y in (("HEY!", .15), ("JHYDONTYDU", .3),
                                             ("JUST CETUPAND", .5), ("DANGEMANR", .7))]
        second = [line(t, .25, y) for t, y in (("HEY", .15), ("IS THS", .3),
                                              ("REALLY", .5), ("YDUR BESTH", .7))]
        self.assertTrue(recognition.is_stage_break(first))
        self.assertTrue(recognition.is_stage_break(second))
        self.assertEqual(recognition.scene_kind(first), "failure")
        self.assertFalse(recognition.is_stage_break([line("GAME OVER", .3, .4)]))

    def test_rival_badge_does_not_conflict_with_actual_chart(self):
        lines = [line("SINGLE", .31, .28), line("25", .31, .31),
                 line("SINGLE", .63, .28), line("23", .63, .31), line("RIVAL", .63, .015)]
        self.assertEqual(recognition.frame_labels(lines, "result")["chart"]["text"], "S25")
        self.assertEqual(recognition.rival_slots(lines), {"p2"})
        self.assertEqual(recognition.rival_slots([line("R I V A L", .63, .015)]), {"p2"})
        self.assertEqual(recognition.rival_slots([line("RIVAL", .63, .5)]), set())

    def test_left_player_and_conflicting_players(self):
        left = [line("DOUBLE", .31, .28), line("18", .31, .31)]
        self.assertEqual(recognition.frame_labels(left, "result")["chart"]["text"], "D18")
        right = [line("DOUBLE", .63, .28), line("23", .63, .31)]
        self.assertIsNone(recognition.frame_labels(left + right, "result")["chart"])
        basic = [line("VERY HARD", .31, .28), line("12", .31, .31)]
        self.assertEqual(recognition.frame_labels(basic, "result")["chart"]["text"], "VERY HARD 12")

    def test_result_title_and_chart_not_score(self):
        lines = [line("곡 이름", .4, .16, .2), line("DOUBLE", .63, .28),
                 line("23", .63, .31), line("99", .65, .42), line("SCORE", .78, .34)]
        result = recognition.frame_labels(lines, "result")
        self.assertEqual(result["song"]["text"], "곡 이름")
        self.assertEqual(result["chart"]["text"], "D23")

    def test_selection_uses_selected_circle_not_difficulty_row(self):
        lines = [line("선곡 제목", .4, .5, .2), line("SINGLE", .6, .77),
                 line("21", .6, .81), line("25", .6, .63)]
        result = recognition.frame_labels(lines, "selection")
        self.assertEqual(result["chart"]["text"], "S21")
        self.assertEqual(result["song"]["text"], "선곡 제목")

    def test_missing_chart_remains_unknown(self):
        self.assertIsNone(recognition.frame_labels([line("23", .63, .31)], "result")["chart"])

    def test_consensus_requires_two_and_rejects_ties(self):
        first = {"song": {"text": "Song", "confidence": .5}}
        second = {"song": {"text": "Other", "confidence": 1}}
        self.assertEqual(recognition.consensus([first], "song"), (None, None))
        self.assertEqual(recognition.consensus([first, first, second, second], "song"), (None, None))
        value, support = recognition.consensus([first, first, second], "song")
        self.assertEqual(value, "Song")
        self.assertEqual(support["supporting_frames"], 2)
        self.assertEqual(support["mean_ocr_confidence"], .5)

    def test_blank_and_background_text_not_title(self):
        self.assertIsNone(recognition.frame_labels([line("123", .4, .16), line("KCAL", .48, .73)], "result")["song"])

    def test_fail_screen_is_not_result_screen(self):
        self.assertFalse(recognition.is_result_screen([line("HEY!", .3, .15), line("DANCE MAN?", .3, .7)]))
        self.assertTrue(recognition.is_result_screen([line("SCORE", .7, .3), line("PERFECT", .5, .4)]))

    def test_mode_correction_is_bounded(self):
        self.assertEqual(recognition.chart_mode("DOUELE"), "D")
        self.assertEqual(recognition.chart_mode("OOUBLE"), "D")
        self.assertIsNone(recognition.chart_mode("TROUBLE"))
        self.assertIsNone(recognition.chart_mode("D"))

    def test_stage_number_uses_hud_label_and_supports_one_through_six(self):
        for value in range(1, 7):
            lines = [line("STAGE", .14, .01), line(f"{value:02}", .145, .045)]
            self.assertEqual(recognition.stage_number(lines)["value"], value)
        self.assertIsNone(recognition.stage_number([line("STAGE", .14, .01), line("07", .145, .045)]))
        self.assertIsNone(recognition.stage_number([line("03", .145, .045)]))
        self.assertIsNone(recognition.stage_number([line("STAGE", .14, .01), line("03", .4, .045)]))

    def test_spacing_consensus(self):
        value, support = recognition.consensus([
            {"song": {"text": "뱅 뱅", "confidence": .5}},
            {"song": {"text": "뱅뱅", "confidence": .5}},
        ], "song")
        self.assertIn(value, ("뱅 뱅", "뱅뱅"))
        self.assertEqual(support["supporting_frames"], 2)

    def test_similar_title_consensus_is_bounded_and_rejects_competition(self):
        def song(text, confidence=.8):
            return {"song": {"text": text, "confidence": confidence}}
        value, support = recognition.consensus([
            song("비코즈 오븐 유", .6), song("비코즈 오브 유", .9)], "song")
        self.assertEqual(value, "비코즈 오브 유")
        self.assertEqual(support["agreement"], "similar_title_ocr")
        self.assertEqual(recognition.consensus([song("Song A"), song("Song B")], "song"), (None, None))
        self.assertEqual(recognition.consensus([
            song("비코즈 오븐 유"), song("비코즈 오브 유"), song("전혀 다른 곡명"), song("전혀 다른 공명")], "song"),
            (None, None))
        self.assertEqual(recognition.consensus([song("ABC"), song("ABD")], "song"), (None, None))

    def test_small_single_option_chart(self):
        result = recognition.frame_labels([line("D", .14, .86, .02), line("25", .14, .9, .025)], "selection")
        self.assertEqual(result["chart"]["text"], "D25")

    def test_half_double_result_badge_is_distinct_from_double(self):
        lines = [line("H.DOUBLE", .65, .28), line("17", .65, .32)]
        self.assertEqual(recognition.frame_labels(lines, "result")["chart"]["text"], "HD17")
        self.assertEqual(recognition.chart_mode("HDOUBLE"), "HD")

    def test_summary_stage_row_disambiguates_repeated_charts(self):
        lines = [line("1ST", .48, .18), line("First", .4, .22, .2),
                 line("2ND", .48, .45), line("Second", .4, .49, .2),
                 line("DOUBLE", .72, .17), line("23", .72, .20),
                 line("DOUBLE", .72, .44), line("23", .72, .47)]
        self.assertEqual(recognition.summary_stage_row(lines, 2)["song"]["text"], "Second")
        self.assertIsNone(recognition.summary_stage_row(lines, None))

    def test_summary_stage_row_reads_chart_independently_of_selection(self):
        lines = [line("1ST", .48, .18), line("First", .4, .22, .2),
                 line("2ND", .48, .45), line("Die Another Day", .4, .49, .2),
                 line("DOUBLE", .72, .17), line("20", .72, .20),
                 line("DOUBLE", .72, .44), line("19", .72, .47)]
        row = recognition.summary_stage_row(lines, 2)
        self.assertEqual(row["song"]["text"], "Die Another Day")
        self.assertEqual(row["chart"]["text"], "D19")
        self.assertIsNone(recognition.summary_stage_row(lines, 3))

    def test_summary_title_survives_missing_chart_and_shifted_badge(self):
        title = [line("1ST", .48, .18), line("Song", .4, .22, .2)]
        row = recognition.summary_stage_row(title, 1)
        self.assertEqual(row["song"]["text"], "Song")
        self.assertIsNone(row["chart"])
        shifted = [line("DOUBLE", .80, .17), line("20", .80, .20)]
        row = recognition.summary_stage_row(title + shifted + shifted, 1)
        self.assertEqual(row["charts"]["p2"]["text"], "D20")

    def test_summary_left_and_two_player_charts_remain_separate(self):
        title = [line("1ST", .48, .18), line("Same Song", .4, .22, .2)]
        left = [line("SINGLE", .23, .17), line("18", .23, .20)]
        right = [line("DOUBLE", .72, .17), line("20", .72, .20)]
        row = recognition.summary_stage_row(title + left, 1)
        self.assertEqual(row["song"]["text"], "Same Song")
        self.assertEqual(row["chart"]["text"], "S18")
        row = recognition.summary_stage_row(title + left + right, 1)
        self.assertEqual(row["charts"]["p1"]["text"], "S18")
        self.assertEqual(row["charts"]["p2"]["text"], "D20")
        self.assertIsNone(row["chart"])

    def test_demo_marker_is_not_evidence_of_a_real_play(self):
        self.assertTrue(recognition.is_demo_screen([line("DEMO PLAY", .2, .94)]))
        self.assertEqual(recognition.scene_kind([line("DEMO PLAY", .2, .94)]), "demo")
        self.assertFalse(recognition.is_demo_screen([line("DEMO PLAY", .2, .5)]))


if __name__ == "__main__":
    unittest.main()
