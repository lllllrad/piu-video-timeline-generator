"""Offline, review-assisted timeline generation. No automatic gameplay detection."""
import argparse
import json
import math
from pathlib import Path
import re
import subprocess


def packet_end(path):
    """Find video end without decoding when a container omits stream duration."""
    latest = None
    # Stream the probe output; multi-hour recordings need not fit in memory.
    with subprocess.Popen([
        "ffprobe", "-v", "error", "-select_streams", "v", "-show_packets",
        "-show_entries", "packet=pts_time,duration_time", "-of", "compact=p=0:nk=0",
        str(path),
    ], stdout=subprocess.PIPE, text=True) as process:
        for line in process.stdout:
            fields = dict(part.split("=", 1) for part in line.strip().split("|") if "=" in part)
            try:
                pts = float(fields["pts_time"])
                duration = float(fields["duration_time"])
            except (KeyError, ValueError):
                continue
            if math.isfinite(pts) and math.isfinite(duration) and duration > 0:
                latest = max(latest if latest is not None else -math.inf, pts + duration)
        if process.wait():
            raise ValueError("Could not inspect video packet timestamps")
    if latest is None:
        raise ValueError("Cannot determine video end from stream duration or packet timestamps")
    return latest


def number(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value) or value < minimum:
        raise ValueError(f"{name} must be finite and >= {minimum}")
    return value


def media_record(path):
    path = path.expanduser().resolve(strict=True)
    if path.suffix == ".part":
        raise ValueError("Wait for the download to complete before recording or reviewing media")
    if not path.is_file():
        raise ValueError(f"Not a video file: {path}")
    before = path.stat()
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_format", "-show_streams",
        "-of", "json", str(path),
    ], check=True, capture_output=True, text=True)
    info = json.loads(result.stdout)
    streams = [s for s in info.get("streams", [])
               if s.get("codec_type") == "video"
               and not s.get("disposition", {}).get("attached_pic")]
    if not streams:
        raise ValueError("Media contains no video stream")
    container = info.get("format", {})
    try:
        format_duration = float(container["duration"])
        origin = float(container.get("start_time", 0))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Media needs a known finite duration and start time") from error
    if not math.isfinite(format_duration) or format_duration <= 0 or not math.isfinite(origin):
        raise ValueError("Media needs a positive finite duration and finite start time")
    try:
        ends = [float(s["start_time"]) + float(s["duration"]) for s in streams]
        if not all(math.isfinite(end) and end > origin for end in ends):
            raise ValueError("Invalid stream duration")
        end = max(ends)
        duration_method = "video_stream_metadata"
    except (KeyError, TypeError, ValueError):
        end = packet_end(path)
        duration_method = "video_packet_timestamps"
    duration = end - origin
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Cannot determine positive playback duration")
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Media changed during inspection")
    return {
        "path": str(path), "size_bytes": after.st_size,
        "mtime_ns": after.st_mtime_ns, "duration_seconds": duration,
        "format_duration_seconds": format_duration, "duration_method": duration_method,
        "container_start_seconds": origin,
        "timestamp_basis": "seconds_from_local_playback_start",
        "video_streams": [{key: s.get(key) for key in (
            "index", "codec_name", "width", "height", "avg_frame_rate",
            "r_frame_rate", "time_base", "start_pts", "start_time", "duration",
        )} for s in streams],
    }


def review_template(record):
    return {
        "schema_version": 1, "method": "manual_video_review",
        "boundary_policy": "silent_song_cover_to_silent_pre_result_black_frame_whole_seconds",
        "media": record,
        "alignment": {"youtube_url": None, "offset_seconds": None},
        "segments": [],
    }


def optional_text(value, name):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value.splitlines()) != 1 or any(ord(c) < 32 for c in value):
        raise ValueError(f"{name} must be null or nonempty single-line text")
    return value.strip()


def build_timeline(review, record):
    if not isinstance(review, dict) or type(review.get("schema_version")) is not int or review.get("schema_version") != 1:
        raise ValueError("Expected review schema_version 1")
    if review.get("method") != "manual_video_review":
        raise ValueError("Only manual_video_review inputs are supported; comments are not inputs")
    saved = review.get("media")
    if not isinstance(saved, dict) or any(saved.get(k) != record[k] for k in (
        "path", "size_bytes", "mtime_ns", "duration_seconds", "container_start_seconds",
        "timestamp_basis", "video_streams",
    )):
        raise ValueError("Review media does not match this file; review the source/alignment again")
    alignment = review.get("alignment")
    if not isinstance(alignment, dict):
        raise ValueError("alignment must be an object")
    url = optional_text(alignment.get("youtube_url"), "youtube_url")
    offset = alignment.get("offset_seconds")
    if offset is not None:
        number(offset, "offset_seconds", minimum=-float("inf"))
    if (url is None) != (offset is None):
        raise ValueError("Set both youtube_url and a manually verified offset, or leave both null")
    segments = review.get("segments")
    if not isinstance(segments, list):
        raise ValueError("segments must be a list")
    normalized = []
    previous_end = 0
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise ValueError(f"Segment {index + 1} must be an object")
        unknown = set(segment) - {"start_seconds", "end_seconds", "song", "chart", "confidence", "evidence"}
        if unknown:
            raise ValueError(f"Segment {index + 1} has unsupported fields: {', '.join(sorted(unknown))}")
        start = number(segment.get("start_seconds"), "start_seconds")
        end = number(segment.get("end_seconds"), "end_seconds")
        if start < previous_end or end <= start or end > record["duration_seconds"]:
            raise ValueError(f"Segment {index + 1} is overlapping, unsorted, empty, or outside the video")
        previous_end = end
        evidence = optional_text(segment.get("evidence"), "evidence")
        if evidence is None:
            raise ValueError(f"Segment {index + 1} needs evidence from direct video review")
        confidence = segment.get("confidence")
        if confidence is not None and number(confidence, "confidence") > 1:
            raise ValueError("confidence must be between 0 and 1, or null")
        item = {
            "start_seconds": start, "end_seconds": end,
            "song": optional_text(segment.get("song"), "song"),
            "chart": optional_text(segment.get("chart"), "chart"),
            "confidence": confidence, "evidence": evidence,
        }
        if offset is not None:
            item["youtube_start_seconds"] = number(start + offset, "youtube_start_seconds")
            item["youtube_end_seconds"] = number(end + offset, "youtube_end_seconds")
        normalized.append(item)
    return {"schema_version": 1, "method": "manual_video_review",
            "boundary_policy": "silent_song_cover_to_silent_pre_result_black_frame_whole_seconds",
            "media": record,
            "alignment": {"youtube_url": url, "offset_seconds": offset},
            "segments": normalized}


