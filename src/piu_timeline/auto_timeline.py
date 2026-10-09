"""Automatically detect gameplay and OCR song/chart labels from a local recording."""
import json
import math
from pathlib import Path
import subprocess
import shutil

from .detect import detect, similarity
from .media import fetch_command, resolve_url
from .recognition import (capture_game, focused_lines, frame_labels, ocr_images,
                          stage_number, summary_stage_row, scene_kind, is_demo_screen, focused_names, chart_mode, center)
from .timeline import media_record, write_json
from .result_stats import extract_stats
from .evidence import resolve_labels, resolve_players, reconcile_sessions
from .ocr import configuration
from .credits import transition_samples, reconcile_players, recover_summary_stages


SELECTION_OFFSETS = (-14, -13, -10, -9, -6, -5, -3)
ANALYSIS_VERSION = 25


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


def recognize_segment(record, roi, start, end, directory, stage=None, previous_end=0, next_start=None, reuse_summary=False):
    directory.mkdir(exist_ok=True)
    retained = directory / "ocr.json"
    existing = json.loads(retained.read_text()) if retained.is_file() else []
    saved = {round(item["requested_seconds"], 3): item for item in existing}
    next_start = record["duration_seconds"] if next_start is None else next_start
    frames = []
    seen = set()

    def acquire(window, times, adaptive=False):
        pending, batch = [], []
        for index, seconds in enumerate(times):
            seconds = round(seconds, 3)
            if (seconds in seen or not previous_end < seconds < next_start
                    or not 0 <= seconds < record["duration_seconds"]):
                continue
            seen.add(seconds)
            if seconds in saved:
                frame = saved[seconds]
            else:
                filename = f"adaptive-{window}-{seconds:.3f}.png" if adaptive else f"{window}-{index}.png"
                frame = capture_game(record, directory / filename, seconds, roi)
                pending.append(frame)
            batch.append({**frame, "window": window})
        recognized = ocr_images([frame["file"] for frame in pending])
        fresh = {frame["file"]: result["lines"] for frame, result in zip(pending, recognized)}
        for frame in batch:
            raw = frame.get("ocr", fresh.get(frame["file"], []))
            scene = scene_kind(raw)
            eligible = ((frame["window"] == "selection" and scene == "selection")
                        or (frame["window"] == "result" and scene in {"result", "summary"}))
            if eligible and (scene != "summary" or reuse_summary) and "focused_ocr" in frame:
                focused = frame["focused_ocr"]
            else:
                focused = focused_lines(frame["file"], scene, roi[2], roi[3]) if eligible else []
            rows = {}
            labels = {"song": None, "chart": None}
            if eligible and scene == "summary":
                # Badge columns move in some Phoenix layouts. Keep title OCR
                # focused, supplement only chart glyphs from the raw screen.
                badge_lines = [line for line in raw if (.15 < center(line)[0] < .31 or .69 < center(line)[0] < .87)
                               and (chart_mode(line["text"]) or line["text"].strip().isdigit())]
                rows = {str(number): row for number in range(1, 7)
                        if (row := summary_stage_row([*focused, *badge_lines], number))}
                labels = rows.get(str(stage), labels)
            elif eligible:
                labels = frame_labels(focused, scene)
            frames.append({**frame, "phase": scene, "scene": scene, "ocr": raw,
                           "focused_ocr": focused, "eligible_screen": eligible, "rows": rows,
                           "identity_eligible": (frame["window"] == "selection" and scene in {"selection", "mode", "unknown"}
                                                 or frame["window"] == "result" and scene in {"result", "summary", "failure"}),
                           **labels})
        # Do not let a later credit establish confidence before deciding
        # whether this play needs additional acquisition.
        stops = [f["requested_seconds"] for f in frames if f["window"] == "result"
                 and f["scene"] in {"selection", "mode", "entry", "demo"}]
        if stops:
            stop = min(stops)
            for frame in frames:
                if frame["window"] == "result" and frame["requested_seconds"] >= stop:
                    frame["eligible_screen"] = frame["identity_eligible"] = False

    acquire("selection", [start + offset for offset in SELECTION_OFFSETS])
    acquire("result", [end + offset for offset in
                       (3, 5, 7, 8, 9, 10, 11, 12, 14, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60)])
    # The first seconds may contain the only failed/short result screen.
    acquire("result", [end + offset for offset in (.5, 1.25, 2)], adaptive=True)
    # A previously discovered brief screen remains evidence on every replay,
    # even if it resolved the uncertainty that originally triggered its scan.
    for window in ("selection", "result"):
        acquire(window, [item["requested_seconds"] for item in existing
                         if item.get("window") == window], adaptive=True)

    # A singleton short screen receives close neighbors instead of losing its
    # fields solely because the regular sampling grid caught it only once.
    for scene in ("result", "summary", "failure"):
        singletons = [f for f in frames if f["window"] == "result" and f["scene"] == scene
                      and (f["eligible_screen"] or f["identity_eligible"])]
        if len(singletons) == 1:
            at = singletons[0]["requested_seconds"]
            acquire("result", [at - .3, at + .3], adaptive=True)

    def focus_identities():
        candidates = sorted([f for f in frames if f["identity_eligible"]],
                            key=lambda f: (f["scene"] == "unknown", abs(f["requested_seconds"] -
                                           (start if f["window"] == "selection" else end))))
        identities = resolve_players(frames)
        already_focused = sum("name_ocr" in f for f in candidates)
        if already_focused >= 2 and identities and all(p.get("name") and
                p["fields"]["name"].get("discriminator_status") != "unknown" for p in identities.values()):
            return identities
        checked = 0
        for frame in candidates:
            if "name_ocr" in frame:
                continue
            frame["name_ocr"] = focused_names(frame["file"], roi[2], roi[3])
            checked += 1
            identities = resolve_players(frames)
            if already_focused + checked >= 2 and identities and all(p.get("name") and
                    p["fields"]["name"].get("discriminator_status") != "unknown" for p in identities.values()):
                return identities
            if checked >= 8:
                break
        return resolve_players(frames)

    identities = focus_identities()
    labels, confidence = resolve_labels(frames)
    no_result = not any(f["scene"] in {"result", "summary", "failure"} for f in frames if f["window"] == "result")
    if (not identities or any(not p.get("name") for p in identities.values())
            or any(v is None for v in labels.values()) or no_result):
        # A sparse look farther back captures the account/mode/selection header
        # while avoiding OCR over a long idle gap. Only unresolved plays need it.
        acquire("selection", [start - offset for offset in (20, 30, 45, 60)], adaptive=True)
        for window, begin, stop in (("result", end, min(end + 65, next_start)),
                                    ("selection", max(previous_end + .5, start - 60), start - 2)):
            plan = directory / f"transitions-v1-{window}.json"
            if plan.is_file():
                times = json.loads(plan.read_text())
            else:
                times = transition_samples(record, roi, begin, stop)
                write_json(plan, times)
            acquire(window, times, adaptive=True)
        focus_identities()
    frames.sort(key=lambda f: f["requested_seconds"])
    labels, confidence = resolve_labels(frames)
    retained.unlink(missing_ok=True)
    write_json(retained, frames)
    return labels, confidence, str(retained)


