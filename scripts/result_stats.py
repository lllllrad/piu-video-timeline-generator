"""Player-separated result OCR; never infer missing judgment counts as zero."""
from collections import Counter
from pathlib import Path
import re
import subprocess

from recognition import center, frame_labels, is_result_screen, ocr_images
from timeline import write_json

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
        players[player] = {"side": side, "present": present, "fields": values}
    return players


def focused_stats(frame, directory, index, width, height):
    # Separate numeric columns from central labels and side background art.
    boxes = [("p1-counts", .30, .408, .09, .315), ("p2-counts", .61, .408, .09, .315),
             ("p1-score", .075, .33, .22, .115), ("p2-score", .70, .33, .23, .115),
             ("p1-chart", .26, .25, .15, .14), ("p2-chart", .59, .25, .15, .14)]
    paths, regions = [], []
    for name, x, y, w, h in boxes:
        px, py, pw, ph = int(x * width), int(y * height), int(w * width), int(h * height)
        path = directory / f"frame-{index:03}-{name}.png"
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


def field_consensus(observations):
    values = [item for item in observations if item is not None]
    counts = Counter(item["value"] for item in values)
    if not counts:
        return {"value": None, "status": "unknown", "supporting_frames": 0, "alternatives": {}}
    winner, votes = counts.most_common(1)[0]
    accepted = votes >= 2 and votes > len(values) / 2
    selected = [item for item in values if item["value"] == winner]
    confidence = sum(item["confidence"] for item in selected) / votes
    return {"value": winner if accepted and confidence >= .7 else None,
            "status": "recognized" if accepted and confidence >= .7 else "conflict" if len(counts) > 1 else "unknown",
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
    directory.mkdir(parents=True, exist_ok=False)
    frames = []
    seen = set()
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
        lines = focused_stats(frame, directory, index, width, height)
        # Keep only SCORE markers from raw OCR; numeric extraction uses dedicated
        # crops so mixed-language/BGA OCR cannot outvote focused numeric evidence.
        lines += [line for line in raw if re.sub(r"[^A-Z]", "", line["text"].upper()) == "SCORE"]
        frames.append({"file": str(frame), "source_pts_seconds": pts,
                       "playback_seconds": observation.get("playback_seconds"),
                       "ocr": lines, "players": parse_result(lines)})
    result = aggregate_frames(frames)
    write_json(directory / "frames.json", frames)
    result["evidence"] = str((directory / "frames.json").resolve())
    return result
