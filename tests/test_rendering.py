import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
from piu_timeline import rendering as r
from piu_timeline.timeline import render_text


def player(identifier="p2", **values):
    values = {"chart": "D21", "perfect": 500, "great": 0, "good": 0, "bad": 0,
              "miss": 0, "max_combo": 500, "score": 999999, **values}
    return {"player_id": identifier, "side": "left" if identifier == "p1" else "right", "presence": "recognized",
            **values, "fields": {key: {"value": value, "status": "recognized" if value is not None else "unknown"}
                                  for key, value in values.items()}}


def timeline(players=None):
    segment = {"start_seconds": 12.9, "end_seconds": 140, "song": "Song", "chart": "D21"}
    if players is not None:
        segment["results"] = {"players": players}
    return {"segments": [segment]}


def judgment_config():
    return {"details": [{"text": "P {player.perfect} / G {player.great}", "missing": "show"}],
            "rules": [{"title": "All judgments perfect",
                       "when": {"all": [{"field": f"player.{field}", "op": "eq", "value": 0}
                                         for field in ("great", "good", "bad", "miss")]}}]}


class RenderingTest(unittest.TestCase):
    def test_default_matches_paste_ready_timeline_rows(self):
        data = timeline()
        rendered = r.render(data, {})
        entry = rendered["entries"][0]
        self.assertEqual("00:00 auto-generated timeline started\n" + entry["title"] + "\n" + entry["end_title"] + "\n",
                         render_text(data))
        self.assertFalse(r.needs_results(r.validate_config({})))

    def test_single_alias_follows_either_side_and_does_not_mutate(self):
        config = judgment_config()
        for side in ("p1", "p2"):
            data = timeline({side: player(side)})
            original = copy.deepcopy(data)
            entry = r.render(data, config)["entries"][0]
            self.assertEqual(entry["player"], side)
            self.assertIn("All judgments perfect", entry["title"])
            self.assertIn("P 500 / G 0", entry["details"][0])
            self.assertEqual(data, original)

    def test_unknown_zero_conflict_never_satisfies_condition(self):
        config = judgment_config()
        for field in ("great", "good", "bad", "miss"):
            p = player(**{field: None})
            entry = r.render(timeline({"p2": p}), config)["entries"][0]
            self.assertNotIn("All judgments perfect", entry["title"])
            p["fields"][field] = {"value": 0, "status": "conflict"}
            self.assertNotIn("All judgments perfect", r.render(timeline({"p2": p}), config)["entries"][0]["title"])
        self.assertFalse(r.condition_matches({"field": "player.miss", "op": "ne", "value": 0}, {"player.miss": None}))

    def test_two_players_are_not_silently_merged(self):
        data = timeline({"p1": player("p1", great=2), "p2": player("p2", chart="D24", great=7)})
        config = {"title": "{timestamp} {player.chart}", "details": [{"text": "{player.great}", "missing": "show"}]}
        entry = r.render(data, config)["entries"][0]
        self.assertIsNone(entry["player"])
        self.assertEqual(entry["details"], ["?"])
        self.assertTrue(entry["warnings"])
        for side, expected in (("p1", "2"), ("p2", "7")):
            self.assertEqual(r.render(data, {**config, "player": side})["entries"][0]["details"], [expected])
        both = r.render(data, {**config, "player": "all"})["entries"]
        self.assertEqual(len(both), 2)
        self.assertIn("[P1]", both[0]["title"])
        self.assertIn("D24", both[1]["title"])

    def test_explicit_namespaces_and_absent_target(self):
        data = timeline({"p2": player("p2")})
        entry = r.render(data, {"player": "p1", "title": "{chart} {player.perfect} {p2.perfect}"})["entries"][0]
        self.assertEqual(entry["title"], "? ? 500")
        self.assertTrue(entry["warnings"])

    def test_uncertain_other_slot_prevents_single_selection(self):
        other = player("p1")
        other["presence"] = "uncertain"
        entry = r.render(timeline({"p1": other, "p2": player()}), {"title": "{player.perfect}"})["entries"][0]
        self.assertEqual(entry["title"], "?")

    def test_rule_order_and_conditional_details(self):
        config = {"rules": [{"when": {"field": "great", "op": "eq", "value": 0}, "title": "first",
                             "details": [{"text": "zero", "when": {"field": "miss", "op": "eq", "value": 0}}]},
                            {"when": {"field": "perfect", "op": "gt", "value": 0}, "title": "second"}]}
        entry = r.render(timeline({"p2": player()}), config)["entries"][0]
        self.assertEqual((entry["title"], entry["details"]), ("first", ["zero"]))

    def test_missing_policies(self):
        data = timeline({})
        for policy, expected in (("omit", []), ("show", ["Miss ?"])):
            entry = r.render(data, {"details": [{"text": "Miss {miss}", "missing": policy}]})["entries"][0]
            self.assertEqual(entry["details"], expected)
        with self.assertRaises(ValueError):
            r.render(data, {"details": [{"text": "Miss {miss}", "missing": "error"}]})

    def test_result_requirements_are_inferred_from_rules_and_fields(self):
        for config in ({"title": "{player.perfect}"}, {"details": [{"text": "test", "requires": ["miss"]}]},
                       {"rules": [{"when": {"field": "miss", "op": "eq", "value": 0}, "title": "test"}]},
                       {"player": "p2"}):
            self.assertTrue(r.needs_results(r.validate_config(config)))
            with self.assertRaisesRegex(ValueError, "just results"):
                r.render(timeline(), config)

    def test_invalid_templates_are_rejected(self):
        for config in ({"title": "{player.__class__}"}, {"title": "{song!r}"}, {"title": "{score:99999d}"},
                       {"title": "{"}, {"titel": "oops"}, {"player": "auto"}, {"version": True},
                       {"rules": [{"when": {"field": "miss", "op": "eq", "value": None}, "title": "oops"}]},
                       {"rules": [{"when": {"field": "miss", "op": "eq", "value": True}, "title": "oops"}]}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                r.validate_config(config)

    def test_control_characters_cannot_inject_timestamp_rows(self):
        data = timeline()
        data["segments"][0]["song"] = "Song\n00:00 Fake\x00\u202e"
        title = r.render(data, {})["entries"][0]["title"]
        self.assertNotIn("\n", title)
        self.assertNotIn("\u202e", title)

    def test_cli_render_needs_no_media_and_protects_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "timeline.json"
            source.write_text(json.dumps(timeline({"p2": player()})))
            config = root / "config.json"
            config.write_text(json.dumps(judgment_config()))
            command = [sys.executable, "-m", "piu_timeline.rendering", str(source), str(root / "render"),
                       "--template", str(config)]
            subprocess.run(command, check=True, capture_output=True)
            self.assertIn("P 500", (root / "render/details.txt").read_text())
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertTrue(source.exists())

    def test_invalid_auto_config_fails_before_media_fetch(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "out"
            result = subprocess.run([sys.executable, "-m", "piu_timeline.auto_timeline",
                                     "https://www.youtube.com/watch?v=_OE47GBOvB0", str(output),
                                     "--title", "{evil}", "--no-judgments"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unsupported placeholder", result.stderr)
            self.assertFalse(output.exists())

    def test_explicitly_disabled_results_error_before_fetch(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "out"
            result = subprocess.run([sys.executable, "-m", "piu_timeline.auto_timeline",
                                     "https://www.youtube.com/watch?v=_OE47GBOvB0", str(output),
                                     "--detail", "{player.perfect}", "--no-judgments"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires judgments", result.stderr)
            self.assertFalse(output.exists())

    def test_json_duplicate_keys_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "template.json"
            config.write_text('{"title":"first","title":"second"}')
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                r.load_config(config)


if __name__ == "__main__":
    unittest.main()