def recover_stage(path, width, height):
    evidence = json.loads(path.read_text())
    if not isinstance(evidence, dict):
        return None
    recognized = evidence.get("recognized") or stage_number(evidence.get("focused_ocr", [])) or stage_number(evidence.get("ocr", []))
    if recognized:
        if not evidence.get("recognized"):
            evidence["recognized"] = recognized
            path.unlink()
            write_json(path, evidence)
        return recognized
    if evidence.get("stage_crop_version") == 2:
        return None
    # Anchor to the observed HUD: single and double modes have different x.
    labels = [line for line in evidence.get("ocr", [])
              if line["text"].strip().upper() in {"STAGE", "ISTAGE"} and center(line)[1] < .1]
    if len(labels) != 1:
        return None
    x, y, w, h = max(0, center(labels[0])[0] - .04), 0., .08, .085
    px, py, pw, ph = int(x * width), int(y * height), int(w * width), int(h * height)
    crop = path.with_name("stage-focus-v2.png")
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", evidence["file"],
                    "-vf", f"crop={pw}:{ph}:{px}:{py},scale=iw*6:ih*6", str(crop)],
                   check=True, capture_output=True)
    lines = []
    for line in ocr_images([crop], english=True)[0]["lines"]:
        bx, by, bw, bh = line["box"]
        lines.append({**line, "box": [(px + bx * pw) / width, (py + by * ph) / height,
                                     bw * pw / width, bh * ph / height], "image": str(crop)})
    evidence["stage_crop_version"] = 2
    evidence["focused_ocr"] = lines
    evidence["recognized"] = stage_number(lines)
    path.unlink()
    write_json(path, evidence)
    return evidence["recognized"]


