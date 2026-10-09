"""Player-separated result OCR; never infer missing judgment counts as zero."""
from collections import Counter
from pathlib import Path
import json
import re
import subprocess

from .recognition import chart_mode, center, frame_labels, is_result_screen, is_stage_break, ocr_images, rival_slots
from .timeline import write_json

COUNT_FIELDS = ("perfect", "great", "good", "bad", "miss", "max_combo")
FIELDS = (*COUNT_FIELDS, "score", "chart")
SIDES = {"p1": "left", "p2": "right"}
ROW_Y = dict(zip(COUNT_FIELDS, (.434, .487, .540, .593, .646, .699)))


def number_at(lines, cx, cy, dx, dy, maximum):
    candidates = [line for line in lines
                  if abs(center(line)[0] - cx) < dx and abs(center(line)[1] - cy) < dy
                  and re.fullmatch(r"[0-9]{1,8}", line["text"].strip())
                  and int(line["text"]) <= maximum and line["confidence"] >= .5]
    values = {int(line["text"]) for line in candidates}
    if len(values) != 1:
        return None
    best = max(candidates, key=lambda line: line["confidence"])
    return {"value": int(best["text"]), "confidence": best["confidence"], "raw": best}


def parse_result(lines):
    """Coordinates belong to the normalized, unmirrored game image, not the stream."""
    players = {}
    rivals = rival_slots(lines)
    for player, side in SIDES.items():
        left = side == "left"
        region = [line for line in lines if (center(line)[0] < .45 if left else center(line)[0] > .55)]
        chart = frame_labels(region, "result")["chart"]
        cx = .335 if left else .665
        values = {field: number_at(region, cx, y, .04, .019, 999999) for field, y in ROW_Y.items()}
        values["score"] = number_at(region, .185 if left else .815, .414, .115, .028, 99999999)
        values["chart"] = ({"value": chart["text"], "confidence": chart["confidence"], "raw": chart}
                           if chart else None)
        score_label = any(re.sub(r"[^A-Z]", "", line["text"].upper()) == "SCORE"
                          and .32 < center(line)[1] < .39 for line in region)
        # A readable badge or a score panel corroborated by several judgment rows
        # establishes a slot; a stray digit in a background video does not.
        present = bool(chart or (score_label and values["score"]
                                and sum(values[field] is not None for field in COUNT_FIELDS) >= 3))
        players[player] = {"side": side, "present": present and player not in rivals, "fields": values,
                           "role": "rival" if player in rivals else "player"}
    # Phoenix displays one shared badge for two players on the same chart.
    # Both numeric panels must be established, and any unreadable separate
    # badge glyphs prevent treating that slot as intentionally absent.
    charts = [slot for slot in players if players[slot]["fields"]["chart"]]
    if len(charts) == 1 and all(p["present"] for p in players.values()):
        source = charts[0]
        target = "p2" if source == "p1" else "p1"
        cx = .665 if target == "p2" else .335
        occupied = any(abs(center(line)[0] - cx) < .05 and .25 < center(line)[1] < .36
                       and (chart_mode(line["text"]) or re.fullmatch(r"\d{1,2}", line["text"].strip()))
                       for line in lines)
        if not occupied:
            players[target]["fields"]["chart"] = {**players[source]["fields"]["chart"],
                                                   "shared_from": source}
    return players


def focused_stats(frame, directory, index, width, height):
    # Separate numeric columns from central labels and side background art.
    boxes = [("p1-counts", .30, .408, .09, .315), ("p2-counts", .61, .408, .09, .315),
             ("p1-score", .075, .33, .22, .115), ("p2-score", .70, .33, .23, .115),
             ("p1-chart", .26, .25, .15, .14), ("p2-chart", .59, .25, .15, .14)]
    paths, regions = [], []
    for name, x, y, w, h in boxes:
        px, py, pw, ph = int(x * width), int(y * height), int(w * width), int(h * height)
        path = directory / f"frame-{index}-{name}.png"
        processing = f"crop={pw}:{ph}:{px}:{py},scale=iw*4:ih*4"
        if name.endswith("counts"):
            processing += r",format=gray,lut=y=if(gt(val\,180)\,255\,0)"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(frame),
                        "-vf", processing, str(path)],
                       check=True, capture_output=True)
        paths.append(path)
        regions.append((px / width, py / height, pw / width, ph / height))
    mapped = []
    for result, (x, y, w, h) in zip(ocr_images(paths, english=True), regions):
        for line in result["lines"]:
            bx, by, bw, bh = line["box"]
            mapped.append({**line, "box": [x + bx * w, y + by * h, bw * w, bh * h],
                           "image": result["path"]})
    return mapped


