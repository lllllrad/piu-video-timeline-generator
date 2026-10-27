"""Recover aggregate counter evidence only with independent, exclusive tap onsets."""
from collections import defaultdict
from statistics import median

from piu_timeline.play.frames import TIME_EPSILON
from piu_timeline.play.channels import receptor_evidence
from piu_timeline.play.receptors import onset_overlaps
from piu_timeline.play.candidates import target_offsets,target_in_window


def bracket(match):
    return (match.get('observation_lower_seconds', match.get('combo_lower_seconds')),
            match.get('observation_upper_seconds', match.get('combo_upper_seconds')))


def native_body_risk_available(data):
    """A complete image detector supplies receptor-local risk, not warning spans."""
    from piu_timeline.play.skins.held import FORMAT
    skin=data.get('skin_detector',{})
    return (skin.get('contract',{}).get('held_body')==FORMAT
            and skin.get('missing_template_roles')==[] and 'unsupported_intervals'in data)


def hold_overlap(data, lo, hi, guard):
    analysis = data.get('hold_analysis', {})
    for hold in analysis.get('holds', []):
        end = hold['end_range'][1] if hold.get('end_range') else hold['last_body_seconds']+.25
        if hold['start_range'][0]-guard <= hi and end+guard >= lo:
            return True
    if any(interval['start_seconds']-guard<=hi and interval['end_seconds']+guard>=lo
           for interval in data.get('unsupported_intervals',[])):return True
    for track in analysis.get('unresolved_tracks', []):
        # These are unrelated image tiles grouped for review, not a connected
        # body persisting from the first tile to the last. Their actual receptor
        # risk is measured independently in the native frame observations.
        if (native_body_risk_available(data)
                and track.get('failure_detail')=='skin_body_images_without_complete_endpoint_ownership'
                and track.get('image_evidence')
                and all(p.get('role')=='hold_body'for p in track['image_evidence'])):continue
        if track['visible_start_seconds']-guard<=hi and track['visible_end_seconds']+.25+guard>=lo:return True
    return False


