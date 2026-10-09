"""Bounded acquisition and credit continuity around detected gameplay intervals."""
import re
import subprocess


def transition_samples(record, roi, begin, end, limit=24):
    """Find screen changes cheaply; OCR only representatives after each change.

    Decode two small grayscale frames per second inside a bounded gap, never
    perform OCR on every video frame. Two representatives cover short screens
    and their entrance animations without counting the same source frame twice.
    """
    if end <= begin:
        return []
    x, y, w, h = roi
    result = subprocess.run([
        "ffmpeg", "-v", "info", "-nostdin", "-ss", str(begin), "-noautorotate", "-i", record["path"],
        "-map", f"0:{record['video_streams'][0]['index']}", "-t", str(end - begin),
        "-vf", f"fps=2,crop={w}:{h}:{x}:{y},scale=192:108,format=gray,select='gt(scene,0.22)',showinfo",
        "-an", "-f", "null", "-",
    ], check=True, capture_output=True, text=True)
    changes = [begin + float(value) for value in re.findall(r"\bpts_time:([\d.eE+-]+)", result.stderr)]
    samples = []
    for change in changes:
        for offset in (.25, .85):
            seconds = round(change + offset, 3)
            if seconds < end and all(abs(seconds - previous) >= .3 for previous in samples):
                samples.append(seconds)
        if len(samples) >= limit:
            break
    return samples[:limit]


def credit_groups(segments, observations):
    """Close credits on observed summaries, starts/mode choices or stage resets.

    Missing stage text does not erase continuity. At most six plays can share a
    credit. Conflicting observed accounts stop identity propagation separately.
    """
    groups = []
    for index, segment in enumerate(segments):
        reason = "recording_start"
        boundary = index == 0
        if index:
            previous = segments[index - 1]
            post = [o for o in observations[index - 1] if o.get("window") == "result"]
            pre = [o for o in observations[index] if o.get("window") == "selection"]
            if any(o.get("scene") == "summary" for o in post):
                boundary, reason = True, "play_result"
            elif any(o.get("scene") in {"entry", "mode", "demo", "summary"} for o in pre):
                boundary, reason = True, "new_game_screen"
            elif (previous.get("stage") is not None and segment.get("stage") is not None
                  and segment["stage"] <= previous["stage"]):
                boundary, reason = True, "stage_reset"
            elif len(groups[-1]["indices"]) >= 6:
                boundary, reason = True, "six_play_limit"
            elif not (previous.get("stage") is not None and segment.get("stage") is not None
                      or any(o.get("scene") in {"result", "failure"} for o in post)):
                boundary, reason = True, "unconfirmed_continuity"
        if boundary:
            groups.append({"indices": [], "boundary": reason})
        groups[-1]["indices"].append(index)
    return groups


def reconcile_players(segments, observations):
    from .evidence import resolve_players, key
    for credit_id, group in enumerate(credit_groups(segments, observations), 1):
        indices = group["indices"]
        frames = [o for index in indices for o in observations[index]]
        identities = resolve_players(frames)
        for index in indices:
            segment = segments[index]
            segment["credit"] = {"id": credit_id, "boundary": group["boundary"],
                                 "plays": len(indices), "association": "observed_scene_sequence"}
            for slot, identity in identities.items():
                if slot in segment.get("excluded_slots", {}) or not identity.get("name"):
                    continue
                own = segment.setdefault("players", {}).get(slot)
                # A local conflict is evidence of a possible account change,
                # rather than an invitation to overwrite it with a majority.
                if own and (own.get("name") or own.get("fields", {}).get("name", {}).get("status") == "conflict"):
                    continue
                # Do not propagate over any different recognized account in the
                # credit. Never merge left and right slots.
                known = [segments[i].get("players", {}).get(slot, {}).get("name") for i in indices]
                if any(name and key(name) != key(identity["name"]) for name in known):
                    continue
                segment["players"][slot] = {**identity,
                    "fields": {**(own or {}).get("fields", {}), **identity["fields"]},
                    "identity_association": {"credit_id": credit_id,
                                             "source_segments": [i + 1 for i in indices]}}


def recover_summary_stages(segments, observations):
    """Recover a missing HUD stage by a unique, repeated numbered title row.

    Match displayed titles rather than infer stage from play order: recordings
    can begin mid-credit or omit a very short failed gameplay interval.
    """
    from .evidence import key, resolve_labels, unique_frames
    from .recognition import consensus

    def same_title(first, second):
        if key(first) == key(second):
            return True
        # Use the same bounded OCR-variant matching as title resolution. Row
        # association still requires a unique match and repeated actual rows.
        return consensus([{"song": {"text": first, "confidence": 1}},
                          {"song": {"text": second, "confidence": 1}}], "song")[0] is not None

    for group in credit_groups(segments, observations):
        summaries = list(unique_frames([o for i in group["indices"] for o in observations[i]
                                        if o.get("scene") == "summary" and o.get("eligible_screen")]))
        rows = {}
        for stage in range(1, 7):
            frames = [{**o, **o["rows"][str(stage)]} for o in summaries if str(stage) in o.get("rows", {})]
            labels, support = resolve_labels(frames)
            if labels["song"]:
                rows[stage] = (labels, support, frames)
        for index in group["indices"]:
            segment = segments[index]
            if segment.get("stage") is not None or not segment.get("song"):
                continue
            matches = [(stage, value) for stage, value in rows.items()
                       if same_title(value[0]["song"], segment["song"])]
            same_plays = [i for i in group["indices"] if segments[i].get("song")
                          and same_title(segments[i]["song"], segment["song"])]
            if len(matches) != 1 or len(same_plays) != 1:
                continue
            stage, (labels, support, frames) = matches[0]
            segment["stage"] = stage
            segment["stage_association"] = {"method": "unique_summary_title_row", "stage": stage,
                                             "source_frames": [o["file"] for o in frames],
                                             "confidence": support["song"]}
