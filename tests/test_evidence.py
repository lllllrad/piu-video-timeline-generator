import unittest

from piu_timeline.evidence import resolve_labels, resolve_players, reconcile_sessions
from piu_timeline.recognition import is_result_screen, scene_kind


def line(text, x=.5, y=.5):
    return {"text": text, "confidence": .99, "box": [x - .02, y - .01, .04, .02]}


def observation(pts, scene, song, chart):
    return {"source_pts_seconds": pts, "scene": scene, "eligible_screen": True, "file": f"{pts}.png",
            "song": {"text": song, "confidence": .99} if song else None,
            "chart": {"text": chart, "confidence": .99} if chart else None}


class EvidenceTest(unittest.TestCase):
    def test_summary_never_becomes_a_result_even_with_score_markers(self):
        lines = [line(t) for t in ("PLAY RESULT", "SCORE", "PERFECT")]
        self.assertFalse(is_result_screen(lines))
        self.assertEqual(scene_kind(lines), "summary")
        self.assertEqual(scene_kind([line("1ST"), line("2ND")]), "summary")

    def test_replay_ignores_legacy_result_crop_on_a_summary_screen(self):
        from piu_timeline.relabel_analysis import replay_observations
        frame = {"phase": "result", "ocr": [line("PLAY RESULT")],
                 "focused_ocr": [line("Wrong first row", .5, .18)], "song": {"text": "Wrong first row"}}
        replay = replay_observations([frame], 3)[0]
        self.assertEqual(replay["scene"], "summary")
        self.assertIsNone(replay["song"])
        self.assertEqual(replay["rows"], {})

    def test_unclassified_background_is_not_selection(self):
        self.assertEqual(scene_kind([line("Wrong BGA title")]), "unknown")

    def test_summary_recovers_correct_pair(self):
        frames = [observation(i, "result", "BGA credit", "D20") for i in (1, 2)]
        frames += [observation(i, "summary", "Played song", "D21") for i in (3, 4)]
        labels, support = resolve_labels(frames)
        self.assertEqual(labels, {"song": "Played song", "chart": "D21"})
        self.assertEqual(support["song"]["phase"], "summary")

    def test_does_not_borrow_chart_from_a_different_selected_song(self):
        frames = [observation(i, "result", "Played song", None) for i in (1, 2)]
        frames += [observation(i, "selection", "Browsed song", "D20") for i in (3, 4)]
        self.assertEqual(resolve_labels(frames)[0], {"song": "Played song", "chart": None})

    def test_same_frame_cannot_vote_twice(self):
        frame = observation(1, "result", "Song", "D20")
        self.assertEqual(resolve_labels([frame, frame])[0], {"song": None, "chart": None})

    def test_single_frame_and_tied_titles_remain_unknown(self):
        frames = [observation(i, "result", name, None) for i, name in enumerate(("A", "B", "A", "B"))]
        self.assertIsNone(resolve_labels(frames)[0]["song"])
        self.assertIsNone(resolve_labels(frames[:1])[0]["song"])

    def test_names_are_separate_and_conflicts_stay_unknown(self):
        frames = [{"source_pts_seconds": i, "scene": "result", "eligible_screen": True,
                   "ocr": [line("ALICE #1234", .28, .065), line("BOB #5678", .72, .065),
                           line("BGA #5555", .7, .3)]} for i in range(2)]
        players = resolve_players(frames)
        self.assertEqual(players["p1"]["name"], "ALICE #1234")
        self.assertEqual(players["p2"]["name"], "BOB #5678")
        frames[1]["ocr"][0]["text"] = "CAROL #9999"
        self.assertIsNone(resolve_players(frames)["p1"]["name"])

    def test_repeated_account_names_use_a_text_specific_confidence_gate(self):
        raw = line("ALICE #1234", .28, .065)
        raw["confidence"] = .5
        frames = [{"source_pts_seconds": i, "scene": "result", "eligible_screen": True, "ocr": [raw]}
                  for i in range(3)]
        self.assertEqual(resolve_players(frames)["p1"]["name"], "ALICE #1234")
        self.assertIsNone(resolve_players(frames[:1])["p1"]["name"])

    def test_summary_repairs_previous_stages_but_not_previous_credit(self):
        segments = [{"stage": stage, "song": "Old", "chart": "D10", "needs_review": False}
                    for stage in (1, 2, 1, 2)]
        row = {k: v for k, v in observation(0, "summary", "Correct", "D20").items() if k in {"song", "chart"}}
        frames = [observation(i, "summary", None, None) | {"rows": {"1": row}} for i in (1, 2)]
        reconcile_sessions(segments, [[], [], [], frames])
        self.assertEqual(segments[0]["song"], "Old")
        self.assertEqual(segments[2]["song"], "Correct")
        self.assertEqual(segments[3]["song"], "Old")
        self.assertTrue(segments[2]["needs_review"])
