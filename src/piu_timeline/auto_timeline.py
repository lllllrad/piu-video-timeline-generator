"""Automatically detect gameplay and OCR song/chart labels from a local recording."""
import json
import math
from pathlib import Path
import subprocess

from .detect import detect, similarity
from .media import fetch_command, resolve_url
from .recognition import capture_game, consensus, focused_lines, frame_labels, is_result_screen, ocr_images, summary_chart, summary_song
from .timeline import media_record, write_json
from .result_stats import extract_stats


def resolve_source(source, raw_dir=None):
    local = Path(source).expanduser()
    if local.is_file():
        return local.resolve(), {"kind": "local", "network_used": False}
    url = resolve_url(source)
    if raw_dir is None:
        raise ValueError("YouTube sources require a local raw directory")
    destination = Path(raw_dir)
    destination.mkdir(parents=True, exist_ok=True)
    existing = [path.resolve() for path in destination.iterdir()
                if path.is_file() and path.suffix.lower() in {".mkv", ".mp4", ".webm", ".mov"}]
    if len(existing) == 1:
        return existing[0], {"kind": "cached_youtube", "url": url, "network_used": False}
    if len(existing) > 1:
        raise ValueError(f"Multiple videos found in {destination}")
    command = fetch_command(source, destination)
    command[-2:-2] = ["--print", "after_move:PIU_FILE:%(filepath)s"]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    paths = [Path(line.removeprefix("PIU_FILE:")).resolve() for line in result.stdout.splitlines()
             if line.startswith("PIU_FILE:")]
    if len(paths) != 1 or not paths[0].is_file() or not paths[0].is_relative_to(destination):
        raise ValueError("Download did not return exactly one completed video")
    return paths[0], {"kind": "youtube_download", "url": url, "network_used": True,
                      "timing_policy": "full untrimmed download; no local offset inferred"}


def find_reference(record, game_roi, evidence_dir):
    duration = record["duration_seconds"]
    times = list(range(30, min(math.ceil(duration), 601), 30))
    if not times:
        times = [duration / 2]
    for index, seconds in enumerate(times):
        if seconds >= duration:
            continue
        frame = capture_game(record, evidence_dir / f"reference-{index:03}.png", seconds, game_roi)
        result = ocr_images([frame["file"]])[0]
        for line in result["lines"]:
            if line["text"].strip().upper() != "STAGE" or line["box"][1] > .12:
                continue
            x, y, w, h = line["box"]
            gx, gy, gw, gh = game_roi
            # Keep the static word, not the changing stage number below it.
            left, top = max(0, int(x * gw) - 2), max(0, int(y * gh) - 2)
            width, height = min(gw - left, math.ceil(w * gw) + 4), min(gh - top, math.ceil(h * gh) + 4)
            return frame["playback_seconds"], (gx + left, gy + top, width, height), {**frame, "ocr": result}
    raise ValueError("No STAGE HUD found in the first ten minutes. Check --game-roi; this layout may be unsupported.")


def reference_patch(record, roi, seconds):
    x, y, width, height = roi
    return subprocess.run([
        "ffmpeg", "-v", "error", "-nostdin", "-ss", str(seconds), "-noautorotate", "-i", record["path"],
        "-map", f"0:{record['video_streams'][0]['index']}", "-frames:v", "1",
        "-vf", f"crop={width}:{height}:{x}:{y},scale=64:16,format=gray", "-f", "rawvideo", "pipe:1",
    ], check=True, capture_output=True).stdout


