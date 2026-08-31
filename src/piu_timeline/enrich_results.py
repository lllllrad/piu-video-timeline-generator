"""Add player judgments from saved game-result frames; no download or full rescan."""
import argparse
import copy
import json
from pathlib import Path
import subprocess

from .rendering import add_render_arguments, config_from_args, render, report_review, validate_config, write_rendered
from .result_stats import extract_stats
from .timeline import write_json


def enrich(source, output, config=None, selected=None):
    if config is not None:
        config = validate_config(config)
    document = json.loads(source.read_text(encoding="utf-8"))
    if document.get("method") != "automatic_hud_ocr":
        raise ValueError("Use an automatic analysis.json (or legacy timeline.json) with retained OCR frame evidence")
    segments = document.get("segments")
    if not isinstance(segments, list):
        raise ValueError("Missing automatic segments")
    indices = list(range(len(segments))) if selected is None else sorted(set(i - 1 for i in selected))
    if any(i < 0 or i >= len(segments) for i in indices):
        raise ValueError("--segment is a one-based segment number in this timeline")
    roi = document.get("game_roi")
    if not isinstance(roi, list) or len(roi) != 4 or any(type(v) is not int for v in roi) or min(roi[2:]) <= 0:
        raise ValueError("Timeline needs a valid game_roi")
    prepared = []
    for i in indices:
        evidence = Path(segments[i]["ocr_evidence"])
        observations = json.loads(evidence.read_text(encoding="utf-8"))
        if not isinstance(observations, list):
            raise ValueError("Invalid OCR evidence")
        for item in observations:
            if item.get("phase") == "result" and item.get("eligible_screen"):
                if not Path(item["file"]).is_file():
                    raise ValueError("Result evidence images are missing; restore them or rerun just auto --judgments")
                if item.get("roi") != roi:
                    raise ValueError("Evidence crop differs from timeline game_roi")
        prepared.append(observations)
    output.mkdir(parents=True, exist_ok=False)
    result = copy.deepcopy(document)
    result["artifact_type"] = "video_analysis"
    result["timestamp_basis"] = "local_playback"
    result["analysis_options"] = {**result.get("analysis_options", {}), "judgments": True}
    result.pop("text_timestamp_basis", None)
    result["segments"] = []
    result["result_enrichment"] = {"source_timeline": str(source.resolve()), "source_segments": [i + 1 for i in indices],
                                   "network_used": False, "media_decoded": False}
    for i, observations in zip(indices, prepared):
        print(f"Reading result judgments for segment {i + 1}...", flush=True)
        segment = copy.deepcopy(segments[i])
        segment["results"] = extract_stats(observations, output / "evidence" / f"segment-{i + 1:03}", roi[2], roi[3])
        segment["needs_review"] = segment.get("needs_review", False) or segment["results"]["needs_review"]
        result["segments"].append(segment)
        write_json(output / f"segment-{i + 1:03}.json", segment)
    write_json(output / "analysis.json", result)
    if config is not None:
        rendered = render(result, config)
        write_rendered(output, rendered)
        write_json(output / "timeline.json", {**result, "text_timestamp_basis": "local_playback"})
        report_review(rendered)
    print(f"Enriched {len(result['segments'])} segments in {output}; use just render to change presentation without OCR")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("timeline", type=Path, help="Structured analysis.json or legacy automatic timeline.json")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--segment", type=int, action="append", help="Only selected one-based segments; repeatable")
    parser.add_argument("--render", action="store_true", help="Also render output; presentation flags imply this option")
    add_render_arguments(parser)
    args = parser.parse_args()
    try:
        requested = args.render or any(value is not None for value in (args.template, args.player, args.title, args.detail))
        config = config_from_args(args, default_details=True) if requested else None
        enrich(args.timeline, args.output_dir, config, args.segment)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr
        parser.error(f"Result image processing failed: {detail or error}")


if __name__ == "__main__":
    main()