def recover_aggregates(data):
    notes, original = data.get('notes', []), data.get('matches', [])
    matched = {m['note']: m for m in original}
    missed = {m['note'] for m in data.get('miss_candidates', [])}
    runs = receptor_evidence(data)
    guard = 2*(data.get('median_frame_interval_seconds') or .017)
    owned = defaultdict(set)
    for match in original:
        lo, hi = bracket(match)
        if lo is None or hi is None:
            continue
        for ri, run in enumerate(runs):
            if run['lane'] == notes[match['note']]['lane'] and onset_overlaps(run, lo, hi, guard):
                owned[ri].add(match['note'])
    proposals = []
    claims = defaultdict(set)
    note_claims = defaultdict(set)
    for ei, event in enumerate(data.get('combo_events', [])):
        lo, hi, count = event['lower_seconds'], event['upper_seconds'], event.get('delta', 0)
        if not 2 <= count <= 10 or not 0 < hi-lo <= .1+TIME_EPSILON:
            continue
        if event.get('reason') in ('combo_reset', 'combo_jump_or_observation_gap') or hold_overlap(data, lo, hi, guard):
            continue
        if any(e.get('label') == 'MISS' and e['lower_seconds'] <= hi+guard and e['upper_seconds'] >= lo-guard
               for e in data.get('judgment_events', [])):
            continue
        anchors = [m for m in original if abs(m['target_seconds']-(lo+hi)/2)<1 and None not in bracket(m)]
        local=median([sum(bracket(m))/2-m['target_seconds']for m in anchors])if anchors else data.get('display_delay_correction_ms',0)/1000
        offsets=target_offsets(data,local)
        plausible = [(i,n) for i,n in enumerate(notes) if n['status'] == 'estimated' and n.get('note_type') != 'hold'
                     and any(target_in_window(n,lo,hi,offset)for offset in offsets)
                     and n['target_seconds']+data.get('display_delay_correction_ms', 0)/1000-.25 <= hi
                     and n['target_seconds']+data.get('display_delay_correction_ms', 0)/1000+.5 >= lo]
        rows = []
        for i, note in sorted(plausible, key=lambda pair: pair[1]['target_seconds']):
            if rows and note['target_seconds']-notes[rows[-1][0]]['target_seconds'] < .025:
                rows[-1].append(i)
            else:
                rows.append([i])
        # Single taps avoid assuming whether an unfamiliar chord increments
        # the counter per head or per row. Extra plausible rows remain ambiguous.
        if len(rows) != count or any(len(row) != 1 for row in rows):
            continue
        group = [row[0] for row in rows]
        if not any(all(target_in_window(notes[i],lo,hi,offset)for i in group)for offset in offsets):continue
        if any(notes[i]['prediction_uncertainty_seconds'] > .05 for i in group):
            continue
        if any(m['note'] not in group and None not in bracket(m) and bracket(m)[0] < hi and bracket(m)[1] > lo
               for m in original):
            continue
        if all(i in matched for i in group) or missed.intersection(group):
            continue
        if any(i in matched and (matched[i].get('combo_event') not in (None, ei)
                                or bracket(matched[i])[0] > hi or bracket(matched[i])[1] < lo) for i in group):
            continue
        if any(m.get('combo_event') == ei and m['note'] not in group for m in original):
            continue
        proofs = {i: [ri for ri,r in enumerate(runs) if r['lane'] == notes[i]['lane'] and onset_overlaps(r, lo, hi, guard)]
                  for i in group}
        if any(len(ids) != 1 for ids in proofs.values()):
            continue
        proofs = {i: ids[0] for i,ids in proofs.items()}
        if len(set(proofs.values())) != len(group) or any(owned[ri]-{i} for i,ri in proofs.items()):
            continue
        proposals.append((ei, group, proofs))
        for i,ri in proofs.items():
            claims[ri].add(ei); note_claims[i].add(ei)
    result = {i: dict(m) for i,m in matched.items()}
    recovered = []
    for ei, group, proofs in proposals:
        if any(len(claims[ri]) != 1 or len(note_claims[i]) != 1 for i,ri in proofs.items()):
            continue
        event = data['combo_events'][ei]
        lo, hi = event['lower_seconds'], event['upper_seconds']
        for i in group:
            run = runs[proofs[i]]
            common = {'combo_event': ei, 'combo_lower_seconds': lo, 'combo_upper_seconds': hi,
                      'aggregate_body_risk_basis':'native_receptor_body_regions'if native_body_risk_available(data)else'hold_geometry_and_unresolved_tracks',
                      'aggregate_target_offset_hypotheses_seconds':offsets,
                      'aggregate_row_count': event['delta'], 'aggregate_lane_onset_range': run.get('onset_range'),
                      'aggregate_lane_onset_source_pts_seconds': run.get('onset_source_pts_seconds'),
                      'aggregate_evidence_method': 'exclusive_tap_onsets_for_complete_counter_increment'}
            if i in result:
                # A separately recognized word can retain its narrower bracket
                # and grade. Never give its grade to the other aggregate rows.
                result[i].update(common)
                result[i]['evidence_source'] = 'combo+lane_onset'+('+judgment' if result[i].get('judgment_event') is not None or result[i].get('judgment_label') else '')
                continue
            target = notes[i]['target_seconds']
            result[i] = {**common, 'note': i, 'target_seconds': target, 'row_note_count': 1,
                         'judgment_event': None, 'evidence_source': 'combo+lane_onset',
                         'recovery_method': 'aggregate_counter_with_exclusive_lane_onsets',
                         'observation_lower_seconds': lo, 'observation_upper_seconds': hi,
                         'raw_offset_lower_ms': (lo-target)*1000, 'raw_offset_upper_ms': (hi-target)*1000}
            recovered.append(i)
    return sorted(result.values(), key=lambda m:m['target_seconds']), recovered