def merge_profile_candidates(profiles):
    """Keep one reference per interval; overlapping profiles must agree on bounds."""
    candidates = sorted(({**candidate, "profile_index": index}
                         for index, profile in enumerate(profiles)
                         for candidate in profile["detection"]["candidates"]),
                        key=lambda item: item["start_seconds"])
    merged = []
    for candidate in candidates:
        if merged and candidate["start_seconds"] < merged[-1]["end_seconds"]:
            previous = merged[-1]
            if max(abs(candidate[key] - previous[key]) for key in ("start_seconds", "end_seconds")) > 8:
                raise ValueError("HUD profiles disagree on overlapping gameplay intervals; inspect candidates")
            if candidate["mean_match_score"] > previous["mean_match_score"]:
                merged[-1] = candidate
        else:
            merged.append(candidate)
    return merged


def discover_profiles(record, game_roi, evidence_dir, initial):
    """Search uncovered parts of the entire recording for changed HUD positions."""
    profiles = [initial]
    gx, gy, gw, gh = game_roi
    for index, seconds in enumerate(range(30, math.ceil(record["duration_seconds"]), 30)):
        if any(c["start_seconds"] - 8 <= seconds <= c["end_seconds"] + 8
               for p in profiles for c in p["detection"]["candidates"]):
            continue
        # Only the HUD band is an input, never chat or the camera panel.
        band = (gx, gy, gw, math.ceil(gh * .12))
        frame = capture_game(record, evidence_dir / f"hud-search-{index:04}.png", seconds, band)
        result = ocr_images([frame["file"]], english=True)[0]
        for line in result["lines"]:
            if line["text"].strip().upper() != "STAGE":
                continue
            x, y, w, h = line["box"]
            left, top = max(0, int(x * gw) - 2), max(0, int(y * band[3]) - 2)
            hud = (gx + left, gy + top, min(gw - left, math.ceil(w * gw) + 4),
                   min(band[3] - top, math.ceil(h * band[3]) + 4))
            if any(abs(hud[0] - p["hud"][0]) < gw * .015 and abs(hud[1] - p["hud"][1]) < gh * .015
                   for p in profiles):
                continue
            print(f"Found additional HUD {hud} at {seconds}s; scanning profile...", flush=True)
            detected = detect(record, hud, frame["playback_seconds"], min_duration=10)
            profile = {"hud": hud, "at": frame["playback_seconds"],
                       "evidence": {**frame, "ocr": result}, "detection": detected}
            write_json(evidence_dir / f"profile-{len(profiles):02}.json", profile)
            profiles.append(profile)
    return profiles


def refine_boundary(record, roi, reference, approximate, kind, threshold=.9, radius=8, step=.1):
    begin = max(0, approximate - radius)
    stop = min(record["duration_seconds"], approximate + radius)
    x, y, width, height = roi
    pixels = subprocess.run([
        "ffmpeg", "-v", "error", "-nostdin", "-ss", str(begin), "-noautorotate", "-i", record["path"],
        "-map", f"0:{record['video_streams'][0]['index']}", "-t", str(stop - begin),
        "-vf", f"fps=1/{step}:start_time=0,crop={width}:{height}:{x}:{y},scale=64:16,format=gray",
        "-f", "rawvideo", "pipe:1",
    ], capture_output=True, check=True).stdout
    scores = [similarity(pixels[i:i + 1024], reference) for i in range(0, len(pixels) - 1023, 1024)]
    matching = [score >= threshold for score in scores]
    transitions = []
    for i in range(1, len(matching)):
        if kind == "start" and not matching[i - 1] and all(matching[i:i + 5]) and len(matching[i:i + 5]) == 5:
            transitions.append(i)
        if kind == "end" and matching[i - 1] and not any(matching[i:i + 5]) and len(matching[i:i + 5]) == 5:
            transitions.append(i)
    if not transitions:
        return approximate, {"refined": False, "reason": "No stable transition in search window"}
    index = min(transitions, key=lambda i: abs(begin + i * step - approximate))
    seconds = round(begin + index * step, 3)
    return seconds, {"refined": True, "grid_step_seconds": step,
                     "search_window": [begin, stop], "transition_bracket": [round(seconds - step, 3), seconds],
                     "note": "Decoded frame sampling; allow one sampling step of quantization error"}


