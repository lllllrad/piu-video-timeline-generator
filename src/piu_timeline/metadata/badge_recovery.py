"""Bounded chart recovery from retained original-PTS metadata observations."""
from hashlib import sha256
import json
from pathlib import Path
import unicodedata

from piu_timeline.metadata.badges import FORMAT, read_badges
from piu_timeline.vision.ocr import cache_identity
from piu_timeline.metadata.recognition import focused_lines, frame_labels, summary_stage_row, rival_slots
from piu_timeline.metadata.results import field_consensus, parse_result


def title_key(value):
    return ''.join(unicodedata.normalize('NFKC', value or '').casefold().split())


def sample(frames, limit=6):
    unique = {frame['source_pts_seconds']: frame for frame in frames
              if frame.get('source_pts_seconds') is not None}
    ordered = sorted(unique)
    positions = sorted({round(i*(len(ordered)-1)/(limit-1)) for i in range(limit)}) if ordered else []
    return [unique[ordered[i]] for i in positions]


def direct_chart(chart):
    return chart and any(line.get('badge_read') for line in chart.get('evidence', []))


def recovered_field(observations):
    # One vote per original PTS; preprocessing variants are not extra frames.
    unique = {item['source_pts_seconds']: item for item in observations}
    field = field_consensus(list(unique.values()))
    field.update(method='segmented_chart_badge', source_frames=[
        {'file': item['file'], 'source_pts_seconds': pts}
        for pts, item in sorted(unique.items()) if item['value'] == field['value']])
    return field