def timestamp(seconds):
    total = math.floor(number(seconds, "timestamp"))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


def render_text(timeline, youtube=False):
    if youtube and timeline["alignment"]["offset_seconds"] is None:
        raise ValueError("YouTube text needs a manually verified alignment offset")
    start_key = "youtube_start_seconds" if youtube else "start_seconds"
    end_key = "youtube_end_seconds" if youtube else "end_seconds"
    lines = ["00:00 auto-generated timeline started"]
    for segment in timeline["segments"]:
        song = segment["song"] or "Unknown song"
        chart = f" {segment['chart']}" if segment["chart"] else ""
        label = f"{song}{chart}"
        lines.append(f"{timestamp(segment[start_key])} {label} start")
        lines.append(f"{timestamp(segment[end_key])} {label} end")
    return "\n".join(lines) + "\n"


def write_json(path, value):
    # Never overwrite a review, an original video, or an earlier result.
    with path.open("x", encoding="utf-8") as output:
        output.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def sample_frames(record, output_dir, times):
    if not 1 <= len(times) <= 100:
        raise ValueError("Request between 1 and 100 frames per call")
    for seconds in times:
        if number(seconds, "frame time") >= record["duration_seconds"]:
            raise ValueError("Frame time must be before the video end")
    output_dir.mkdir(parents=True, exist_ok=False)
    frames = []
    for index, seconds in enumerate(times):
        filename = f"frame-{index + 1:03}.png"
        result = subprocess.run([
            "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info", "-n",
            "-ss", str(seconds), "-copyts", "-i", record["path"],
            "-map", f"0:{record['video_streams'][0]['index']}", "-frames:v", "1",
            "-vf", "showinfo", "-fps_mode", "passthrough", str(output_dir / filename),
        ], capture_output=True, text=True, check=True)
        match = re.search(r"\bn:\s*0\s+pts:\s*-?\d+\s+pts_time:([\d.eE+-]+)", result.stderr)
        if match is None or not (output_dir / filename).is_file():
            raise ValueError(f"No decoded frame at {seconds} seconds")
        pts = float(match.group(1))
        frames.append({"file": filename, "requested_seconds": seconds,
                       "source_pts_seconds": pts,
                       "playback_seconds": pts - record["container_start_seconds"]})
    source = Path(record["path"]).stat()
    if (source.st_size, source.st_mtime_ns) != (record["size_bytes"], record["mtime_ns"]):
        raise ValueError("Media changed during frame sampling; discard this sample directory")
    write_json(output_dir / "frames.json", {"schema_version": 1, "media": record, "frames": frames})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    record_parser = commands.add_parser("record", help="Print a normalized local media record")
    record_parser.add_argument("video", type=Path)
    review_parser = commands.add_parser("review", help="Create an empty review file without overwriting")
    review_parser.add_argument("video", type=Path)
    review_parser.add_argument("output", type=Path)
    frames_parser = commands.add_parser("frames", help="Extract specific review frames and their source timestamps")
    frames_parser.add_argument("video", type=Path)
    frames_parser.add_argument("output_dir", type=Path)
    frames_parser.add_argument("--at", type=float, action="append", required=True, help="Playback seconds; repeatable")
    generate = commands.add_parser("generate", help="Render reviewed segments into JSON and text")
    generate.add_argument("video", type=Path)
    generate.add_argument("review", type=Path)
    generate.add_argument("output_dir", type=Path, help="New directory; must not already exist")
    generate.add_argument("--youtube", action="store_true", help="Apply verified alignment to text only")
    args = parser.parse_args()
    try:
        record = media_record(args.video)
        if args.action == "record":
            print(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False))
        elif args.action == "review":
            write_json(args.output, review_template(record))
            print(f"Review template: {args.output}")
        elif args.action == "frames":
            sample_frames(record, args.output_dir, args.at)
            print(f"Extracted {len(args.at)} review frames in {args.output_dir}")
        else:
            review = json.loads(args.review.read_text(encoding="utf-8"))
            timeline = build_timeline(review, record)
            rendered = render_text(timeline, args.youtube)
            timeline["text_timestamp_basis"] = "youtube" if args.youtube else "local_playback"
            args.output_dir.mkdir(parents=True, exist_ok=False)
            write_json(args.output_dir / "timeline.json", timeline)
            with (args.output_dir / "timeline.txt").open("x", encoding="utf-8") as output:
                output.write(rendered)
            print(f"Generated {len(timeline['segments'])} reviewed segments in {args.output_dir}")
    except (ValueError, OSError) as error:
        parser.error(str(error))
    except subprocess.CalledProcessError as error:
        parser.error(f"Media tool failed: {error.stderr.strip()}")


if __name__ == "__main__":
    main()