def singleton_title(observations):
    candidates = [item["song"] for item in observations if item.get("song")]
    return candidates[0] if len(candidates) == 1 and candidates[0]["confidence"] >= .9 else None


def corroborated_result_title(observations, chart):
    candidates = [item["song"] for item in observations if item.get("phase") == "result"
                  and item.get("song") and item.get("chart", {}).get("text") == chart
                  and item["song"]["confidence"] >= .5]
    keys = {"".join(item["text"].split()).casefold() for item in candidates}
    return max(candidates, key=lambda item: item["confidence"]) if len(keys) == 1 else None


def recognize_segment(record, roi, start, end, directory):
    directory.mkdir()
    frames = []
    for phase, times in [("selection", [start - 14, start - 12, start - 10, start - 8, start - 6, start - 4, start - 3]),
                         ("result", [end + offset for offset in (3, 5, 7, 8, 9, 10, 11, 12)])]:
        for index, seconds in enumerate(times):
            if not 0 <= seconds < record["duration_seconds"]:
                continue
            frame = capture_game(record, directory / f"{phase}-{index}.png", seconds, roi)
            frames.append({**frame, "phase": phase})
    recognized = ocr_images([frame["file"] for frame in frames])
    observations = []
    for frame, result in zip(frames, recognized):
        eligible = frame["phase"] != "result" or is_result_screen(result["lines"])
        focused = focused_lines(frame["file"], frame["phase"], roi[2], roi[3]) if eligible else []
        labels = frame_labels(focused, frame["phase"]) if eligible else {"song": None, "chart": None}
        observations.append({**frame, "ocr": result["lines"], "focused_ocr": focused,
                             "eligible_screen": eligible, **labels})
    # Results describe the chart actually played, so prefer them over selection UI.
    labels, confidence = {}, {}
    for field in ("song", "chart"):
        for phase in ("result", "selection"):
            value, support = consensus([item for item in observations if item["phase"] == phase], field)
            if value is not None:
                labels[field], confidence[field] = value, {**support, "phase": phase}
                break
        else:
            labels[field], confidence[field] = None, None
    if labels["song"] is None:
        candidate = corroborated_result_title(observations, labels.get("chart")) or singleton_title(observations)
        if candidate:
            labels["song"] = candidate["text"].strip()
            confidence["song"] = {"supporting_frames": 1, "recognized_frames": 1,
                                  "mean_ocr_confidence": candidate["confidence"],
                                  "alternatives": {labels["song"]: 1},
                                  "phase": "selection_or_result",
                                  "agreement": "high_confidence_single_frame"}
    if labels["song"] is None or labels["chart"] is None:
        summary_observations = []
        for index, seconds in enumerate((end + 12, end + 14, end + 16)):
            if seconds >= record["duration_seconds"]:
                continue
            frame = capture_game(record, directory / f"summary-{index}.png", seconds, roi)
            raw = ocr_images([frame["file"]])[0]["lines"]
            is_summary = any("".join(line["text"].upper().split()) == "PLAYRESULT" for line in raw)
            focused = focused_lines(frame["file"], "summary", roi[2], roi[3]) if is_summary else []
            item = {**frame, "phase": "summary", "ocr": raw, "focused_ocr": focused,
                    "song": summary_song(focused, labels["chart"]) if is_summary and labels["chart"] else None,
                    "chart": summary_chart(focused, labels["song"]) if is_summary and labels["song"] else None}
            summary_observations.append(item)
        for field in ("song", "chart"):
            if labels[field] is not None:
                continue
            value, support = consensus(summary_observations, field)
            if value:
                labels[field], confidence[field] = value, {**support, "phase": "summary"}
        observations.extend(summary_observations)
    write_json(directory / "ocr.json", observations)
    return labels, confidence, str(directory / "ocr.json")