def contextual_stats(frame, directory, index, width, height):
    """Keep upright captions beside numbers to prevent automatic rotated OCR."""
    boxes = [("counts", .27, .40, .46, .325),
             ("charts", .27, .25, .46, .20),
             ("p1-score", .075, .315, .34, .13), ("p2-score", .585, .315, .34, .13)]
    paths, regions = [], []
    for name, x, y, w, h in boxes:
        px, py, pw, ph = int(x * width), int(y * height), int(w * width), int(h * height)
        path = directory / f"context-v2-{index}-{name}.png"
        if not path.is_file():
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(frame),
                            "-vf", f"crop={pw}:{ph}:{px}:{py},scale=iw*4:ih*4", str(path)],
                           check=True, capture_output=True)
        paths.append(path)
        regions.append((px / width, py / height, pw / width, ph / height))
    mapped = []
    for result, (x, y, w, h) in zip(ocr_images(paths, english=True), regions):
        for line in result["lines"]:
            bx, by, bw, bh = line["box"]
            mapped.append({**line, "box": [x + bx * w, y + by * h, bw * w, bh * h],
                           "image": result["path"]})
    return mapped


def contrast_score(frame, directory, index, width, height, player):
    """A second, bounded score channel for glyphs still misread as letters."""
    x, y, w, h = (.075 if player == "p1" else .585), .315, .34, .13
    px, py, pw, ph = int(x * width), int(y * height), int(w * width), int(h * height)
    path = directory / f"score-contrast-v1-{index}-{player}.png"
    if not path.is_file():
        processing = f"crop={pw}:{ph}:{px}:{py},scale=iw*2:ih*2" + r",format=gray,lut=y=if(gt(val\,180)\,255\,0)"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(frame),
                        "-vf", processing, str(path)], check=True, capture_output=True)
    mapped = []
    for line in ocr_images([path], english=True)[0]["lines"]:
        bx, by, bw, bh = line["box"]
        mapped.append({**line, "box": [(px + bx * pw) / width, (py + by * ph) / height,
                                      bw * pw / width, bh * ph / height], "image": str(path)})
    return mapped


def field_consensus(observations, min_confidence=.7):
    values = [item for item in observations if item is not None]
    counts = Counter(item["value"] for item in values)
    if not counts:
        return {"value": None, "status": "unknown", "supporting_frames": 0, "alternatives": {}}
    winner, votes = counts.most_common(1)[0]
    accepted = votes >= 2 and votes > len(values) / 2
    selected = [item for item in values if item["value"] == winner]
    confidence = sum(item["confidence"] for item in selected) / votes
    return {"value": winner if accepted and confidence >= min_confidence else None,
            "status": "recognized" if accepted and confidence >= min_confidence else "conflict" if len(counts) > 1 else "unknown",
            "supporting_frames": votes, "recognized_frames": len(values),
            "mean_ocr_confidence": confidence, "alternatives": {str(k): v for k, v in counts.items()}}


def aggregate_frames(frames):
    players = {}
    for player, side in SIDES.items():
        present = [frame["players"][player] for frame in frames if frame["players"][player]["present"]]
        if not present:
            continue
        fields = {key: field_consensus([item["fields"][key] for item in present]) for key in FIELDS}
        players[player] = {"player_id": player, "side": side,
                           "presence": "recognized" if len(present) >= 2 else "uncertain",
                           "supporting_frames": len(present),
                           **{key: fields[key]["value"] for key in FIELDS}, "fields": fields,
                           "needs_review": len(present) < 2 or any(fields[key]["status"] != "recognized" for key in FIELDS)}
    return {"schema_version": 1, "method": "player_result_ocr", "players": players,
            "status": "recognized" if players and all(p["presence"] == "recognized" for p in players.values()) else "unknown",
            "player_mapping": "unmirrored game coordinates: p1=left, p2=right",
            "needs_review": not players or any(p["needs_review"] for p in players.values())}


