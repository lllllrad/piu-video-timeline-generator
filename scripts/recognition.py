"""Local game-screen OCR with positional evidence and multi-frame agreement."""
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]


def ocr_binary():
    if sys.platform != "darwin" or not shutil.which("swiftc"):
        raise ValueError("Automatic OCR currently requires macOS Vision and swiftc (Xcode Command Line Tools)")
    source = ROOT / "scripts/ocr.swift"
    binary = ROOT / ".local/bin/piu-ocr"
    cache = ROOT / ".local/cache/swift"
    cache.mkdir(parents=True, exist_ok=True)
    binary.parent.mkdir(parents=True, exist_ok=True)
    if not binary.exists() or binary.stat().st_mtime_ns < source.stat().st_mtime_ns:
        subprocess.run(["swiftc", "-module-cache-path", str(cache), str(source), "-o", str(binary)], check=True)
    return binary


def ocr_images(paths, english=False):
    result = subprocess.run([str(ocr_binary()), *(["--english"] if english else []), *map(str, paths)], capture_output=True, text=True)
    if result.returncode:
        raise ValueError("Local Vision OCR failed. On restricted hosts, allow local OCR execution; "
                         "no images are uploaded. " + result.stderr.strip())
    return json.loads(result.stdout)


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
    modes = {"DOUBLE": "D", "SINGLE": "S", "COOP": "COOP", "VERYHARD": "VERY HARD "}
    if word in modes:
        return modes[word]
    # Restrict correction to one substituted glyph in a full mode word.
    matches = [value for name, value in modes.items() if len(name) == len(word)
               and sum(a != b for a, b in zip(name, word)) == 1]
    return matches[0] if len(matches) == 1 else None


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
    return "SCORE" in words and bool(words & {"PERFECT", "MAXCOMBO", "KCAL"})


def focused_lines(frame, phase, game_width, game_height):
    """Upscale title and chart regions before OCR; map boxes back to game coordinates."""
    boxes = ([(.2, .15, .6, .07), (.59, .25, .15, .14), (.26, .25, .15, .14)] if phase == "result"
             else [(.2, .485, .6, .052), (.15, .63, .7, .3), (.07, .82, .15, .17)])
    if phase == "summary":
        boxes = [(.25, .14, .45, .8), (.70, .14, .09, .8)]
    paths, regions = [], []
    for index, (x, y, w, h) in enumerate(boxes):
        pixels = (int(x * game_width), int(y * game_height), int(w * game_width), int(h * game_height))
        px, py, pw, ph = pixels
        path = Path(frame).with_name(Path(frame).stem + f"-focus-{index}.png")
        processing = f"crop={pw}:{ph}:{px}:{py},scale=iw*3:ih*3"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(frame),
                        "-vf", processing, str(path)], check=True, capture_output=True)
        paths.append(path)
        regions.append((px / game_width, py / game_height, pw / game_width, ph / game_height))
    recognized = ocr_images(paths[:1]) + ocr_images(paths[1:], english=True)
    mapped = []
    for result, (x, y, w, h) in zip(recognized, regions):
        for line in result["lines"]:
            bx, by, bw, bh = line["box"]
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


def summary_chart(lines, song):
    key = lambda text: re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()
    titles = [line for line in lines if key(line["text"]) == key(song)]
    if len(titles) != 1:
        return None
    title_y = center(titles[0])[1]
    for line in lines:
        mode = chart_mode(line["text"])
        cx, cy = center(line)
        if mode and .69 < cx < .8 and -.09 < cy - title_y < .02:
            digits = [item for item in lines if re.fullmatch(r"\d{1,2}", item["text"])
                      and 1 <= int(item["text"]) <= 99 and item["confidence"] >= .5
                      and abs(center(item)[0] - cx) < .04 and 0 < center(item)[1] - cy < .075]
            if len(digits) == 1:
                return {"text": mode + str(int(digits[0]["text"])),
                        "confidence": min(line["confidence"], digits[0]["confidence"]),
                        "evidence": [titles[0], line, digits[0]]}
    return None


def consensus(observations, field):
    candidates = [item[field] for item in observations if item.get(field)]
    # Spacing is unstable in small Korean UI labels; keep the most common display form below.
    keys = [re.sub(r"\s+", "", unicodedata.normalize("NFKC", item["text"])).casefold() for item in candidates]
    counts = Counter(keys)
    if not counts:
        return None, None
    ordered = counts.most_common()
    best, votes = ordered[0]
    if votes < 2 or (len(ordered) > 1 and ordered[1][1] == votes):
        return None, None
    selected = [item for item, key in zip(candidates, keys) if key == best]
    display = Counter(item["text"].strip() for item in selected).most_common(1)[0][0]
    return display, {"supporting_frames": votes, "recognized_frames": len(candidates),
                  "mean_ocr_confidence": sum(item["confidence"] for item in selected) / votes,
                  "alternatives": dict(counts)}
