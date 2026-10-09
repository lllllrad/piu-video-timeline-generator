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
    """Read account labels only inside Phoenix's top player-name bands."""
    players = {}
    for player, (low, high) in {"p1": (.14, .44), "p2": (.56, .86)}.items():
        candidates = [line for line in lines if low < center(line)[0] < high
                      and .05 < center(line)[1] < .085 and line["confidence"] >= .5
                      and re.search(r"[^\W\d_]", line["text"], re.UNICODE)]
        # Require the account discriminator, rather than mistaking a rank or BGA
        # caption for a name. Unknown/guest accounts stay unknown.
        candidates = [line for line in candidates if re.fullmatch(r".+?\s*#\s*\d{4}", line["text"].strip())]
        if len(candidates) == 1:
            line = candidates[0]
            name = re.sub(r"\s*#\s*(\d{4})$", r" #\1", line["text"].strip())
            players[player] = {"value": name, "confidence": line["confidence"], "raw": line}
    return players


def resolve_players(observations, stage_evidence=None):
    frames = [o for o in unique_frames(observations) if o.get("eligible_screen") and o.get("scene") in {"selection", "result", "summary"}]
    if stage_evidence:
        frames.append(stage_evidence)
    names = [player_names(o.get("ocr", [])) for o in frames]
    players = {}
    for player, side in {"p1": "left", "p2": "right"}.items():
        # Name candidates already require a valid account discriminator and
        # the dedicated name band. Mixed-language Vision assigns many clearly
        # readable Latin account labels 0.5; do not reuse the numeric-field gate.
        evidence = field_consensus([n.get(player) for n in names], min_confidence=.5)
        if evidence.get("recognized_frames", 0):
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
