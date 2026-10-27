"""Attach observed word refreshes after independent counter-row recovery."""
from collections import defaultdict

from piu_timeline.play.judgments import synchronized_refreshes


def attach_recovered_labels(data):
    """Recover labels only; never move a row or narrow its input bracket."""
    matches = [dict(match) for match in data['matches']]
    words = [dict(event) for event in data.get('judgment_events', [])]
    counters = [dict(event) for event in data.get('combo_events', [])]
    if not words or not counters:
        return {**data, 'matches': matches, 'judgment_events': words}
    groups, owners = defaultdict(list), defaultdict(list)
    for match in matches:
        if match.get('combo_event') is not None:
            groups[match['combo_event']].append(match)
        if match.get('judgment_event') is not None:
            owners[match['judgment_event']].append(match)
    eligible = set()
    for ci, group in groups.items():
        counter = counters[ci]
        if (counter.get('delta') != 1 or not any(m.get('recovery_method') for m in group)
                or not any(not m.get('judgment_label') for m in group)
                or max(m['target_seconds'] for m in group)-min(m['target_seconds'] for m in group) >= .025
                or any(m.get('aggregate_row_count', 1) != 1 for m in group)
                or counter.get('detection_status') == 'excluded'):
            continue
        if counter['status'] != 'matched' and counter.get('reason') not in (
                'possible_hold_or_dense_stack', 'ambiguous_note_or_combo_association',
                'ongoing_hold_tick_not_new_press'):
            continue
        counter['status'] = 'matched'
        eligible.add(ci)
    # Association exclusions do not erase measured refreshes. Include all valid
    # native refreshes as competitors, even when their row is still unresolved.
    candidates = [{**event, 'status': event.get('detection_status', 'candidate')
                   if event.get('label') in ('PERFECT', 'GREAT', 'GOOD', 'BAD') else 'excluded'}
                  for event in words]
    for ji, ci in synchronized_refreshes({'combo_events': counters}, candidates):
        if ci not in eligible:
            continue
        group, word = groups[ci], words[ji]
        if (any(m.get('combo_event') != ci for m in owners[ji])
                or word.get('anchor_combo_event') not in (None, ci)
                or any(m.get('judgment_event') not in (None, ji)
                       or m.get('judgment_label') not in (None, word['label']) for m in group)):
            continue
        word.update(status='corroborating', reason=None, anchor_combo_event=ci)
        for match in group:
            if match.get('judgment_label'):
                continue
            source = match.get('evidence_source', 'combo')
            match.update(judgment_label=word['label'], judgment_event=ji,
                         judgment_label_source='recovered_synchronized_refresh',
                         evidence_source=source if 'judgment' in source.split('+') else source+'+judgment')
    return {**data, 'matches': matches, 'judgment_events': words}
