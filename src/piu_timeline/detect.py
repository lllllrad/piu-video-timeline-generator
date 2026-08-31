"""Experimental fixed-layout HUD matching; emits candidates, never reviewed labels."""
import argparse
from pathlib import Path
import subprocess

from .timeline import media_record, number, write_json


def roi_value(text):
    try:
        values = tuple(int(value) for value in text.split(","))
        if len(values) != 4 or min(values[:2]) < 0 or min(values[2:]) <= 0:
            raise ValueError
        return values
    except ValueError as error:
        raise argparse.ArgumentTypeError("ROI must be x,y,width,height with positive dimensions") from error


def similarity(frame, reference):
    return 1 - sum(abs(a - b) for a, b in zip(frame, reference)) / (255 * len(reference))


def intervals(scores, step, duration, threshold, min_duration, max_gap):
    """Merge short nonmatching gaps; retain quantized, unreviewed boundaries."""
    runs = []
    start = last = None
    matches = []
    for index, score in enumerate(scores):
        time = index * step
        if score >= threshold:
            if start is not None and time - last - step > max_gap + 1e-9:
                runs.append((start, last, matches))
                start, matches = None, []
            if start is None:
                start = time
            last = time
            matches.append(score)
    if start is not None:
        runs.append((start, last, matches))
    return [{"start_seconds": start, "end_seconds": min(last + step, duration),
             "song": None, "chart": None,
             "mean_match_score": sum(matches) / len(matches),
             "needs_review": True}
            for start, last, matches in runs
            if min(last + step, duration) - start >= min_duration]


def detect(record, roi, reference_at, step=2, threshold=0.9, min_duration=20, max_gap=4, limit=None):
    video = record["video_streams"][0]
    x, y, width, height = roi
    if x + width > video["width"] or y + height > video["height"]:
        raise ValueError("ROI exceeds the encoded video dimensions")
    if number(reference_at, "reference time") >= record["duration_seconds"]:
        raise ValueError("Reference time must be before video end")
    if number(step, "step") <= 0 or number(threshold, "threshold") > 1:
        raise ValueError("Step must be positive; threshold must be in [0, 1]")
    number(min_duration, "minimum duration")
    number(max_gap, "maximum gap")
    duration = record["duration_seconds"] if limit is None else min(number(limit, "limit"), record["duration_seconds"])
    if duration <= 0 or duration / step > 100000:
        raise ValueError("Use a positive scan duration and at most 100000 samples")
    # Fixed-size grayscale patches keep matching independent of ROI pixel count.
    crop = f"crop={width}:{height}:{x}:{y},scale=64:16,format=gray"
    reference = subprocess.run([
        "ffmpeg", "-v", "error", "-nostdin", "-ss", str(reference_at), "-noautorotate",
        "-i", record["path"], "-map", f"0:{video['index']}", "-frames:v", "1",
        "-vf", crop, "-f", "rawvideo", "pipe:1",
    ], check=True, capture_output=True).stdout
    if len(reference) != 1024:
        raise ValueError("Could not extract a complete reference patch")
    mean = sum(reference) / len(reference)
    if sum((value - mean) ** 2 for value in reference) / len(reference) < 100:
        raise ValueError("Reference patch has too little contrast; select a distinctive static HUD")
    # Decode keyframes only: useful for coarse proposals, never exact boundaries.
    result = subprocess.run([
        "ffmpeg", "-v", "error", "-nostdin", "-skip_frame", "nokey", "-noautorotate",
        "-i", record["path"], "-map", f"0:{video['index']}", "-t", str(duration),
        "-vf", f"fps=1/{step}:start_time=0:eof_action=pass,{crop}", "-f", "rawvideo", "pipe:1",
    ], check=True, capture_output=True)
    if len(result.stdout) % 1024:
        raise ValueError("Incomplete decoded patch stream")
    scores = [similarity(result.stdout[i:i + 1024], reference)
              for i in range(0, len(result.stdout), 1024)]
    if not scores:
        raise ValueError("No keyframes available for candidate detection")
    stat = Path(record["path"]).stat()
    if (stat.st_size, stat.st_mtime_ns) != (record["size_bytes"], record["mtime_ns"]):
        raise ValueError("Source changed during detection")
    return {
        "schema_version": 1, "method": "experimental_hud_template", "media": record,
        "parameters": {"roi": list(roi), "reference_seconds": reference_at,
                       "step_seconds": step, "threshold": threshold,
                       "minimum_duration_seconds": min_duration, "maximum_gap_seconds": max_gap,
                       "scan_duration_seconds": duration,
                       "sampled_grid_end_seconds": min(len(scores) * step, duration)},
        "warnings": ["Not a calibrated gameplay detector; review all candidates and missed sections.",
                     "Boundaries are sampling-grid estimates from keyframes, not exact source frames.",
                     "Layout, HUD skin, single/double mode or camera changes may invalidate the template."],
        "candidates": intervals(scores, step, duration, threshold, min_duration, max_gap),
        "samples": [{"grid_seconds": i * step, "match_score": score} for i, score in enumerate(scores)],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path, help="New candidate JSON file")
    parser.add_argument("--roi", type=roi_value, required=True, help="Encoded pixel x,y,width,height; no auto-rotation")
    parser.add_argument("--reference-at", type=float, required=True, help="Reviewed gameplay time with the static HUD visible")
    parser.add_argument("--step", type=float, default=2)
    parser.add_argument("--threshold", type=float, default=0.9)
    parser.add_argument("--min-duration", type=float, default=20)
    parser.add_argument("--max-gap", type=float, default=4)
    parser.add_argument("--limit", type=float, help="Scan only the first N playback seconds")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Output already exists")
        result = detect(media_record(args.video), args.roi, args.reference_at, args.step,
                        args.threshold, args.min_duration, args.max_gap, args.limit)
        write_json(args.output, result)
        print(f"Saved {len(result['candidates'])} unreviewed candidates to {args.output}")
    except (ValueError, OSError) as error:
        parser.error(str(error))
    except subprocess.CalledProcessError as error:
        detail = error.stderr
        if isinstance(detail, bytes):
            detail = detail.decode(errors="replace")
        parser.error(f"Media tool failed: {(detail or '').strip()}")


if __name__ == "__main__":
    main()
