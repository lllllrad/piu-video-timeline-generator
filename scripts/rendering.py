"""Safe conditional timeline rendering, independent of video and OCR."""
import argparse
import json
import math
from pathlib import Path
import string
import tomllib
import unicodedata

from timeline import timestamp, write_json

PLAYER_FIELDS = {"perfect", "great", "good", "bad", "miss", "max_combo", "score", "chart", "player_id", "side"}
NUMERIC = {"perfect", "great", "good", "bad", "miss", "max_combo", "score"}
BASE = {"timestamp", "song", "chart", "chart_suffix", "player_id", "side", *NUMERIC}
FIELDS = BASE | {f"{prefix}.{field}" for prefix in ("player", "p1", "p2") for field in PLAYER_FIELDS}
SELECTORS = ("single", "p1", "p2", "all")
DEFAULT_TITLE = "{timestamp} {song}{chart_suffix}"
DEFAULT_DETAIL = "P {player.perfect} / G {player.great} / Good {player.good} / Bad {player.bad} / Miss {player.miss}"


def clean(value):
    return " ".join("".join(" " if unicodedata.category(c).startswith("C") else c for c in str(value)).split())


def placeholders(template):
    if not isinstance(template, str) or len(template) > 4096:
        raise ValueError("Templates must be strings of at most 4096 characters")
    fields = set()
    for _, field, spec, conversion in string.Formatter().parse(template):
        if field is None:
            continue
        if field not in FIELDS or spec or conversion:
            raise ValueError(f"Unsupported placeholder/format: {field!r}; use plain named fields")
        fields.add(field)
    return fields