def recognize_stage(record, roi, start, end, directory):
    seconds = min(start + 5, (start + end) / 2)
    frame = capture_game(record, directory / "stage.png", seconds, roi)
    lines = ocr_images([frame["file"]], english=True)[0]["lines"]
    recognized = stage_number(lines)
    evidence = {**frame, "ocr": lines, "recognized": recognized}
    write_json(directory / "stage.json", evidence)
    return (recognized["value"] if recognized else None), str(directory / "stage.json")


def analyze(video, output, game_roi=None, provenance=None, retained=None):
    """Persist recognition data independently of player selection or presentation."""
    record = media_record(video)
    stream = record["video_streams"][0]
    # Known stream layout; explicit crop supports direct game captures.
    roi = game_roi or (0, 0, round(stream["width"] * 1300 / 1920), round(stream["height"] * 730 / 1080))
    x, y, width, height = roi
    if x + width > stream["width"] or y + height > stream["height"]:
        raise ValueError("Game ROI exceeds video dimensions")
    cached_segments = {}
    reuse_summary = False
    if retained:
        retained_document = json.loads((retained / "analysis.json").read_text())
        reuse_summary = retained_document.get("analysis_version", 0) >= 9
        from .storage import relocate_evidence
        shutil.copytree(retained, output)
        relocate_evidence(output, output, source=retained)
        (output / "analysis.json").unlink(missing_ok=True)
        evidence_dir = output / "evidence"
        profiles = json.loads((output / "profiles.json").read_text())
        candidates = json.loads((output / "candidates.json").read_text())["candidates"]
        for path in output.glob("segment-*.json"):
            cached_segments[path.stem] = json.loads(path.read_text())
            path.unlink()
        for path in output.glob("play-*.json"):
            path.unlink()
        print("Reusing verified acquisition; refreshing summary layout and evidence decisions...", flush=True)
    else:
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
    all_observations = []
    segment_files = []
    for index, candidate in enumerate(candidates):
        profile_index = candidate["profile_index"]
        hud, reference = profiles[profile_index]["hud"], references[profile_index]
        print(f"Refining and recognizing segment {index + 1}/{len(candidates)}...", flush=True)
        cached = cached_segments.get(f"segment-{index + 1:03}")
        if cached:
            start, end = cached["start_seconds"], cached["end_seconds"]
            start_evidence, end_evidence = cached["boundary_evidence"]["start"], cached["boundary_evidence"]["end"]
        else:
            start, start_evidence = refine_boundary(record, hud, reference, candidate["start_seconds"], "start")
            end, end_evidence = refine_boundary(record, hud, reference, candidate["end_seconds"], "end")
        if end <= start or (segments and start < segments[-1]["end_seconds"]):
            raise ValueError("Automatic refinement produced invalid/overlapping intervals")
        segment_dir = evidence_dir / f"segment-{index + 1:03}"
        segment_dir.mkdir(exist_ok=True)
        stage_path = segment_dir / "stage.json"
        if stage_path.is_file():
            recognized = recover_stage(stage_path, width, height)
            stage, stage_evidence = recognized["value"] if recognized else None, str(stage_path)
        else:
            stage, stage_evidence = recognize_stage(record, roi, start, end, segment_dir)
        if stage is None:
            recognized = recover_stage(Path(stage_evidence), width, height)
            stage = recognized["value"] if recognized else None
        stage_data = json.loads(Path(stage_evidence).read_text())
        if isinstance(stage_data, dict) and is_demo_screen(stage_data.get("ocr", [])):
            print(f"Rejected candidate {index + 1}: explicit DEMO PLAY screen", flush=True)
            continue
        labels, support, ocr_file = recognize_segment(record, roi, start, end, segment_dir, stage,
                                                      previous_end=candidates[index - 1]["end_seconds"] if index else 0,
                                                      next_start=candidates[index + 1]["start_seconds"] - 8
                                                      if index + 1 < len(candidates) else None,
                                                      reuse_summary=reuse_summary)
        # Keep unresolved candidates until later credit summaries have had a
        # chance to identify their stage. Early rejection loses real failed plays.
        segments.append({"start_seconds": start, "end_seconds": end, "stage": stage,
                         "stage_evidence": stage_evidence, "hud_profile": profile_index, **labels,
                         "confidence": support, "boundary_evidence": {"start": start_evidence, "end": end_evidence},
                         "ocr_evidence": ocr_file,
                         "needs_review": any(labels[key] is None for key in labels)
                                         or stage is None
                                         or not start_evidence["refined"] or not end_evidence["refined"]
                                         or any(value and (value["mean_ocr_confidence"] < .7
                                                           or value.get("supporting_frames", 0) < 2)
                                                for value in support.values())})
        observations = json.loads(Path(ocr_file).read_text())
        all_observations.append(observations)
        segments[-1]["players"] = resolve_players(observations, stage_data if isinstance(stage_data, dict) else None)
        stats_dir = evidence_dir / f"stats-{index + 1:03}"
        stats = extract_stats(observations, stats_dir, width, height)
        segments[-1]["results"] = stats
        segments[-1]["needs_review"] |= stats["needs_review"]
        segments[-1]["needs_review"] |= any(
            p["fields"]["name"].get("mean_ocr_confidence", 0) < .7
            or p["fields"]["name"]["status"] != "recognized"
            for p in segments[-1]["players"].values())
        segment_files.append(output / f"segment-{index + 1:03}.json")
        write_json(segment_files[-1], segments[-1])
    recover_summary_stages(segments, all_observations)
    reconcile_sessions(segments, all_observations)
    reconcile_players(segments, all_observations)
    # Caption-preserving result badges can correct rotated focused glyphs.
    for segment in segments:
        players = list(segment["results"]["players"].values())
        charts = {p["fields"]["chart"].get("value") for p in players
                  if p["fields"]["chart"]["status"] == "recognized" and p["fields"]["chart"].get("value")}
        if players and len(charts) == 1 and all(p["fields"]["chart"]["status"] == "recognized"
                and p["fields"]["chart"].get("method") in {"caption_context_ocr", "full_screen_badge_ocr", "full_screen_ocr"}
                for p in players):
            corrected = next(iter(charts))
            old = segment.get("chart")
            # SINGLE and VERY HARD are alternate labels for the same basic badge.
            same_basic = old and corrected.startswith("VERY HARD ") and old == "S" + corrected.split()[-1]
            if old != corrected and not same_basic:
                segment["chart"] = corrected
                segment["confidence"]["chart"] = {**players[0]["fields"]["chart"], "phase": "result"}
                segment["chart_correction"] = {"previous": old, "method": "upright_result_badge",
                                                "evidence": segment["results"]["evidence"]}
    accepted = []
    for path, segment in zip(segment_files, segments):
        path.unlink()
        if segment["song"] is None and segment["chart"] is None:
            print(f"Rejected {path.stem}: no labels after credit reconciliation", flush=True)
            continue
        segment["needs_review"] = (any(segment.get(key) is None for key in ("song", "chart", "stage"))
            or segment["results"]["needs_review"]
            or any(not segment["boundary_evidence"][key]["refined"] for key in ("start", "end"))
            or any(value and (value.get("mean_ocr_confidence", 0) < .7
                             or value.get("supporting_frames", 0) < 2)
                   for value in segment["confidence"].values())
            or any(not player.get("name") or player["fields"]["name"]["status"] != "recognized"
                   or player["fields"]["name"].get("mean_ocr_confidence", 0) < .7
                   for player in segment["players"].values())
            or bool(segment.get("label_revisions")))
        accepted.append(segment)
        write_json(path, segment)
    segments = accepted
    stat = video.resolve().stat()
    if (stat.st_size, stat.st_mtime_ns) != (record["size_bytes"], record["mtime_ns"]):
        raise ValueError("Source changed during automatic processing")
    result = {"schema_version": 1, "analysis_version": ANALYSIS_VERSION,
              "ocr_configuration": configuration(), "artifact_type": "video_analysis", "method": "automatic_hud_ocr", "media": record,
              "provenance": provenance or {"kind": "local", "network_used": False},
              "game_roi": list(roi), "alignment": {"youtube_url": None, "offset_seconds": None},
              "timestamp_basis": "local_playback", "segments": segments,
              "warnings": ["OCR confidence is not calibrated correctness probability.",
                           "Unknown or conflicting labels remain null; inspect evidence before publication.",
                           "YouTube alignment is not inferred from local filenames or duration metadata."]}
    write_json(output / "analysis.json", result)
    print(f"Analyzed {len(segments)} gameplay segments in {output}")
    return result
