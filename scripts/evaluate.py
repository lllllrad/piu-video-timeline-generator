"""Evaluate automatic output against separately reviewed, source-bound intervals."""
import argparse
import json
from pathlib import Path
import re
import unicodedata

from timeline import number, write_json


def normalized(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold() if text else None


def outside_range(value, interval):
    low, high = interval
    return max(low - value, 0, value - high)


def evaluate(prediction, reference):
    if reference.get("method") != "independent_video_review":
        raise ValueError("Reference must be independent_video_review, not comments or detector output")
    for key in ("path", "size_bytes", "mtime_ns"):
        value = reference.get("media", {}).get(key)
        if value is None or value != prediction.get("media", {}).get(key):
            raise ValueError("Reference and output refer to different media")
    coverage = reference.get("coverage_seconds")
    if not isinstance(coverage, list) or len(coverage) != 2:
        raise ValueError("Reference needs an explicit coverage interval")
    for value in coverage:
        number(value, "coverage")
    if coverage[0] >= coverage[1]:
        raise ValueError("Reference needs an increasing coverage interval")
    expected = reference.get("segments")
    if not isinstance(expected, list) or not expected:
        raise ValueError("Reference needs reviewed segments")
    previous_end = coverage[0]
    for item in expected:
        for key in ("start_range", "end_range"):
            pair = item.get(key)
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("Each boundary needs a reviewed [lower, upper] range")
            for value in pair:
                number(value, key)
            if pair[0] > pair[1]:
                raise ValueError("Reversed reference boundary range")
        if item["start_range"][1] >= item["end_range"][0] or not item.get("evidence"):
            raise ValueError("Invalid reviewed interval or missing evidence")
        if item["start_range"][0] < previous_end or item["end_range"][1] > coverage[1]:
            raise ValueError("Reviewed intervals must be ordered, non-overlapping and within coverage")
        previous_end = item["end_range"][1]
    candidates, original_indices = [], []
    previous_end = 0
    for index, item in enumerate(prediction["segments"]):
        start, end = number(item["start_seconds"], "start"), number(item["end_seconds"], "end")
        if start < previous_end or end <= start:
            raise ValueError("Predicted intervals must be ordered and non-overlapping")
        previous_end = end
        if start < coverage[1] and end > coverage[0]:
            if start < coverage[0] or end > coverage[1]:
                raise ValueError("A prediction crosses review coverage; extend the review before evaluating")
            candidates.append(item)
            original_indices.append(index)
    pairs = []
    for i, actual in enumerate(candidates):
        for j, wanted in enumerate(expected):
            start, end = sum(wanted["start_range"]) / 2, sum(wanted["end_range"]) / 2
            overlap = max(0, min(end, actual["end_seconds"]) - max(start, actual["start_seconds"]))
            union = max(end, actual["end_seconds"]) - min(start, actual["start_seconds"])
            if union and overlap / union >= .5:
                pairs.append((overlap / union, i, j))
    used_actual, used_expected, matches = set(), set(), []
    for iou, i, j in sorted(pairs, reverse=True):
        if i in used_actual or j in used_expected:
            continue
        used_actual.add(i)
        used_expected.add(j)
        actual, wanted = candidates[i], expected[j]
        matches.append({"prediction_index": original_indices[i], "reference_index": j, "iou": iou,
                        "start_outside_review_range_seconds": outside_range(actual["start_seconds"], wanted["start_range"]),
                        "end_outside_review_range_seconds": outside_range(actual["end_seconds"], wanted["end_range"]),
                        "song_correct": normalized(actual.get("song")) == normalized(wanted.get("song")) if wanted.get("song") else None,
                        "chart_correct": normalized(actual.get("chart")) == normalized(wanted.get("chart")) if wanted.get("chart") else None})
    return {"schema_version": 1, "coverage_seconds": coverage,
            "reference_segments": len(expected), "predicted_segments": len(candidates),
            "matched_segments": len(matches), "missed_segments": len(expected) - len(matches),
            "false_positives": len(candidates) - len(matches),
            "precision": len(matches) / len(candidates) if candidates else 0,
            "recall": len(matches) / len(expected),
            "song_correct": sum(m["song_correct"] is True for m in matches),
            "song_reviewed": sum(bool(s.get("song")) for s in expected),
            "chart_correct": sum(m["chart_correct"] is True for m in matches),
            "chart_reviewed": sum(bool(s.get("chart")) for s in expected),
            "unknown_songs": sum(s.get("song") is None for s in candidates),
            "unknown_charts": sum(s.get("chart") is None for s in candidates),
            "matches": sorted(matches, key=lambda m: m["reference_index"]),
            "note": "Timing is measured against reviewed uncertainty ranges, not assumed exact labels."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prediction", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = evaluate(json.loads(args.prediction.read_text()), json.loads(args.reference.read_text()))
        write_json(args.output, result)
        print(json.dumps({key: value for key, value in result.items() if key != "matches"}, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
