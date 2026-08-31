"""Re-evaluate missing song/chart labels from retained OCR evidence without media decoding."""
import argparse
import copy
import json
from pathlib import Path

from .auto_timeline import corroborated_result_title, singleton_title
from .recognition import consensus, summary_chart, summary_song
from .timeline import write_json


def relabel(source, output):
    document = json.loads(source.read_text(encoding="utf-8"))
    if document.get("method") != "automatic_hud_ocr" or not isinstance(document.get("segments"), list):
        raise ValueError("Use an automatic analysis.json with retained OCR evidence")
    result = copy.deepcopy(document)
    changes = []
    for index, segment in enumerate(result["segments"], 1):
        if segment.get("song") is not None and segment.get("chart") is not None:
            continue
        observations = json.loads(Path(segment["ocr_evidence"]).read_text(encoding="utf-8"))
        if segment.get("song") is None:
            candidate = corroborated_result_title(observations, segment.get("chart")) or singleton_title(observations)
            if candidate:
                segment["song"] = candidate["text"].strip()
                segment.setdefault("confidence", {})["song"] = {
                    "supporting_frames": 1, "recognized_frames": 1,
                    "mean_ocr_confidence": candidate["confidence"],
                    "alternatives": {segment["song"]: 1}, "phase": "retained_evidence",
                    "agreement": "high_confidence_single_frame"}
        summary = [item for item in observations if item.get("phase") == "summary"]
        derived = []
        for item in summary:
            lines = item.get("focused_ocr", [])
            derived.append({
                "song": summary_song(lines, segment.get("chart")) if segment.get("chart") else None,
                "chart": summary_chart(lines, segment.get("song")) if segment.get("song") else None})
        for field in ("song", "chart"):
            if segment.get(field) is not None:
                continue
            value, support = consensus(derived, field)
            if value is not None:
                segment[field] = value
                segment.setdefault("confidence", {})[field] = {**support, "phase": "retained_summary"}
        before = document["segments"][index - 1]
        for field in ("song", "chart"):
            if before.get(field) is None and segment.get(field) is not None:
                changes.append({"segment": index, "field": field, "value": segment[field]})
    output.mkdir(parents=True, exist_ok=False)
    result["relabeling"] = {"source_analysis": str(source.resolve()), "media_decoded": False,
                            "network_used": False, "changes": changes}
    write_json(output / "analysis.json", result)
    print(f"Recovered {len(changes)} missing labels in {output} without media decoding")
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