def extract_stats(observations, directory, width, height):
    directory.mkdir(parents=True, exist_ok=True)
    saved = directory / "frames.json"
    frames = json.loads(saved.read_text()) if saved.is_file() else []
    # Reparse retained glyphs when layout/mode support changes; no decoding or
    # numeric OCR is necessary to recognize an additional displayed badge.
    for frame in frames:
        if "ocr" in frame:
            markers = [line for line in frame.get("source_ocr", []) if rival_slots([line])]
            frame["players"] = parse_result([*frame["ocr"], *markers])
    seen = {frame["source_pts_seconds"] for frame in frames}
    for index, observation in enumerate(observations):
        if observation.get("phase") != "result" or not observation.get("eligible_screen"):
            continue
        pts = observation.get("source_pts_seconds")
        if pts is None or pts in seen:
            continue
        seen.add(pts)
        raw = observation.get("ocr", [])
        if not is_result_screen(raw):
            continue
        frame = Path(observation["file"]).resolve()
        lines = focused_stats(frame, directory, f"pts-{pts:.3f}", width, height)
        # Keep only SCORE markers from raw OCR; numeric extraction uses dedicated
        # crops so mixed-language/BGA OCR cannot outvote focused numeric evidence.
        lines += [line for line in raw if re.sub(r"[^A-Z]", "", line["text"].upper()) in {"SCORE", "RIVAL"}]
        frames.append({"file": str(frame), "source_pts_seconds": pts,
                       "playback_seconds": observation.get("playback_seconds"),
                       "ocr": lines, "source_ocr": raw, "players": parse_result(lines)})
    # Retained full-screen chart glyphs provide an independent upright channel.
    raw_by_pts = {o.get("source_pts_seconds"): o.get("ocr", []) for o in observations}
    for frame in frames:
        frame.setdefault("source_ocr", raw_by_pts.get(frame["source_pts_seconds"], []))
        for slot in rival_slots(frame["source_ocr"]):
            frame["players"][slot].update(present=False, role="rival")
    result = aggregate_frames(frames)
    need_chart_context = False
    need_number_context = False
    for player in result["players"]:
        chart = field_consensus([parse_result(f["source_ocr"])[player]["fields"]["chart"] for f in frames])
        need_chart_context |= chart["status"] != "recognized" and any(f["source_ocr"] for f in frames)
        if chart["status"] == "recognized":
            chart["method"] = "full_screen_badge_ocr"
            result["players"][player]["chart"] = chart["value"]
            result["players"][player]["fields"]["chart"] = chart
    for player, resolved in result["players"].items():
        for key in (*COUNT_FIELDS, "score"):
            upright = field_consensus([parse_result(f["source_ocr"])[player]["fields"][key] for f in frames])
            if upright["status"] == "recognized" and resolved["fields"][key]["status"] == "recognized":
                need_number_context |= upright["value"] != resolved[key]
    failures = {o.get("source_pts_seconds"): o for o in observations
                if o.get("window") == "result" and o.get("identity_eligible")
                and is_stage_break(o.get("ocr", []))}
    if not result["players"] and len(failures) >= 2:
        result.update(status="not_displayed", reason="stage_break_screen", needs_review=False,
                      source_frames=[{"file": o["file"], "source_pts_seconds": pts}
                                     for pts, o in sorted(failures.items())])
    if result["needs_review"] or need_chart_context or need_number_context:
        ordered = sorted(frames, key=lambda f: f["source_pts_seconds"])
        # Sample the result's duration, rather than repeating costly OCR on
        # every retained frame. Previously acquired context remains evidence.
        positions = {round(i * (len(ordered) - 1) / 5) for i in range(6)} if ordered else set()
        selected = [f for i, f in enumerate(ordered) if i in positions or f.get("context_version") == 2]
        for frame in selected:
            if frame.get("context_version") != 2:
                frame["context_version"] = 2
                frame["context_ocr"] = contextual_stats(Path(frame["file"]), directory,
                                                        f"{frame['source_pts_seconds']:.3f}", width, height)
        for player in result["players"]:
            for key in FIELDS:
                contextual = field_consensus([parse_result(f["context_ocr"])[player]["fields"][key]
                                              for f in selected])
                if contextual["status"] != "recognized" and result["players"][player]["fields"][key]["status"] != "recognized":
                    contextual = field_consensus([parse_result(f["source_ocr"])[player]["fields"][key]
                                                  for f in frames])
                    contextual["method"] = "full_screen_ocr"
                if contextual["status"] == "recognized":
                    contextual.setdefault("method", "caption_context_ocr")
                    result["players"][player][key] = contextual["value"]
                    result["players"][player]["fields"][key] = contextual
    for player, resolved in result["players"].items():
        if resolved["fields"]["score"]["status"] == "recognized":
            continue
        ordered = sorted(frames, key=lambda f: f["source_pts_seconds"])
        positions = {round(i * (len(ordered) - 1) / 5) for i in range(6)} if ordered else set()
        selected = [f for i, f in enumerate(ordered) if i in positions]
        for frame in selected:
            channel = frame.setdefault("contrast_score_ocr", {})
            if player not in channel:
                channel[player] = contrast_score(Path(frame["file"]), directory,
                                                  f"{frame['source_pts_seconds']:.3f}", width, height, player)
        score = field_consensus([parse_result(f["contrast_score_ocr"][player])[player]["fields"]["score"]
                                 for f in selected])
        if score["status"] == "recognized":
            score["method"] = "caption_contrast_ocr"
            resolved["score"] = score["value"]
            resolved["fields"]["score"] = score
    for player in result["players"].values():
        player["needs_review"] = player["presence"] != "recognized" or any(
            field["status"] != "recognized" for field in player["fields"].values())
    if result["players"]:
        result["needs_review"] = any(p["needs_review"] for p in result["players"].values())
    saved.unlink(missing_ok=True)
    write_json(saved, frames)
    result["evidence"] = str((directory / "frames.json").resolve())
    return result
