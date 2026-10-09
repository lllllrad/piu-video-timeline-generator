"""Local game-screen OCR with positional evidence and multi-frame agreement."""
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
import re
import subprocess
import unicodedata

from .ocr import ocr_binary, ocr_images


def capture_game(record, output, seconds, roi):
    x, y, width, height = roi
    result = subprocess.run([
        "ffmpeg", "-v", "info", "-nostdin", "-n", "-ss", str(seconds), "-copyts", "-noautorotate",
        "-i", record["path"], "-map", f"0:{record['video_streams'][0]['index']}",
        "-frames:v", "1", "-vf", f"showinfo,crop={width}:{height}:{x}:{y}",
        "-fps_mode", "passthrough", str(output),
    ], capture_output=True, text=True, check=True)
    match = re.search(r"\bn:\s*0\s+pts:\s*-?\d+\s+pts_time:([\d.eE+-]+)", result.stderr)
    if match is None or not output.is_file():
        raise ValueError(f"No frame at {seconds}")
    pts = float(match.group(1))
    return {"file": str(output), "requested_seconds": seconds, "source_pts_seconds": pts,
            "playback_seconds": pts - record["container_start_seconds"], "roi": list(roi)}


def center(line):
    x, y, width, height = line["box"]
    return x + width / 2, y + height / 2


def chart_mode(text):
    word = re.sub(r"[^A-Z]", "", text.upper())
    # Basic-mode badges do not explicitly say SINGLE; preserve the displayed label.
    modes = {"DOUBLE": "D", "HDOUBLE": "HD", "SINGLE": "S", "COOP": "COOP", "VERYHARD": "VERY HARD "}
    if word in modes:
        return modes[word]
    # Restrict correction to one substituted glyph in a full mode word.
    matches = [value for name, value in modes.items() if len(name) == len(word)
               and sum(a != b for a, b in zip(name, word)) == 1]
    return matches[0] if len(matches) == 1 else None


def stage_number(lines):
    """Read STAGE 01..06 from the in-game HUD without inferring play order."""
    values = []
    for label in lines:
        if re.sub(r"[^A-Z]", "", label["text"].upper()) not in {"STAGE", "ISTAGE"}:
            continue
        lx, ly = center(label)
        numbers = [line for line in lines if re.fullmatch(r"0?[1-6]", line["text"].strip().translate(str.maketrans({"O": "0", "О": "0", "Ч": "4"})))
                   and abs(center(line)[0] - lx) < .04
                   and 0 < center(line)[1] - ly < .08]
        if len(numbers) == 1:
            values.append((int(numbers[0]["text"].translate(str.maketrans({"O": "0", "О": "0", "Ч": "4"}))), label, numbers[0]))
    unique = {value for value, _, _ in values}
    if len(unique) != 1:
        return None
    value, label, number = max(values, key=lambda item: min(item[1]["confidence"], item[2]["confidence"]))
    return {"value": value, "confidence": min(label["confidence"], number["confidence"]),
            "evidence": [label, number]}


def frame_labels(lines, phase):
    """Read Phoenix title and selected chart regions, never scores or chat."""
    band = (.13, .23) if phase == "result" else (.48, .54)
    titles = [line for line in lines if .25 < center(line)[0] < .75
              and band[0] < center(line)[1] < band[1]
              and line["confidence"] >= .3 and not re.fullmatch(r"[\d\W]+", line["text"])
              and "BPM" not in line["text"].upper()
              and not any(word in line["text"].upper() for word in ("PRESS", "CENTER", "STEP"))]
    title = min(titles, key=lambda line: abs(center(line)[0] - .5), default=None)
    chart = None
    charts = []
    for line in lines:
        mode = chart_mode(line["text"])
        if mode is None:
            continue
        cx, cy = center(line)
        if not (.15 < cx < .85 and ((.24 < cy < .4) if phase == "result" else (.65 < cy < .9))):
            continue
        numbers = [candidate for candidate in lines if re.fullmatch(r"\d{1,2}", candidate["text"])
                   and 1 <= int(candidate["text"]) <= 99 and candidate["confidence"] >= .5
                   and abs(center(candidate)[0] - cx) < .045
                   and 0 < center(candidate)[1] - cy < .085]
        if numbers:
            number = min(numbers, key=lambda candidate: center(candidate)[1] - cy)
            charts.append({"text": f"{mode}{int(number['text'])}",
                     "confidence": min(line["confidence"], number["confidence"]),
                     "evidence": [line, number]})
    if len({item["text"] for item in charts}) == 1:
        chart = max(charts, key=lambda item: item["confidence"])
    if chart is None and phase == "selection":
        # Single available-chart selection (no expanded DOUBLE/SINGLE badge).
        compact = [line for line in lines if line["text"].strip().upper() in {"D", "S"}
                   and .05 < center(line)[0] < .3 and center(line)[1] > .82]
        for mode_line in compact:
            cx, cy = center(mode_line)
            digits = [line for line in lines if re.fullmatch(r"\d{1,2}", line["text"])
                      and line["confidence"] >= .5 and abs(center(line)[0] - cx) < .04
                      and 0 < center(line)[1] - cy < .08 and 1 <= int(line["text"]) <= 99]
            if len(digits) == 1:
                chart = {"text": mode_line["text"].upper() + str(int(digits[0]["text"])),
                         "confidence": min(mode_line["confidence"], digits[0]["confidence"]),
                         "evidence": [mode_line, digits[0]]}
                break
    return {"song": title, "chart": chart}


