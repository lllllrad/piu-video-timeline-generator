"""Locate HUD profiles and refine observed gameplay boundaries."""
import math
import subprocess

from piu_timeline.vision.detect import detect, similarity
from piu_timeline.metadata.recognition import capture_game, ocr_images
from piu_timeline.tools.timeline import write_json


def find_reference(record, game_roi, evidence_dir):
    duration = record["duration_seconds"]
    times = list(range(30, min(math.ceil(duration), 601), 30))
    if not times:
        times = [duration / 2]
    for index, seconds in enumerate(times):
        if seconds >= duration:
            continue
        frame = capture_game(record, evidence_dir / f"reference-{index:03}.png", seconds, game_roi)
        # The fixed HUD label is English; multilingual OCR can read STAGE as STAG드.
        result = ocr_images([frame["file"]], english=True)[0]
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