def analyze(video, output, game_roi=None, provenance=None):
    """Persist recognition data independently of player selection or presentation."""
    record = media_record(video)
    stream = record["video_streams"][0]
    # Known stream layout; explicit crop supports direct game captures.
    roi = game_roi or (0, 0, round(stream["width"] * 1300 / 1920), round(stream["height"] * 730 / 1080))
    x, y, width, height = roi
    if x + width > stream["width"] or y + height > stream["height"]:
        raise ValueError("Game ROI exceeds video dimensions")
    output.mkdir(parents=True, exist_ok=False)
    evidence_dir = output / "evidence"
    evidence_dir.mkdir()
    print("Locating gameplay HUD with local OCR...", flush=True)
    at, hud, reference_evidence = find_reference(record, roi, evidence_dir)
    write_json(output / "reference.json", reference_evidence)
    print(f"Scanning gameplay using HUD {hud} at {at}s...", flush=True)
    detected = detect(record, hud, at, min_duration=10)
    print("Checking uncovered video for alternate HUD positions...", flush=True)
    profiles = discover_profiles(record, roi, evidence_dir,
                                 {"hud": hud, "at": at, "evidence": reference_evidence, "detection": detected})
    write_json(output / "profiles.json", profiles)
    candidates = merge_profile_candidates(profiles)
    write_json(output / "candidates.json", {"method": "multi_profile_hud", "candidates": candidates})
    references = [reference_patch(record, p["hud"], p["at"]) for p in profiles]
    segments = []
    for index, candidate in enumerate(candidates):
        profile_index = candidate["profile_index"]
        hud, reference = profiles[profile_index]["hud"], references[profile_index]
        print(f"Refining and recognizing segment {index + 1}/{len(candidates)}...", flush=True)
        start, start_evidence = refine_boundary(record, hud, reference, candidate["start_seconds"], "start")
        end, end_evidence = refine_boundary(record, hud, reference, candidate["end_seconds"], "end")
        if end <= start or (segments and start < segments[-1]["end_seconds"]):
            raise ValueError("Automatic refinement produced invalid/overlapping intervals")
        labels, support, ocr_file = recognize_segment(record, roi, start, end, evidence_dir / f"segment-{index + 1:03}")
        segments.append({"start_seconds": start, "end_seconds": end, "hud_profile": profile_index, **labels,
                         "confidence": support, "boundary_evidence": {"start": start_evidence, "end": end_evidence},
                         "ocr_evidence": ocr_file,
                         "needs_review": any(labels[key] is None for key in labels)
                                         or not start_evidence["refined"] or not end_evidence["refined"]
                                         or any(value and (value["mean_ocr_confidence"] < .7
                                                           or value.get("supporting_frames", 0) < 2)
                                                for value in support.values())})
        observations = json.loads(Path(ocr_file).read_text())
        stats = extract_stats(observations, evidence_dir / f"stats-{index + 1:03}", width, height)
        segments[-1]["results"] = stats
        segments[-1]["needs_review"] |= stats["needs_review"]
        write_json(output / f"segment-{index + 1:03}.json", segments[-1])
    stat = video.resolve().stat()
    if (stat.st_size, stat.st_mtime_ns) != (record["size_bytes"], record["mtime_ns"]):
        raise ValueError("Source changed during automatic processing")
    result = {"schema_version": 1, "artifact_type": "video_analysis", "method": "automatic_hud_ocr", "media": record,
              "provenance": provenance or {"kind": "local", "network_used": False},
              "game_roi": list(roi), "alignment": {"youtube_url": None, "offset_seconds": None},
              "timestamp_basis": "local_playback", "segments": segments,
              "warnings": ["OCR confidence is not calibrated correctness probability.",
                           "Unknown or conflicting labels remain null; inspect evidence before publication.",
                           "YouTube alignment is not inferred from local filenames or duration metadata."]}
    write_json(output / "analysis.json", result)
    print(f"Analyzed {len(segments)} gameplay segments in {output}")
    return result