def keys(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(f"Invalid {label} keys; allowed: {', '.join(sorted(allowed))}")


def validate_condition(condition):
    keys(condition, {"all", "any", "field", "op", "value"}, "condition")
    groups = set(condition) & {"all", "any"}
    if groups:
        if len(condition) != 1:
            raise ValueError("A condition group must contain only all or any")
        children = condition[next(iter(groups))]
        if not isinstance(children, list) or not 1 <= len(children) <= 50:
            raise ValueError("Condition groups need 1–50 comparisons")
        # One level of grouping is enough for typed rules; no recursive programs.
        for child in children:
            if not isinstance(child, dict) or set(child) & {"all", "any"}:
                raise ValueError("Nested condition groups are not supported")
            validate_condition(child)
        return
    field, op = condition.get("field"), condition.get("op")
    if field not in FIELDS or op not in {"eq", "ne", "lt", "le", "gt", "ge", "recognized"}:
        raise ValueError("Condition needs a known field and typed comparison operator")
    if op == "recognized":
        if "value" in condition:
            raise ValueError("recognized does not take a value")
        return
    value = condition.get("value")
    if field.split(".")[-1] in NUMERIC:
        if type(value) is not int or value < 0:
            raise ValueError("Judgment/score conditions require non-negative integers")
    elif not isinstance(value, str) or op not in {"eq", "ne"}:
        raise ValueError("Text fields support only eq/ne against a string")


def validate_config(config):
    keys(config, {"version", "player", "title", "details", "rules"}, "template configuration")
    if type(config.get("version", 1)) is not int or config.get("version", 1) != 1:
        raise ValueError("Unsupported template version")
    if config.get("player", "single") not in SELECTORS:
        raise ValueError("player must be single, p1, p2 or all")
    placeholders(config.get("title", DEFAULT_TITLE))
    def details(blocks):
        if not isinstance(blocks, list) or len(blocks) > 50:
            raise ValueError("details must be a list of at most 50 blocks")
        for block in blocks:
            keys(block, {"text", "requires", "missing", "when"}, "detail block")
            placeholders(block.get("text"))
            required = block.get("requires", [])
            if not isinstance(required, list) or any(not isinstance(f, str) or f not in FIELDS for f in required):
                raise ValueError("requires must list known fields")
            if block.get("missing", "omit") not in {"omit", "show", "error"}:
                raise ValueError("missing must be omit, show or error")
            if "when" in block:
                validate_condition(block["when"])
    details(config.get("details", []))
    rules = config.get("rules", [])
    if not isinstance(rules, list) or len(rules) > 50:
        raise ValueError("rules must be a list of at most 50 entries")
    for rule in rules:
        keys(rule, {"when", "title", "details"}, "rule")
        validate_condition(rule.get("when"))
        if not set(rule) & {"title", "details"}:
            raise ValueError("A rule must override title or details")
        if "title" in rule:
            placeholders(rule["title"])
        if "details" in rule:
            details(rule["details"])
    return {"version": 1, "player": "single", "title": DEFAULT_TITLE, "details": [], "rules": [], **config}


def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate configuration key: {key}")
        result[key] = value
    return result


def load_config(path=None):
    if path is None:
        return validate_config({})
    raw = Path(path).read_bytes()
    if len(raw) > 65536:
        raise ValueError("Template file exceeds 64 KiB")
    if Path(path).suffix.lower() == ".toml":
        value = tomllib.loads(raw.decode("utf-8"))
    elif Path(path).suffix.lower() == ".json":
        value = json.loads(raw, object_pairs_hook=reject_duplicates)
    else:
        raise ValueError("Use a .toml or .json template file")
    return validate_config(value)


def needs_results(config):
    def scan(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "field" and child not in {"song", "timestamp", "chart", "chart_suffix"}:
                    return True
                if key == "requires" and any(f not in {"song", "timestamp", "chart", "chart_suffix"} for f in child):
                    return True
                if key in {"text", "title"} and any(f not in {"song", "timestamp", "chart", "chart_suffix"} for f in placeholders(child)):
                    return True
                if isinstance(child, (dict, list)) and scan(child):
                    return True
        if isinstance(value, list):
            return any(scan(child) for child in value)
        return False
    return config["player"] != "single" or scan(config)


def condition_matches(condition, context):
    if "all" in condition:
        return all(condition_matches(c, context) for c in condition["all"])
    if "any" in condition:
        return any(condition_matches(c, context) for c in condition["any"])
    value = context.get(condition["field"])
    if condition["op"] == "recognized":
        return value is not None
    if value is None:  # Unknown never satisfies even ne or comparison with zero.
        return False
    wanted = condition["value"]
    if type(value) is not type(wanted):
        return False
    op = condition["op"]
    return {"eq": lambda: value == wanted, "ne": lambda: value != wanted,
            "lt": lambda: value < wanted, "le": lambda: value <= wanted,
            "gt": lambda: value > wanted, "ge": lambda: value >= wanted}[op]()


def player_value(player, field):
    if not player or player.get("presence") != "recognized":
        return None
    if field in {"side", "player_id"}:
        return player.get(field)
    evidence = player.get("fields", {}).get(field, {})
    if evidence.get("status") != "recognized":
        return None
    value = evidence.get("value")
    if field in NUMERIC:
        return value if type(value) is int and value >= 0 else None
    return clean(value) if isinstance(value, str) else None


def context_for(segment, player_id, players, config):
    selected = players.get(player_id)
    chart = player_value(selected, "chart")
    # Legacy/default song-only timelines need no result OCR. Never borrow a chart
    # from the other player when an explicit target is missing or two slots exist.
    if chart is None and not players and config["player"] == "single":
        chart = clean(segment["chart"]) if segment.get("chart") else None
    context = {field: None for field in FIELDS}
    context.update(timestamp=timestamp(segment["start_seconds"]),
                   song=clean(segment["song"]) if segment.get("song") else None,
                   chart=chart, chart_suffix=f" [{chart}]" if chart else "")
    for prefix, player in (("player", selected), ("p1", players.get("p1")), ("p2", players.get("p2"))):
        for field in PLAYER_FIELDS:
            context[f"{prefix}.{field}"] = player_value(player, field)
    for field in NUMERIC | {"player_id", "side"}:
        context[field] = context[f"player.{field}"]
    return context


def substitute(template, context):
    output = []
    for literal, field, _, _ in string.Formatter().parse(template):
        output.append(literal)
        if field is not None:
            value = context.get(field)
            output.append(str(value) if value is not None else "Unknown song" if field == "song" else "?")
    return clean("".join(output))


def render(timeline, config):
    config = validate_config(config)
    if not isinstance(timeline, dict):
        raise ValueError("Timeline must be a JSON object")
    segments = timeline.get("segments")
    if not isinstance(segments, list):
        raise ValueError("Timeline needs segments")
    if needs_results(config) and any("results" not in segment for segment in segments):
        raise ValueError("This template/player selection needs result data. Run just results INPUT OUTPUT first.")
    entries = []
    previous_end = 0
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict) or not isinstance(segment.get("results", {}), dict):
            raise ValueError("Segments and results must be objects")
        start, end = segment.get("start_seconds"), segment.get("end_seconds")
        if (type(start) not in (int, float) or type(end) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(end) or start < previous_end or end <= start):
            raise ValueError("Timeline intervals must be finite, ordered and non-overlapping")
        previous_end = end
        players = segment.get("results", {}).get("players", {})
        if not isinstance(players, dict) or set(players) - {"p1", "p2"}:
            raise ValueError("Invalid result player slots")
        for identifier, player in players.items():
            if (not isinstance(player, dict) or player.get("player_id") != identifier
                    or player.get("presence") not in {"recognized", "uncertain"}
                    or not isinstance(player.get("fields"), dict)
                    or any(not isinstance(v, dict) for v in player["fields"].values())):
                raise ValueError("Invalid player identity, presence or field evidence")
        selector = config["player"]
        if selector == "single":
            chosen = [next(iter(players))] if len(players) == 1 and next(iter(players.values())).get("presence") == "recognized" else [None]
        elif selector == "all":
            chosen = sorted(players) or [None]
        else:
            chosen = [selector]
        for player_id in chosen:
            context = context_for(segment, player_id, players, config)
            warnings = []
            if needs_results(config) and (not player_id or player_value(players.get(player_id), "player_id") is None):
                warnings.append("Player selection is ambiguous or unavailable; selected-player fields remain unknown")
            title, blocks = config["title"], config["details"]
            rule_index = None
            for rule_index_candidate, rule in enumerate(config["rules"]):
                if condition_matches(rule["when"], context):
                    title, blocks = rule.get("title", title), rule.get("details", blocks)
                    rule_index = rule_index_candidate
                    break
            missing_title = sorted(field for field in placeholders(title) if context.get(field) is None)
            if missing_title:
                warnings.append("Unknown title fields: " + ", ".join(missing_title))
            text = substitute(title, context)
            if selector == "all" and player_id:
                text += f" [{player_id.upper()}]"
            details = []
            for block in blocks:
                if "when" in block and not condition_matches(block["when"], context):
                    continue
                required = set(block.get("requires", [])) | placeholders(block["text"])
                missing = sorted(field for field in required if context.get(field) is None)
                if missing:
                    warnings.append("Unknown detail fields: " + ", ".join(missing))
                    policy = block.get("missing", "omit")
                    if policy == "error":
                        raise ValueError(f"Segment {index + 1}: missing detail fields: {', '.join(missing)}")
                    if policy == "omit":
                        continue
                details.append(substitute(block["text"], context))
            entries.append({"segment_index": index, "start_seconds": start, "player": player_id,
                            "title": text, "details": details, "rule_index": rule_index,
                            "warnings": warnings,
                            "needs_review": bool(warnings) or segment.get("needs_review", False)
                                            or segment.get("results", {}).get("needs_review", False)})
    return {"schema_version": 1, "timestamp_basis": "local_playback", "config": config, "entries": entries}


def write_rendered(directory, rendered):
    write_json(directory / "rendered.json", rendered)
    entries = rendered["entries"]
    with (directory / "timeline.txt").open("x", encoding="utf-8") as stream:
        stream.write("".join(entry["title"] + "\n" for entry in entries))
    with (directory / "details.txt").open("x", encoding="utf-8") as stream:
        stream.write("\n\n".join("\n".join([entry["title"], *entry["details"]]) for entry in entries) + ("\n" if entries else ""))


def report_review(rendered):
    count = sum(bool(entry["needs_review"]) for entry in rendered["entries"])
    warnings = sum(bool(entry["warnings"]) for entry in rendered["entries"])
    if count:
        print(f"Review needed: {count} entries ({warnings} with missing/ambiguous template fields); see rendered.json")


def add_render_arguments(parser):
    parser.add_argument("--template", type=Path, help="TOML/JSON conditional title/detail configuration")
    parser.add_argument("--player", choices=SELECTORS, help="single (default): sole player on either side; p1/p2: fixed slot; all: both")
    parser.add_argument("--title", help="Override title; e.g. {timestamp} {song} [{player.chart}]")
    parser.add_argument("--detail", action="append", help="Repeatable detail template; selected-player fields work on either side")


def config_from_args(args, default_details=False):
    config = load_config(args.template)
    if args.player:
        config["player"] = args.player
    if args.title is not None:
        config["title"] = args.title
    if args.detail is not None:
        config["details"] = [{"text": text, "missing": "show"} for text in args.detail]
    elif default_details and args.template is None:
        config["details"] = [{"text": DEFAULT_DETAIL, "missing": "show"}]
    return validate_config(config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("timeline", type=Path, help="Structured analysis.json or legacy timeline.json")
    parser.add_argument("output_dir", type=Path)
    add_render_arguments(parser)
    args = parser.parse_args()
    try:
        config = config_from_args(args)
        result = render(json.loads(args.timeline.read_text()), config)
        args.output_dir.mkdir(parents=True, exist_ok=False)
        write_rendered(args.output_dir, result)
        print(f"Rendered {len(result['entries'])} entries without media/network access in {args.output_dir}")
        report_review(result)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
