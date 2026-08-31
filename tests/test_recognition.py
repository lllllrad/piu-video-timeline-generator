"""Pure OCR parsing tests; real Vision checks are run separately on a host."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("recognition", ROOT / "scripts/recognition.py")
recognition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recognition)


def line(text, x, y, width=.05, height=.025, confidence=1):
    return {"text": text, "box": [x, y, width, height], "confidence": confidence}


class RecognitionTest(unittest.TestCase):
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

    def test_spacing_consensus(self):
        value, support = recognition.consensus([
            {"song": {"text": "뱅 뱅", "confidence": .5}},
            {"song": {"text": "뱅뱅", "confidence": .5}},
        ], "song")
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

    def test_summary_chart_matches_song_not_another_row(self):
        lines = [line("Song A", .4, .22, .2), line("Song B", .4, .49, .2),
                 line("DOUBLE", .72, .17), line("21", .72, .20),
                 line("DOUBLE", .72, .44), line("25", .72, .47)]
        self.assertEqual(recognition.summary_chart(lines, "Song B")["text"], "D25")
        self.assertIsNone(recognition.summary_chart(lines, "Unknown"))

    def test_summary_song_uses_unique_known_chart(self):
        lines = [line("First", .4, .22, .2), line("Hidden title", .4, .49, .2),
                 line("DOUBLE", .72, .17), line("21", .72, .20),
                 line("DOUBLE", .72, .44), line("24", .72, .47)]
        self.assertEqual(recognition.summary_song(lines, "D24")["text"], "Hidden title")
        duplicate = lines + [line("Another", .4, .72, .2), line("DOUBLE", .72, .67), line("24", .72, .70)]
        self.assertIsNone(recognition.summary_song(duplicate, "D24"))


if __name__ == "__main__":
    unittest.main()
