import unittest
from unittest.mock import patch
import subprocess

from piu_timeline.credits import credit_groups, reconcile_players, transition_samples, recover_summary_stages
from piu_timeline.evidence import resolve_players
from test_evidence import line


def frame(pts, scene, window, name=None):
    return {"source_pts_seconds": pts, "file": f"{pts}.png", "scene": scene, "window": window,
            "eligible_screen": True, "ocr": [line(name, .72, .065)] if name else []}


class CreditTests(unittest.TestCase):
    def test_credit_propagation_does_not_restore_an_excluded_rival_slot(self):
        segments = [{"stage": 1, "players": {}, "excluded_slots": {"p2": {"role": "rival"}}},
                    {"stage": 2, "players": {}}]
        observations = [[frame(1, "selection", "selection")],
                        [frame(2, "result", "result", "Bob #5678"), frame(3, "result", "result", "Bob #5678")]]
        reconcile_players(segments, observations)
        self.assertNotIn("p2", segments[0]["players"])
        self.assertEqual(segments[1]["players"]["p2"]["name"], "Bob #5678")

    def test_missing_stages_keep_identity_within_observed_credit(self):
        segments = [{"stage": None, "players": {}} for _ in range(3)]
        observations = [[frame(1, "selection", "selection", "SURA #6747"), frame(2, "result", "result")],
                        [frame(3, "result", "result", "SURA #6747"), frame(4, "summary", "result")],
                        [frame(5, "selection", "selection")]]
        for s, obs in zip(segments, observations):
            s["players"] = resolve_players(obs)
        reconcile_players(segments, observations)
        self.assertEqual(segments[0]["players"]["p2"]["name"], "SURA #6747")
        self.assertEqual(segments[1]["players"]["p2"]["name"], "SURA #6747")
        self.assertEqual(segments[2]["players"], {})
        self.assertEqual(segments[2]["credit"]["boundary"], "play_result")

    def test_mode_selection_stage_reset_and_six_play_limit_close_credits(self):
        segments = [{"stage": i + 1} for i in range(6)] + [{"stage": None}]
        obs = [[] for _ in segments]
        self.assertEqual(credit_groups(segments, obs)[-1]["indices"], [6])
        obs[2] = [frame(1, "mode", "selection")]
        self.assertEqual(credit_groups(segments, obs)[1]["boundary"], "new_game_screen")
        self.assertEqual(credit_groups([{"stage": 2}, {"stage": 1}], [[], []])[1]["boundary"], "stage_reset")

    def test_conflicting_accounts_never_fill_an_unknown_play(self):
        segments = [{"stage": i + 1, "players": {}} for i in range(3)]
        obs = [[frame(i, "result", "result", name) for i in pts] for name, pts in
               (("ALICE #1234", (1, 2, 3)), (None, (4,)), ("BOB #5678", (5, 6)))]
        for s, frames in zip(segments, obs):
            s["players"] = resolve_players(frames)
        reconcile_players(segments, obs)
        self.assertEqual(segments[1]["players"], {})
        self.assertEqual(segments[2]["players"]["p2"]["name"], "BOB #5678")

    def test_summary_recovers_only_unique_repeated_title_stage(self):
        row = {"song": {"text": "Song", "confidence": 1}, "chart": {"text": "D20", "confidence": 1}}
        segments = [{"stage": None, "song": "Song"}]
        obs = [[{**frame(pts, "summary", "result"), "rows": {"3": row}} for pts in (1, 2)]]
        recover_summary_stages(segments, obs)
        self.assertEqual(segments[0]["stage"], 3)
        self.assertEqual(segments[0]["stage_association"]["source_frames"], ["1.png", "2.png"])
        segments[0]["stage"] = None
        obs[0][1]["rows"]["2"] = row
        obs[0][0]["rows"]["2"] = row
        recover_summary_stages(segments, obs)
        self.assertIsNone(segments[0]["stage"])
        obs[0] = [obs[0][0], obs[0][0]]
        obs[0][0]["rows"] = {"3": row}
        recover_summary_stages(segments, obs)
        self.assertIsNone(segments[0]["stage"])

    def test_unique_summary_row_recovers_a_bounded_title_ocr_variant(self):
        row = {"song": {"text": "비코즈 오브 유", "confidence": 1}, "chart": None}
        segments = [{"stage": None, "song": "비코즈 오븐 유"}]
        obs = [[{**frame(pts, "summary", "result"), "rows": {"1": row}} for pts in (1, 2)]]
        recover_summary_stages(segments, obs)
        self.assertEqual(segments[0]["stage"], 1)
        segments[0]["stage"] = None
        for o in obs[0]:
            o["rows"]["2"] = {"song": {"text": "비코즈 오본 유", "confidence": 1}, "chart": None}
        recover_summary_stages(segments, obs)
        self.assertIsNone(segments[0]["stage"])

    def test_multiple_missing_stages_in_a_credit_are_each_recovered(self):
        rows = {str(i): {"song": {"text": song, "confidence": 1}, "chart": None}
                for i, song in ((1, "First title"), (2, "Second title"))}
        segments = [{"stage": None, "song": name} for name in ("First title", "Second title")]
        obs = [[frame(0, "result", "result")],
               [{**frame(pts, "summary", "result"), "rows": rows} for pts in (1, 2)]]
        recover_summary_stages(segments, obs)
        self.assertEqual([s["stage"] for s in segments], [1, 2])

    def test_transition_plan_is_bounded_and_uses_relative_decode_times(self):
        record = {"path": "video.mkv", "video_streams": [{"index": 0}]}
        result = subprocess.CompletedProcess([], 0, stderr="pts_time:2.5 pts_time:3.0 pts_time:19.9")
        with patch("piu_timeline.credits.subprocess.run", return_value=result) as run:
            samples = transition_samples(record, (0, 0, 1300, 730), 100, 120, limit=3)
        self.assertEqual(samples, [102.75, 103.35, 103.85])
        self.assertIn("fps=2", " ".join(run.call_args.args[0]))
        self.assertTrue(all(100 <= t < 120 for t in samples))

    def test_busy_gap_keeps_paired_samples_near_its_end(self):
        record = {"path": "video.mkv", "video_streams": [{"index": 0}]}
        result = subprocess.CompletedProcess([], 0, stderr=" ".join(
            f"pts_time:{seconds}" for seconds in range(0, 60, 2)))
        with patch("piu_timeline.credits.subprocess.run", return_value=result):
            samples = transition_samples(record, (0, 0, 1300, 730), 100, 160, limit=6)
        self.assertEqual(len(samples), 6)
        self.assertEqual(samples[:2], [100.25, 100.85])
        self.assertEqual(samples[-2:], [158.25, 158.85])
        self.assertEqual(samples, sorted(set(samples)))