def is_result_screen(lines):
    words = {re.sub(r"[^A-Z]", "", line["text"].upper()) for line in lines}
    # Judgment captions are stylized and often read as PERFEST / MAX COMBD.
    # Require their panel geometry or several aligned numeric rows as well as
    # the SCORE caption; selection MY BEST scores must not qualify.
    captions = sum(any(abs(center(line)[1] - y) < .025 and .43 < center(line)[0] < .57
                       and re.sub(r"[^A-Z]", "", line["text"].upper()).startswith(prefix)
                       for line in lines)
                   for y, prefix in ((.434, "PERFE"), (.540, "GOOD"), (.593, "BAD"), (.699, "MAXCOMB")))
    numeric_rows = max(sum(any(abs(center(line)[0] - x) < .04 and abs(center(line)[1] - y) < .02
                              and re.fullmatch(r"\d{3,6}", line["text"].strip()) for line in lines)
                           for y in (.434, .487, .540, .593, .646, .699)) for x in (.335, .665))
    return not is_summary_screen(lines) and "SCORE" in words and (
        bool(words & {"PERFECT", "MAXCOMBO", "KCAL"}) or captions >= 2 or numeric_rows >= 3)


def is_summary_screen(lines):
    words = {re.sub(r"[^A-Z]", "", line["text"].upper()) for line in lines}
    ordinals = {ordinal_number(line["text"]) for line in lines if .35 < center(line)[0] < .65}
    return "PLAYRESULT" in words or {"PLAY", "RESULT"} <= words or len(ordinals - {None}) >= 2


def ordinal_number(text):
    token = re.sub(r"[^A-Z0-9]", "", text.upper())
    return {"1ST": 1, "15T": 1, "2ND": 2, "3RD": 3, "4TH": 4, "5TH": 5, "6TH": 6}.get(token)


def is_demo_screen(lines):
    return any(re.sub(r"[^A-Z]", "", line["text"].upper()) == "DEMOPLAY"
               and center(line)[1] > .85 for line in lines)


def is_stage_break(lines):
    """Phoenix's taunt screen replaces per-song statistics after a life loss."""
    from difflib import SequenceMatcher
    words = [re.sub(r"[^A-Z]", "", line["text"].upper())
             for line in lines if .08 < center(line)[1] < .85]
    if not any(word == "HEY" for word in words):
        return False
    for phrases in (("WHYDONTYOU", "JUSTGETUPAND", "DANCEMAN"), ("ISTHIS", "REALLY", "YOURBEST")):
        if sum(any(SequenceMatcher(None, word, phrase).ratio() >= .65 for word in words)
               for phrase in phrases) >= 2:
            return True
    return False


def scene_kind(lines):
    """Summary takes precedence: never parse its first row as a per-song title."""
    if is_demo_screen(lines):
        return "demo"
    if is_summary_screen(lines):
        return "summary"
    if is_result_screen(lines):
        return "result"
    words = {re.sub(r"[^A-Z]", "", line["text"].upper()) for line in lines}
    if words & {"BASIC", "BASICMODE"} and words & {"PREMIUM", "PREMIUMMODE"}:
        return "mode"
    if is_stage_break(lines):
        return "failure"
    if words & {"GAMEOVER", "STAGEBREAK", "STAGEFAILED"} or "STAGE" in words and words & {"BREAK", "FAILED"}:
        return "failure"
    if any("INSERTCOIN" in word or "PRESSCENTERSTEP" in word or "PRESSTHECENTERSTEP" in word for word in words):
        return "entry"
    if stage_number(lines):
        return "gameplay"
    words = {re.sub(r"[^A-Z]", "", line["text"].upper()) for line in lines}
    if "MYBEST" in words or frame_labels(lines, "selection")["chart"]:
        return "selection"
    return "unknown"