def refresh(document, directory):
    """Recover missing badge fields without decoding video or touching count OCR.

    Summary labels belong to matching titles and observed player slots. A basic
    mode label remains intact; its canonical identity requires a separate,
    independently corroborated Single/Double summary badge.
    """
    directory = Path(directory)
    sidecar = directory / 'evidence/chart-badge-recovery.json'
    stored = json.loads(sidecar.read_text()) if sidecar.is_file() else {}
    contract = {'badge': FORMAT, 'ocr': cache_identity(), 'recovery_schema': 1}
    cache = stored.get('observations', {}) if stored.get('contract') == contract else {}
    original_cache = json.dumps(cache, sort_keys=True)
    records, changed = {}, False

    def load(path):
        path = Path(path)
        if path not in records:
            records[path] = json.loads(path.read_text()) if path.is_file() else []
        return records[path]

    def read(frame, phase):
        path = Path(frame['file'])
        if not path.is_file():
            return None
        stat = path.stat()
        glyphs = frame.get('focused_ocr') or frame.get('ocr', [])
        dependency = sha256(json.dumps([str(path), sha256(path.read_bytes()).hexdigest(), stat.st_size, stat.st_mtime_ns,
                                       phase, glyphs], sort_keys=True).encode()).hexdigest()
        if dependency not in cache:
            # Focused Korean titles take precedence over Latin scene-routing
            # hypotheses. Acquire that bounded channel if it was never read.
            if phase == 'summary' and not frame.get('focused_ocr'):
                roi = frame.get('roi', [0, 0, 1300, 730])
                glyphs = focused_lines(path, phase, roi[2], roi[3])
            badges = read_badges(path, phase, glyphs)
            glyphs = [line for line in glyphs if not line.get('badge_read')] + badges
            if phase == 'summary':
                rows = [row for stage in range(1, 7) if (row := summary_stage_row(glyphs, stage))]
                value = {'rows': rows, 'blocked': sorted(rival_slots(frame.get('ocr', [])))}
            else:
                value = {'labels': frame_labels(glyphs, phase), 'players': parse_result(glyphs)}
            cache[dependency] = value
        return cache[dependency]

    for segment in document.get('segments', []):
        raw = segment.get('chart')
        result = segment.get('results', {})
        result_players = result.get('players', {})
        unresolved_result = any(p.get('fields', {}).get('chart', {}).get('status') != 'recognized'
                                for p in result_players.values())
        if raw and not unresolved_result and (not raw.startswith('VERY HARD ') or segment.get('chart_identity')):
            continue
        if not segment.get('song'):
            continue
        own = load(segment['ocr_evidence']) if segment.get('ocr_evidence') else []
        candidates = [f for f in own if f.get('phase') == 'result' and f.get('identity_eligible')]
        summary_paths = set(segment.get('summary_evidence', []))
        summary = []
        for parent in {Path(p).parent for p in summary_paths}:
            summary.extend(f for f in load(parent / 'ocr.json') if f['file'] in summary_paths)
        votes, player_votes, canonical_votes = [], {}, []
        for frame in sample(candidates):
            observed = read(frame, 'result')
            if not observed:
                continue
            labels = observed['labels']
            if title_key((labels.get('song') or {}).get('text')) != title_key(segment['song']):
                continue
            chart = labels.get('chart')
            evidence = {'file': frame['file'], 'source_pts_seconds': frame['source_pts_seconds']}
            if direct_chart(chart):
                votes.append({**evidence, 'value': chart['text'], 'confidence': chart['confidence']})
            for slot, player in observed['players'].items():
                field = player['fields']['chart']
                if player['present'] and field and direct_chart(field['raw']):
                    player_votes.setdefault(slot, []).append({**field, **evidence})
        for frame in sample(summary):
            observed = read(frame, 'summary')
            if not observed:
                continue
            rows = [row for row in observed['rows'] if title_key(row['song']['text']) == title_key(segment['song'])]
            if len(rows) != 1:
                continue
            # Do not borrow a rival's badge or silently pick one of two players.
            allowed = set(segment.get('players', {})) - set(observed['blocked']) - set(segment.get('excluded_slots', {}))
            charts = {slot: chart for slot, chart in rows[0]['charts'].items()
                      if slot in allowed and direct_chart(chart)}
            evidence = {'file': frame['file'], 'source_pts_seconds': frame['source_pts_seconds']}
            for slot, chart in charts.items():
                player_votes.setdefault(slot, []).append({**evidence, 'value': chart['text'], 'confidence': chart['confidence']})
            if len({chart['text'] for chart in charts.values()}) == 1:
                chart = max(charts.values(), key=lambda chart: chart['confidence'])
                vote = {**evidence, 'value': chart['text'], 'confidence': chart['confidence']}
                canonical_votes.append(vote)
                if not raw or not raw.startswith('VERY HARD '):
                    votes.append(vote)
        field = recovered_field(votes)
        if not raw and field['status'] == 'recognized':
            segment['chart'] = field['value']
            segment.setdefault('confidence', {})['chart'] = field
            segment.setdefault('label_revisions', []).append({'previous': None, 'reason': 'segmented_chart_badge', 'evidence': field})
            segment['needs_review'] = not segment.get('song') or result.get('needs_review', False)
            changed = True
        canonical = recovered_field(canonical_votes)
        if raw and raw.startswith('VERY HARD ') and canonical['status'] == 'recognized':
            if canonical['value'] == 'S'+raw.removeprefix('VERY HARD '):
                identity = {**canonical, 'chart': canonical['value'], 'display_chart': raw,
                            'method': 'matching_title_summary_badge'}
                if segment.get('chart_identity') != identity:
                    segment['chart_identity'] = identity
                    changed = True
        for slot, observations in player_votes.items():
            field = recovered_field(observations)
            if field['status'] != 'recognized':
                continue
            # Canonical summary labels must not replace basic-mode display text.
            if raw and raw.startswith('VERY HARD '):
                continue
            targets = [segment.get('players', {}).get(slot), result_players.get(slot)]
            for target in targets:
                if target is None or target.get('fields', {}).get('chart', {}).get('status') == 'recognized':
                    continue
                target.setdefault('fields', {})['chart'] = field
                if target is result_players.get(slot):
                    target['chart'] = field['value']
                    target['needs_review'] = target.get('presence') != 'recognized' or any(
                        f['status'] != 'recognized' for f in target['fields'].values())
                changed = True
        if result_players:
            result['needs_review'] = any(p['needs_review'] for p in result_players.values())
    if original_cache != json.dumps(cache, sort_keys=True):
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        temporary = sidecar.with_suffix('.build.json')
        temporary.write_text(json.dumps({'contract': contract, 'observations': cache}, ensure_ascii=False, indent=2)+'\n')
        temporary.replace(sidecar)
    return changed
