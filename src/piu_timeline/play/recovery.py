"""Conservative recovery of unique rows with independent lane onset evidence."""
from collections import defaultdict

from piu_timeline.play.candidates import candidates
from piu_timeline.play.receptors import onset_overlaps
from piu_timeline.play.channels import receptor_evidence
from piu_timeline.play.processing import processing_support


def recover_rows(data):
    matches = list(data.get('matches', []))
    notes = data.get('notes', [])
    # Legacy/synthetic records without fitted times cannot participate.
    if any('target_seconds' not in match for match in matches) or any(
            'prediction_uncertainty_seconds' not in note for note in notes if note['status'] == 'estimated'):
        return matches, []
    guard = 2*(data.get('median_frame_interval_seconds') or .017)
    runs = receptor_evidence(data)
    events = []
    for source, key in (('combo', 'combo_events'), ('judgment', 'judgment_events')):
        for index, event in enumerate(data.get(key, [])):
            lo, hi = event['lower_seconds'], event['upper_seconds']
            if not 0 <= hi-lo <= .12 or event.get('delta', 1) != 1:
                continue
            if source == 'judgment' and event.get('label') not in ('PERFECT', 'GREAT', 'GOOD', 'BAD'):
                continue
            if event.get('detection_status') == 'excluded':
                continue
            events.append({'source': source, 'event': index, 'delta': 1, 'lower_seconds': lo,
                           'upper_seconds': hi, 'reason': event.get('reason')})
    choices, _ = candidates(data, events)
    assigned = {match['note'] for match in matches}
    missed = {candidate['note'] for candidate in data.get('miss_candidates', [])}
    eligible = [(ni, note) for ni, note in enumerate(notes) if note['status'] == 'estimated'
                and note.get('note_type') != 'hold' and ni not in assigned | missed]
    owned = defaultdict(set)
    for match in matches:
        lo = match.get('observation_lower_seconds', match.get('combo_lower_seconds'))
        hi = match.get('observation_upper_seconds', match.get('combo_upper_seconds'))
        if lo is None or hi is None:
            continue
        for ri, run in enumerate(runs):
            if run['lane'] == notes[match['note']]['lane'] and onset_overlaps(run, lo, hi, guard):
                owned[ri].add(match['note'])
    proposals = []
    event_rows = defaultdict(list)
    for ni, options in choices.items():
        # Each note needs one refresh family with a unique row decision. Two
        # disjoint possible refreshes remain alternatives even with lane light.
        options = [option for option in options if option['alternative_rows'] == 1 and option['aggregate_row_capacity'] == 1]
        if not options:
            continue
        lower = min(option['upper_seconds'] for option in options)
        upper = max(option['upper_seconds'] for option in options)
        if upper-lower > (data.get('median_frame_interval_seconds') or .017)+.002:
            continue
        supported = []
        for option in options:
            lo, hi = option['lower_seconds'], option['upper_seconds']
            offset = option['ranking_offset_seconds']
            plausible = [index for index, note in eligible if note['lane'] == notes[ni]['lane']
                         and lo-.045-note['prediction_uncertainty_seconds'] <= note['target_seconds']+offset
                         <= hi+.045+note['prediction_uncertainty_seconds']]
            if plausible != [ni]:
                continue
            onset_ids = [ri for ri, run in enumerate(runs) if run['lane'] == notes[ni]['lane']
                         and onset_overlaps(run, option['lower_seconds'], option['upper_seconds'], guard)]
            if len(onset_ids) == 1:
                supported.append((option, onset_ids[0]))
            elif not onset_ids and processing_support(data, ni, lo, hi, guard):
                supported.append((option, ('processing', ni)))
        if not supported or len({ri for _, ri in supported}) != 1:
            continue
        ri = supported[0][1]
        owned[ri].add(ni)
        proposals.append((ni, supported, ri))
        for option, _ in supported:
            event_rows[(option['source'], option['event'])].append(notes[ni]['target_seconds'])
    recovered = []
    for ni, supported, ri in proposals:
        if owned[ri] != {ni} or any(max(event_rows[(option['source'], option['event'])])-min(event_rows[(option['source'], option['event'])]) >= .025 for option, _ in supported):
            continue
        # Prefer the narrowest original display bracket; an independent onset
        # confirms row ownership but does not replace the observed timestamp.
        option, _ = min(supported, key=lambda pair: (pair[0]['upper_seconds']-pair[0]['lower_seconds'], pair[0]['source']))
        target = notes[ni]['target_seconds']
        match = {'note': ni, 'target_seconds': target, 'row_note_count': 1, 'aggregate_row_count': 1,
                 'combo_event': None, 'judgment_event': None, 'evidence_source': option['source']+('+note_disappearance' if isinstance(ri, tuple) else '+lane_onset'),
                 'observation_lower_seconds': option['lower_seconds'], 'observation_upper_seconds': option['upper_seconds'],
                 'raw_offset_lower_ms': (option['lower_seconds']-target)*1000,
                 'raw_offset_upper_ms': (option['upper_seconds']-target)*1000,
                 'recovery_method': 'unique_row_with_note_disappearance' if isinstance(ri, tuple) else 'unique_row_with_independent_lane_onset'}
        if isinstance(ri, tuple):
            proof = processing_support(data, ni, option['lower_seconds'], option['upper_seconds'], guard)
            match.update(processing_range=proof['range'], processing_source_pts_seconds=proof['source_pts_seconds'])
        else:
            match.update(lane_onset_range=runs[ri].get('onset_range'),
                         lane_onset_source_pts_seconds=runs[ri].get('onset_source_pts_seconds'))
        for supported_option, _ in supported:
            source, ei = supported_option['source'], supported_option['event']
            match['combo_event' if source == 'combo' else 'judgment_event'] = ei
            if source == 'combo':
                event = data['combo_events'][ei]
                match.update(combo_lower_seconds=event['lower_seconds'], combo_upper_seconds=event['upper_seconds'])
            else:
                match['judgment_label'] = data['judgment_events'][ei]['label']
        matches.append(match)
        recovered.append(ni)
    for match in matches:
        if match['note'] not in recovered:
            continue
        match['row_note_count'] = sum(abs(other['target_seconds']-match['target_seconds']) < .025 and (
            match.get('combo_event') is not None and other.get('combo_event') == match['combo_event']
            or match.get('judgment_event') is not None and other.get('judgment_event') == match['judgment_event']) for other in matches)
    return matches, recovered
