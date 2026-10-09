"""Replay scene-aware label resolution from retained evidence, without media decoding."""
import argparse
import copy
import json
from pathlib import Path

from .evidence import reconcile_sessions, resolve_labels, resolve_players
from .recognition import frame_labels, scene_kind, summary_stage_row
from .timeline import write_json


def replay_observations(observations, stage):
    replayed = []
    for original in observations:
        item = copy.deepcopy(original)
        scene = scene_kind(item.get("ocr", []))
        item["scene"] = scene
        item["eligible_screen"] = scene in {"selection", "result", "summary"}
        # Legacy crops were chosen by sampling offset, not scene. A result crop
        # cannot be interpreted as a summary crop, even if its raw screen is one.
        focused = item.get("focused_ocr", []) if item.get("phase") == scene else []
        item["song"], item["chart"] = None, None
        if scene == "summary":
            item["rows"] = {str(number): row for number in range(1, 7)
                            if (row := summary_stage_row(focused, number))}
            item.update(item["rows"].get(str(stage), {}))
        elif focused and scene in {"result", "selection"}:
            item.update(frame_labels(focused, scene))
        replayed.append(item)
    return replayed


def relabel(source, output):
    document = json.loads(source.read_text(encoding="utf-8"))
    if document.get("method") != "automatic_hud_ocr" or not isinstance(document.get("segments"), list):
        raise ValueError("Use an automatic analysis.json with retained OCR evidence")
    result = copy.deepcopy(document)
    all_observations = []
    for segment in result["segments"]:
        observations = json.loads(Path(segment["ocr_evidence"]).read_text(encoding="utf-8"))
        observations = replay_observations(observations, segment.get("stage"))
        labels, support = resolve_labels(observations)
        segment.update(labels)
        segment["confidence"] = support
        segment["players"] = resolve_players(observations)
        segment["needs_review"] = True
        all_observations.append(observations)
    reconcile_sessions(result["segments"], all_observations)
    changes = [{"segment": index, "field": field, "before": before.get(field), "after": after.get(field)}
               for index, (before, after) in enumerate(zip(document["segments"], result["segments"]), 1)
               for field in ("song", "chart") if before.get(field) != after.get(field)]
    output.mkdir(parents=True, exist_ok=False)
    result["relabeling"] = {"source_analysis": str(source.resolve()), "media_decoded": False,
                            "network_used": False, "changes": changes}
    write_json(output / "analysis.json", result)
    print(f"Changed {len(changes)} labels in {output} without media decoding")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    try:
        relabel(args.analysis, args.output_dir)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