def focused_names(frame, game_width, game_height):
    """Read the dedicated account strips independently of title/score OCR."""
    paths, regions = [], []
    for slot, x in (("p1", .14), ("p2", .56)):
        px, py, pw, ph = int(x * game_width), int(.045 * game_height), int(.30 * game_width), int(.05 * game_height)
        path = Path(frame).with_name(Path(frame).stem + f"-name-v1-{slot}.png")
        if not path.is_file():
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(frame),
                            "-vf", f"crop={pw}:{ph}:{px}:{py},scale=iw*4:ih*4", str(path)],
                           check=True, capture_output=True)
        paths.append(path)
        regions.append((px / game_width, py / game_height, pw / game_width, ph / game_height))
    mapped = []
    # Read both languages in a small dedicated strip. Latin OCR is much more
    # reliable here; Korean OCR preserves Hangul account names.
    for english in (True, False):
        for result, (x, y, w, h) in zip(ocr_images(paths, english=english), regions):
            for line in result["lines"]:
                bx, by, bw, bh = line["box"]
                mapped.append({**line, "box": [x + bx * w, y + by * h, bw * w, bh * h],
                               "image": result["path"], "name_crop": True,
                               "language": "en" if english else "ko-en"})
    return mapped


def focused_lines(frame, phase, game_width, game_height):
    """Upscale title and chart regions before OCR; map boxes back to game coordinates."""
    boxes = ([(.2, .15, .6, .07), (.59, .25, .15, .14), (.26, .25, .15, .14)] if phase == "result"
             else [(.2, .485, .6, .052), (.15, .63, .7, .3), (.07, .82, .15, .17)])
    if phase == "summary":
        boxes = [(.20, .14, .60, .8), (.70, .14, .09, .8), (.21, .14, .09, .8), (.46, .15, .08, .80)]
    paths, regions = [], []
    for index, (x, y, w, h) in enumerate(boxes):
        pixels = (int(x * game_width), int(y * game_height), int(w * game_width), int(h * game_height))
        px, py, pw, ph = pixels
        path = Path(frame).with_name(Path(frame).stem + f"-{phase}-v5-focus-{index}.png")
        processing = f"crop={pw}:{ph}:{px}:{py},scale=iw*3:ih*3"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(frame),
                        "-vf", processing, str(path)], check=True, capture_output=True)
        paths.append(path)
        regions.append((px / game_width, py / game_height, pw / game_width, ph / game_height))
    recognized = ocr_images(paths[:1]) + ocr_images(paths[1:], english=True)
    mapped = []
    for region_index, (result, (x, y, w, h)) in enumerate(zip(recognized, regions)):
        for line in result["lines"]:
            if phase == "summary" and region_index == 3 and ordinal_number(line["text"]) is None:
                continue
            bx, by, bw, bh = line["box"]
            if phase == "summary" and region_index == 0 and not .30 < x + (bx + bw / 2) * w < .70:
                continue
            mapped.append({**line, "box": [x + bx * w, y + by * h, bw * w, bh * h], "image": result["path"]})
    if phase == "result":
        title = frame_labels(mapped, "result")["song"]
        # Centered original text preserves thin glyphs and symbols. Only invoke
        # white-text isolation when OCR has merged off-center BGA credits or failed.
        if title is None or abs(center(title)[0] - .5) > .035:
            path = paths[0].with_name(paths[0].stem + "-white.png")
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(paths[0]),
                            "-vf", r"format=gray,lut=y=if(gt(val\,180)\,255\,0)", str(path)],
                           check=True, capture_output=True)
            result = ocr_images([path])[0]
            x, y, w, h = regions[0]
            filtered = [{**line, "box": [x + line["box"][0] * w, y + line["box"][1] * h,
                                         line["box"][2] * w, line["box"][3] * h], "image": str(path)}
                        for line in result["lines"]]
            isolated = frame_labels(filtered, "result")["song"]
            if isolated and abs(center(isolated)[0] - .5) <= .035:
                mapped = [line for line in mapped if line["image"] != str(paths[0])] + filtered
        title = frame_labels(mapped, "result")["song"]
        if title and title["text"].isascii() and re.search(r"[A-Za-z]", title["text"]):
            # Use the Latin recognizer for wholly Latin titles, not Korean glyph
            # hypotheses. This is language routing, never a song-name dictionary.
            result = ocr_images([title["image"]], english=True)[0]
            x, y, w, h = regions[0]
            latin = [{**line, "box": [x + line["box"][0] * w, y + line["box"][1] * h,
                                      line["box"][2] * w, line["box"][3] * h],
                      "image": title["image"], "recognition_language": "en-US"}
                     for line in result["lines"]]
            alternative = frame_labels(latin, "result")["song"]
            if (alternative and abs(center(alternative)[0] - .5) <= .035
                    and alternative["confidence"] >= title["confidence"]):
                mapped = [line for line in mapped if line["image"] != title["image"]] + latin
    return mapped


