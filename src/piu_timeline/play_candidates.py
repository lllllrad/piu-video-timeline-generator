"""Constrain review alternatives by event ownership, row order and lane pixels."""
from collections import defaultdict
from statistics import median

from .play_receptors import onset_overlaps


EARLY_SECONDS = .25
LATE_SECONDS = .5


def association_window(note, correction=0):
    """Hard limits around the fitted target; uncertainty cannot widen them."""
    center = note['target_seconds'] + correction
    return [center - EARLY_SECONDS, center + LATE_SECONDS]


def intersect_window(interval, window):
    lo, hi = max(interval[0], window[0]), min(interval[1], window[1])
    return [lo, hi] if lo <= hi else None


def candidates(data, events):
    notes, matches = data.get('notes', []), data.get('matches', [])
    correction = data.get('display_delay_correction_ms', 0) / 1000
    frame = data.get('median_frame_interval_seconds') or .017
    lit = defaultdict(list)
    sensor = defaultdict(lambda: [0, 0])
    for run in data.get('hold_analysis', {}).get('receptor_runs', []):
        if run['lit'] is None:
            continue
        sensor[run['lane']][bool(run['lit'])] += run['frames']
        if run['lit']:
            lit[run['lane']].append(run)
    anchors = []
    owners = defaultdict(list)
    for match in matches:
        lo = match.get('observation_lower_seconds', match.get('combo_lower_seconds'))
        hi = match.get('observation_upper_seconds', match.get('combo_upper_seconds'))
        if lo is None or hi is None:
            continue
        anchor = {'lo': lo, 'hi': hi, 'target': match['target_seconds'], 'note': match['note']}
        anchors.append(anchor)
        if match.get('combo_event') is not None:
            owners[('combo', match['combo_event'])].append(anchor)
        if match.get('judgment_event') is not None:
            owners[('judgment', match['judgment_event'])].append(anchor)
    assigned = {match['note'] for match in matches}
    missed = {candidate['note'] for candidate in data.get('miss_candidates', [])}
    eligible = [(i, note) for i, note in enumerate(notes) if note['status'] == 'estimated'
                and note.get('note_type') != 'hold' and i not in assigned | missed]
    # Counter, word and raw-reader evidence of the same display refresh share
    # one row decision. They cannot independently vote for neighboring notes.
    families = []
    for event in sorted(events, key=lambda e: (e['upper_seconds'], e['lower_seconds'])):
        family = next((family for family in reversed(families[-4:])
                       if abs(family['hi']-event['upper_seconds']) <= frame+.002
                       and event['lower_seconds'] <= family['hi']+.01
                       and all(e['source'] != event['source'] for e in family['events'])), None)
        if family is None:
            families.append({'lo': event['lower_seconds'], 'hi': event['upper_seconds'], 'events': [event]})
        else:
            family['events'].append(event)
            family['lo'] = min(family['lo'], event['lower_seconds'])
            family['hi'] = max(family['hi'], event['upper_seconds'])
    result = defaultdict(list)
    rejected = defaultdict(set)
    for family in families:
        lo, hi = family['lo'], family['hi']
        owned = [owner for event in family['events'] for owner in owners[(event['source'], event['event'])]]
        # Raw observations may duplicate a confirmed refresh without its ID.
        if not owned:
            owned = [anchor for anchor in anchors if abs(anchor['hi']-hi) <= frame+.002
                     and anchor['lo'] <= hi and anchor['hi'] >= lo]
        before = [anchor for anchor in anchors if anchor['hi'] < lo-.01]
        after = [anchor for anchor in anchors if anchor['lo'] > hi+.01]
        previous = max(before, key=lambda a: a['hi'], default=None)
        following = min(after, key=lambda a: a['lo'], default=None)
        nearby = [anchor for anchor in anchors if abs((anchor['lo']+anchor['hi'])/2-(lo+hi)/2) < 1]
        offset = median([(a['lo']+a['hi'])/2-a['target'] for a in nearby]) if nearby else correction
        rows, supports = [], {}
        for index, note in sorted(eligible, key=lambda item: item[1]['target_seconds']):
            target, uncertainty = note['target_seconds'], note['prediction_uncertainty_seconds']
            window = association_window(note, correction)
            overlap = intersect_window([lo, hi], window)
            if overlap is None:
                # Keep this as a hard rejection so neighbor bounds cannot
                # resurrect an out-of-window refresh as a connection.
                rejected[index].add('outside_association_window')
                continue
            support_lo, support_hi = overlap
            lane = note.get('lane')
            if owned and any(abs(owner['target']-target) > .025 or notes[owner['note']].get('lane') == lane for owner in owned):
                rejected[index].add('refresh_already_assigned_to_another_row');continue
            if previous and target < previous['target']-.025 or following and target > following['target']+.025:
                rejected[index].add('violates_processed_row_order');continue
            reliable = min(sensor[lane]) >= 3
            supported = [run for run in lit[lane] if (
                         run['frames'] >= 2 and run['start_seconds'] <= support_hi+frame*2 and run['end_seconds'] >= support_lo-frame*2
                         or onset_overlaps(run, support_lo, support_hi, frame*2))]
            if reliable and not supported:
                rejected[index].add('receptor_lane_not_active');continue
            supports[index] = supported
            hold_tick = any(event.get('reason') == 'ongoing_hold_tick_not_new_press' for event in family['events']) or any(hi >= (hold['start_range'][1] if hold['start_censored'] else sum(hold['start_range'])/2)+.04 and lo <= (sum(hold['end_range'])/2 if hold['end_range'] else hold['last_body_seconds']) for hold in data.get('hold_analysis', {}).get('holds', []))
            if hold_tick and not any(onset_overlaps(run, support_lo, support_hi, frame*2) for run in supported):
                rejected[index].add('hold_tick_without_independent_lane_onset');continue
            distance = max(0, abs(target+offset-(lo+hi)/2)-(hi-lo)/2-uncertainty)
            if rows and abs(target-rows[-1]['target']) < .025:
                rows[-1]['notes'].append(index)
                rows[-1]['cost'] = min(rows[-1]['cost'], distance)
                rows[-1]['uncertainty'] = max(rows[-1]['uncertainty'], uncertainty)
            else:
                rows.append({'target': target, 'notes': [index], 'cost': distance, 'uncertainty': uncertainty})
        if not rows:
            continue
        best = min(row['cost'] for row in rows)
        # Keep near-ties explicitly; reject distant before/after alternatives.
        selected = [row for row in rows if row['cost'] <= best+max(.008, frame/2)]
        capacity = max(event.get('delta', 1) for event in family['events'])
        if capacity > 1:
            center = min(rows, key=lambda row: row['cost'])['target']
            selected += [row for row in rows if row not in selected and abs(row['target']-center) <= hi-lo+.02]
            selected = sorted(selected, key=lambda row: row['cost'])[:capacity]
        for row in rows:
            if row not in selected:
                for index in row['notes']:rejected[index].add('another_note_row_is_better_supported')
        def source_cost(row, event):
            center = (event['lower_seconds']+event['upper_seconds'])/2
            span = event['upper_seconds']-event['lower_seconds']
            return max(0, abs(row['target']+offset-center)-span/2-row['uncertainty'])
        for row in selected:
            for index in row['notes']:
                for event in family['events']:
                    window = association_window(notes[index], correction)
                    candidate_range = intersect_window([event['lower_seconds'], event['upper_seconds']], window)
                    if candidate_range is None:
                        continue
                    # An aggregate counter may cover several rows, but a narrow
                    # word refresh at its end cannot vote for every earlier row.
                    if event.get('delta', 1) == 1 and source_cost(row, event) > min(source_cost(other, event) for other in selected)+max(.008, frame/2):
                        continue
                    result[index].append({**event, 'candidate_range': candidate_range, 'association_window': window,
                                          'constraints': ['hard_timing_window', 'event_ownership', 'processed_row_order', 'closest_row'],
                                          'lane_receptor_support': bool(supports[index]), 'lane_support_runs': supports[index],
                                          'ranking_offset_seconds': offset,
                                          'alternative_rows': len(selected) if capacity == 1 else 1, 'aggregate_row_capacity': capacity})
    return result, {index: sorted(reasons) for index, reasons in rejected.items()}
