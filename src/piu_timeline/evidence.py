"""Resolve scene-bound evidence without combining unrelated songs and charts."""
import re
import unicodedata

from .recognition import center, consensus
from .result_stats import field_consensus


def key(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()


def unique_frames(observations):
    seen = set()
    for item in observations:
        identity = item.get("source_pts_seconds", item.get("file"))
        if identity is not None and identity in seen:
            continue
        seen.add(identity)
        yield item


def resolve_labels(observations):
    observations = list(unique_frames(observations))
    labels = {"song": None, "chart": None}
    supports = {"song": None, "chart": None}
    # Explicit stage rows are stronger than screen-relative title guesses.
    # Selection is only a fallback; its chart must belong to the chosen song.
    groups = {phase: [o for o in observations if o.get("scene") == phase and o.get("eligible_screen")]
              for phase in ("summary", "result", "selection")}
    for phase, group in groups.items():
        song, support = consensus(group, "song")
        if song:
            labels["song"] = song
            supports["song"] = {**support, "phase": phase}
            break
    for phase, group in groups.items():
        if labels["song"] is not None:
            group = [o for o in group if o.get("song") and key(o["song"]["text"]) == key(labels["song"])]
        chart, support = consensus(group, "chart")
        if chart:
            labels["chart"] = chart
            supports["chart"] = {**support, "phase": phase}
            break
    return labels, supports


def player_names(lines):
    """Parse account strips, tolerating a damaged discriminator in focused OCR."""
    players = {}
    excluded = {"P1", "P2", "PLAYER", "GUEST", "NOACCOUNT", "CREDIT", "CREDITS", "STAGE", "BASIC", "PREMIUM"}
    for player, (low, high) in {"p1": (.14, .44), "p2": (.56, .86)}.items():
        candidates = []
        for line in lines:
            if not (low < center(line)[0] < high and .05 < center(line)[1] < .085
                    and line["confidence"] >= .5):
                continue
            text = unicodedata.normalize("NFKC", line["text"]).strip()
            match = re.fullmatch(r"(.+?)\s*[#*+]\s*(\d{4})", text)
            # Raw full-screen guesses still need #. Focused strips may read
            # its tiny strokes as +/*; keep the displayed digits as evidence.
            if match and ("#" in text or line.get("name_crop")):
                nickname, suffix = match.groups()
            elif line.get("name_crop") and re.fullmatch(r"[\w .-]{2,24}", text):
                # On an empty player side, BGA credits can occupy the same
                # coordinates. Bare nicknames need the account/rank header
                # immediately above them on that side.
                header = any(low < center(item)[0] < high and .005 < center(item)[1] < .05
                             and re.search(r"\b(BEGINNER|INTERMEDIATE|ADVANCED|EXPERT|MASTER)\b",
                                           item["text"].upper()) for item in lines)
                if not header:
                    continue
                nickname, suffix = text, None
            else:
                continue
            if (not re.search(r"[^\W\d_]", nickname, re.UNICODE)
                    or re.sub(r"\W", "", nickname).upper() in excluded):
                continue
            candidates.append({"value": nickname.strip() + (f" #{suffix}" if suffix else ""),
                               "nickname": nickname.strip(), "discriminator": suffix,
                               "confidence": line["confidence"], "raw": line})
        focused = [item for item in candidates if item["raw"].get("name_crop")]
        if focused:
            # Preserve Hangul when a Korean reading exists; otherwise prefer
            # the Latin reader at equal confidence over mixed-language guesses.
            korean = [item for item in focused if re.search(r"[가-힣]", item["nickname"])]
            pool = korean or focused
            players[player] = max(pool, key=lambda item: (item["confidence"],
                item["discriminator"] is not None, item["raw"].get("language") == "en"))
        elif len(candidates) == 1:
            players[player] = candidates[0]
    return players


def resolve_players(observations, stage_evidence=None):
    frames = [o for o in unique_frames(observations)
              if o.get("identity_eligible", o.get("eligible_screen"))
              and o.get("scene") in {"selection", "result", "summary", "failure", "mode", "gameplay", "unknown"}]
    if stage_evidence:
        frames = list(unique_frames([*frames, stage_evidence]))
    names = [player_names([*o.get("ocr", []), *o.get("name_ocr", [])]) for o in frames]
    players = {}
    for player, side in {"p1": "left", "p2": "right"}.items():
        candidates = [n.get(player) for n in names]
        focused = [item for item in candidates if item and item["raw"].get("name_crop")]
        focused_name = field_consensus(focused, min_confidence=.5)
        focused_nickname = field_consensus([dict(item, value=item["nickname"]) for item in focused], min_confidence=.5)
        # Repeated dedicated-strip OCR takes precedence over full-screen guesses
        # of tiny account digits, just as a numbered row precedes title guesses.
        use_focused = focused_name["status"] == "recognized" or focused_nickname["status"] == "recognized"
        selected = focused if use_focused else candidates
        evidence = field_consensus(selected, min_confidence=.5)
        nickname = field_consensus([dict(item, value=item["nickname"]) if item else None
                                    for item in selected], min_confidence=.5)
        if evidence.get("recognized_frames", 0):
            # A legible repeated nickname is useful even when tiny account
            # digits disagree. Retain full alternatives; do not invent a suffix.
            if evidence["status"] != "recognized" and nickname["status"] == "recognized":
                evidence = {**nickname, "account_alternatives": evidence["alternatives"],
                            "discriminator_status": "unknown"}
            if use_focused:
                evidence["full_screen_alternatives"] = field_consensus(candidates, min_confidence=.5)["alternatives"]
            evidence["source_frames"] = [o.get("file") for o, n in zip(frames, names) if n.get(player)
                                         and (not use_focused or n[player]["raw"].get("name_crop"))]
            players[player] = {"player_id": player, "side": side, "name": evidence["value"],
                               "presence": "recognized" if evidence["status"] == "recognized" else "uncertain",
                               "fields": {"name": evidence}}
    return players


def reconcile_sessions(segments, observations):
    """Attach summary rows only to uniquely numbered stages in the current credit.

    A stage reset or an unknown/non-increasing stage ends the association chain.
    Each summary is already restricted to the gap immediately after its owner.
    """
    for index, owner in enumerate(segments):
        if owner["stage"] is None:
            continue
        session = [index]
        for previous in range(index - 1, -1, -1):
            stage = segments[previous]["stage"]
            if stage is None or stage >= segments[session[-1]]["stage"]:
                break
            session.append(previous)
        summaries = [o for o in observations[index] if o.get("scene") == "summary"]
        for target in session:
            rows = []
            for frame in summaries:
                row = frame.get("rows", {}).get(str(segments[target]["stage"]))
                if row:
                    rows.append({**frame, **row, "eligible_screen": True})
            labels, support = resolve_labels(rows)
            if labels["song"] is None:
                continue
            # A numbered title is independent of a readable chart. Resolve
            # fallback charts from this play's own matching-title evidence,
            # rather than erase a corroborated chart when its summary badge
            # is unreadable. Different simultaneous charts remain unshared.
            split_charts = any(len({chart["text"] for chart in row.get("charts", {}).values()}) > 1 for row in rows)
            if labels["chart"] is None and not split_charts:
                labels, support = resolve_labels([*rows, *observations[target]])
            segment = segments[target]
            old = {name: segment[name] for name in ("song", "chart")}
            if any(old[name] and labels[name] and key(old[name]) != key(labels[name]) for name in old):
                segment.setdefault("label_revisions", []).append({"previous": old, "reason": "explicit_summary_stage_row"})
                segment["needs_review"] = True
            segment.update(labels)
            segment["confidence"] = support
            segment["summary_evidence"] = [o["file"] for o in rows]
            for player, side in (("p1", "left"), ("p2", "right")):
                value, evidence = consensus([{"chart": row.get("charts", {}).get(player)} for row in rows], "chart")
                if value:
                    slot = segment.setdefault("players", {}).setdefault(player, {
                        "player_id": player, "side": side, "name": None, "fields": {}})
                    slot["presence"] = "recognized"
                    slot["fields"]["chart"] = {"status": "recognized", "value": value,
                                                **evidence, "phase": "summary"}
