"""Presentation regressions using the actual Node.js formatter helpers."""
import json
import subprocess
import tempfile
from pathlib import Path
import unittest

from piu_timeline import workflow


def player(name=None, chart=None, presence="recognized"):
    fields = {key: {"status": "recognized", "value": value}
              for key, value in (("name", name), ("chart", chart)) if value is not None}
    return {"presence": presence, "fields": fields}


def segment(players=None, results=None):
    return {"start_seconds": 10, "end_seconds": 20, "stage": 1, "song": "Song", "chart": "D20",
            "players": players or {}, "results": {"players": results or {}}}


class FormatTest(unittest.TestCase):
    def labels(self, segments, options=None):
        module = (workflow.BUILTIN_FORMATS / "lib/timeline.ts").as_uri()
        code = f'''
import {{ createSegmentLabeler, songLabel, playerNames, hasMultiplePlayers }} from {json.dumps(module)};
const [segments, options] = JSON.parse(process.argv[1]);
const timeline = {{ segments }};
const segmentLabel = createSegmentLabeler(timeline, options);
console.log(JSON.stringify({{
  multiple: hasMultiplePlayers(timeline),
  labels: segments.map(segmentLabel),
  songs: segments.map(songLabel),
  names: segments.map(segment => playerNames(segment)),
}}));
'''
        result = subprocess.run(["node", "--input-type=module", "-e", code,
                                 json.dumps([segments, options or {}])],
                                check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    def test_partial_discriminator_keeps_one_player_hidden(self):
        result = self.labels([segment({"p2": player(name)})
                              for name in ("Alice #1234", "Alice", " Alice #1234 ")])
        self.assertFalse(result["multiple"])
        self.assertEqual(result["labels"], ["Song D20"] * 3)
        self.assertEqual(result["names"], ["Alice"] * 3)

    def test_distinct_discriminators_still_establish_multiple_accounts(self):
        segments = [segment({"p2": player(name)}) for name in ("Alice #1234", "Alice", "Alice #5678")]
        result = self.labels(segments, {"accountDiscriminators": True})
        self.assertTrue(result["multiple"])
        self.assertEqual(result["labels"], ["Song D20 [Alice #1234]", "Song D20 [Alice]", "Song D20 [Alice #5678]"])

    def test_uncertain_identity_does_not_add_player(self):
        result = self.labels([segment({"p2": player("Alice")}),
                              segment({"p2": player("Bob", presence="uncertain")})])
        self.assertFalse(result["multiple"])
        self.assertEqual(result["labels"], ["Song D20", "Song D20"])
        self.assertEqual(result["names"][1], "Unknown player")

    def test_result_only_identity_participates_in_recording_policy(self):
        result = self.labels([segment(results={"p2": player("Alice")}),
                              segment({"p2": player("Bob")}), segment()])
        self.assertTrue(result["multiple"])
        self.assertEqual(result["labels"], ["Song D20 [Alice]", "Song D20 [Bob]", "Song D20 [Unknown player]"])

    def test_simultaneous_players_merge_identity_and_result_slots(self):
        play = segment({"p1": player("Alice", "S18")}, {"p2": player("Bob", "D20")})
        result = self.labels([play])
        self.assertEqual(result["labels"], ["Song [P1: Alice S18 / P2: Bob D20]"])
        self.assertEqual(result["names"], ["P1: Alice / P2: Bob"])
        self.assertEqual(result["songs"], ["Song D20"])
        self.assertEqual(self.labels([play], {"playerNames": "never"})["labels"],
                         ["Song [P1: S18 / P2: D20]"])

    def test_explicit_name_policy_preserves_song_and_chart(self):
        plays = [segment({"p2": player("Alice #1234")}), segment({"p2": player("Bob #5678")})]
        self.assertEqual(self.labels(plays, {"playerNames": "never"})["labels"], ["Song D20"] * 2)
        self.assertEqual(self.labels(plays[:1], {"playerNames": "always"})["labels"], ["Song D20 [Alice]"])

    def test_unknown_song_and_chart_remain_unknown(self):
        play = {**segment(), "song": None, "chart": None}
        self.assertEqual(self.labels([play])["labels"], ["Unknown song"])

    def test_bundled_scores_share_name_policy_and_preserve_score(self):
        plays = [segment({"p2": player(name)}, {"p2": {"presence": "recognized", "fields": {
            "score": {"status": "recognized", "value": 987654}}}})
                 for name in ("Alice #1234", "Alice")]
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "analysis.json"
            source.write_text(json.dumps({"segments": plays}))
            output = workflow.run_formatter(workflow.BUILTIN_FORMATS / "scores/index.ts", source)
        self.assertEqual(output, "00:10 Song D20 — 987,654\n" * 2)