def summary_stage_row(lines, stage):
    """Read a numbered title independently of either player's chart badge."""
    ordinals = [line for line in lines if stage is not None and ordinal_number(line["text"]) == stage]
    titles, matches = [], []
    for ordinal in ordinals:
        ox, oy = center(ordinal)
        candidates = [line for line in lines if .25 < center(line)[0] < .7
                      and abs(center(line)[0] - ox) < .15 and .015 < center(line)[1] - oy < .08
                      and not re.fullmatch(r"[\d\W]+", line["text"])]
        for title in candidates:
            titles.append({"text": title["text"], "confidence": min(title["confidence"], ordinal["confidence"]),
                           "evidence": [ordinal, title]})
            title_y = center(title)[1]
            for mode_line in lines:
                mode = chart_mode(mode_line["text"])
                cx, cy = center(mode_line)
                if not mode or not ((.15 < cx < .31 or .69 < cx < .87) and -.09 < cy - title_y < -.025):
                    continue
                digits = [item for item in lines if re.fullmatch(r"\d{1,2}", item["text"])
                          and 1 <= int(item["text"]) <= 99 and item["confidence"] >= .5
                          and abs(center(item)[0] - cx) < .04 and 0 < center(item)[1] - cy < .075]
                # Raw/focused readings from one source frame may duplicate a
                # glyph. Agreement is one observation; competing digits abstain.
                if len({int(item["text"]) for item in digits}) == 1:
                    number = max(digits, key=lambda item: item["confidence"])
                    evidence = [ordinal, title, mode_line, number]
                    matches.append({"player_id": "p1" if cx < .5 else "p2",
                                    "chart": {"text": mode + str(int(number["text"])),
                                              "confidence": min(item["confidence"] for item in evidence),
                                              "evidence": evidence}})
    if len({re.sub(r"\s+", "", item["text"]).casefold() for item in titles}) != 1:
        return None
    charts = {}
    for player in ("p1", "p2"):
        entries = [item["chart"] for item in matches if item["player_id"] == player]
        if len({entry["text"] for entry in entries}) == 1:
            charts[player] = max(entries, key=lambda item: item["confidence"])
    shared = list(charts.values())
    chart = shared[0] if len({entry["text"] for entry in shared}) == 1 else None
    return {"song": max(titles, key=lambda item: item["confidence"]), "chart": chart, "charts": charts}


def consensus(observations, field):
    candidates = [item[field] for item in observations if item.get(field)]
    # Spacing is unstable in small Korean UI labels; keep the most common display form below.
    keys = [re.sub(r"\s+", "", unicodedata.normalize("NFKC", item["text"])).casefold() for item in candidates]
    counts = Counter(keys)
    if not counts:
        return None, None
    ordered = counts.most_common()
    # Titles can differ by one OCR glyph between otherwise agreeing frames.
    # Cluster only long, highly similar song strings. Charts remain exact, and
    # equally supported clusters still abstain rather than guessing a title.
    if field == "song" and ordered[0][1] < 2:
        unique = list(counts)
        groups = []
        for key in unique:
            matches = [group for group in groups if any(
                min(len(key), len(other)) >= 4
                and SequenceMatcher(None, key, other).ratio() >= .82 for other in group)]
            if len(matches) == 1:
                matches[0].add(key)
            elif not matches:
                groups.append({key})
        grouped = sorted(((sum(counts[key] for key in group), group) for group in groups), reverse=True,
                         key=lambda item: item[0])
        if grouped and grouped[0][0] >= 2 and (len(grouped) == 1 or grouped[0][0] > grouped[1][0]):
            votes, group = grouped[0]
            selected = [item for item, key in zip(candidates, keys) if key in group]
            display = max(selected, key=lambda item: item["confidence"])["text"].strip()
            return display, {"supporting_frames": votes, "recognized_frames": len(candidates),
                             "mean_ocr_confidence": sum(item["confidence"] for item in selected) / votes,
                             "alternatives": dict(counts), "agreement": "similar_title_ocr"}
    best, votes = ordered[0]
    if votes < 2 or (len(ordered) > 1 and ordered[1][1] == votes):
        return None, None
    selected = [item for item, key in zip(candidates, keys) if key == best]
    display = Counter(item["text"].strip() for item in selected).most_common(1)[0][0]
    return display, {"supporting_frames": votes, "recognized_frames": len(candidates),
                  "mean_ocr_confidence": sum(item["confidence"] for item in selected) / votes,
                  "alternatives": dict(counts)}
