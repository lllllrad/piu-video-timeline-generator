"""Hold analysis orchestration and projection; pixels, geometry and state are separate."""
from collections import Counter
from hashlib import sha256
import json

from piu_timeline.play.holds.features import FEATURE_FORMAT, acquire_features, feature_contract
from piu_timeline.play.holds.geometry import HoldGeometry, body_tracks, hold_start, register_caps, resolve_geometry, retain_hold
from piu_timeline.play.holds.state import contextual_hold_support, recognition_segments, recognition_window, receptor_runs
from piu_timeline.play.holds.continuity import CapContinuity

ASSOCIATION_FORMAT = {'schema': 1, 'revision': 38}


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def reconstruct(data, frames, diagnostics=None):
    """Resolve chart geometry first, then attach independent recognition spans."""
    from piu_timeline.play.object_roles import filter_frames
    frames=filter_frames(data,frames,bodies=True)
    geometry = HoldGeometry.from_analysis(data, FEATURE_FORMAT['width'])
    frames = register_caps(data, frames, geometry)
    frame_times = [frame['playback_seconds'] for frame in frames]
    continuity = CapContinuity(data, frames, geometry)
    holds = []
    for track in body_tracks(frames, geometry.spacing):
        native_components=[{'source_pts_seconds':p['pts'],'playback_seconds':p['time'],
                            'components':p.get('source_components',[]),'bounds':p.get('foreground_bounds')}
                           for p in track]
        hold = resolve_geometry(data, track, geometry)
        connection = continuity.check(track)
        if connection and connection['decision'] == 'disconnected_caps':
            hold = None
        if hold is None:
            extended = [p for p in track if p['long'] and p.get('stripe_support', 1) >= .72]
            if diagnostics is not None and len(extended) >= 4:
                cap_evidence = []
                for edge in ('top', 'bottom'):
                    for index in {p[edge+'_observed_cap_note'] for p in track if edge+'_observed_cap_note' in p}:
                        pts = [p['pts'] for p in track if p.get(edge+'_observed_cap_note') == index]
                        if len(set(pts)) >= 4:
                            cap_evidence.append({'edge': edge, 'note': index, 'source_pts_seconds': pts,
                                                 'timing_accepted':data['notes'][index]['status']=='estimated'})
                diagnostics.append({'lane': track[0]['lane'], 'reason': 'unresolved_hold_geometry',
                                    'visible_start_seconds': track[0]['time'], 'visible_end_seconds': track[-1]['time'],
                                    'source_pts_range': [track[0]['pts'], track[-1]['pts']],
                                    'native_component_evidence':native_components,
                                    'cap_continuity': connection,
                                    'cap_evidence': cap_evidence, 'observed_points': len(track)})
            continue
        hold['id'] = len(holds)
        hold['native_component_evidence']=native_components
        retain_hold(holds, hold)
    contextual = contextual_hold_support(data, frames, geometry.receptor, geometry.spacing, holds)
    for hold in holds:
        window = recognition_window(data, hold, geometry)
        hold['input'] = recognition_segments(frames, frame_times, hold, contextual, window)
    return holds


def augment_holds(data, output):
    # Synthetic/legacy metadata without source stream geometry cannot reacquire
    # pixels; keep it explicit rather than invoking a decoder with invented data.
    if not data.get('media', {}).get('video_streams') or any('color' not in lane for lane in data.get('layout', {}).get('lanes', [])):
        return data
    from piu_timeline.play.channels import augment_channels
    contract = feature_contract(data)
    association = {'format': ASSOCIATION_FORMAT, 'notes': fingerprint(data['notes']),
                   'object_roles':fingerprint(data.get('object_interpretation',{}).get('effects',[])),
                   'hud_events': fingerprint({key: data.get(key, []) for key in ('combo_events', 'judgment_events')})}
    if data.get('skin_detector'):
        from piu_timeline.play.skins.holds import FORMAT as IMAGE_HOLD_FORMAT
        association['skin_images'] = data['skin_detector']['contract']
        association['image_hold_format'] = IMAGE_HOLD_FORMAT
    path = output / 'holds.json'
    if path.is_file():
        saved = json.loads(path.read_text())
        if (saved.get('feature_contract') == contract and saved.get('association_contract') == association
                and all((output/name).is_file() for name in
                        ('hold-features.json','hold-frames.jsonl','processing-features.npz'))):
            return augment_channels({**data, 'hold_analysis': saved}, output)
    acquire_features(data, output)
    with (output / 'hold-frames.jsonl').open() as stream:
        frames = [json.loads(line) for line in stream]
    from piu_timeline.play.object_roles import filter_frames
    interpreted=filter_frames(data,frames,bodies=True)
    art=[{'source_pts_seconds':raw['source_pts_seconds'],'playback_seconds':raw['playback_seconds'],
          'observation':body,'role':'decorative_art'}for raw,view in zip(frames,interpreted,strict=True)
         for body in raw['bodies']if body not in view['bodies']]
    from piu_timeline.play.receptors import observations, reject_common_flashes
    frames = reject_common_flashes(frames, observations(data, output, frames))
    unresolved = []
    if data.get('skin_detector'):
        from piu_timeline.play.skins.holds import reconstruct_images
        native = filter_frames(data,[json.loads(line) for line in (output/'frames.jsonl').open()])
        holds = reconstruct_images(data, frames, native, unresolved)
    else:
        holds = reconstruct(data, frames, unresolved)
    result = {'feature_contract': contract, 'association_contract': association, 'holds': holds,
              'decorative_body_observations':art,
              'unresolved_tracks': unresolved, 'receptor_runs': receptor_runs(frames),
              'semantics': 'Long notes are sustained states. Hold ticks are not independent presses; release is not measured.'}
    pending = path.with_suffix('.build-json')
    pending.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    pending.replace(path)
    return augment_channels({**data, 'hold_analysis': result}, output, frames)


def chart_projection(data):
    """Project visible chart geometry and types without reading input associations."""
    holds = data.get('hold_analysis', {}).get('holds', [])
    if not data.get('hold_analysis'):
        from piu_timeline.play.note_types import project_types
        notes=[dict(note) for note in data.get('notes',[])]
        diagnostics=project_types(data,notes,[])
        return {**data,'notes':notes,'note_type_diagnostics':diagnostics}
    notes = [dict(note) for note in data['notes']]
    # Accepted caps are boundaries of one held interval, even when a cap's
    # estimated crossing fell outside the body's covered-note time envelope.
    suppressed = {index for hold in holds for index in
                  [*hold['covered_notes'],hold.get('head_note'),hold.get('tail_note')] if index is not None}
    from piu_timeline.play.holds.roles import observed_tail_roles
    tail_roles=[r for r in observed_tail_roles(data) if r['tail_note']not in suppressed]
    pending_tails={r['tail_note']for r in tail_roles}
    suppressed.update(pending_tails)
    for index in suppressed:
        notes[index].update(status='excluded', reason='long_note_body_or_tail', note_type='hold_component')
    for role in tail_roles:
        notes[role['tail_note']].update(reason='observed_hold_tail_pending_geometry',
                                      hold_cap_role='tail',observed_hold_head=role['head_note'])
    projected, unresolved_holds = [], []
    for original in holds:
        hold = dict(original)
        hold['covered_notes']=sorted(set(hold['covered_notes'])|{
            index for index in (hold.get('head_note'),hold.get('tail_note')) if index is not None})
        hold['input_requirement']='held_state'
        hold['requires_head_press']=False
        start = hold['start_range']
        target = hold_start(hold)
        head = hold['head_note']
        if head is None or head not in suppressed:
            head = len(notes)
            notes.append({'lane': hold['lane'], 'points': [], 'target_seconds': target})
            observed=hold.get('head_observation_note')
            if observed is not None:
                notes[head]['source_head_observation']=observed
                for field in ('timing_reconstruction','beat_reconstruction'):
                    if field in data['notes'][observed]:notes[head][field]=dict(data['notes'][observed][field])
        notes[head].update(status='estimated', reason=None, note_type='hold', hold_id=hold['id'],
                           input_requirement='held_state',requires_head_press=False,
                           target_seconds=target,
                           prediction_uncertainty_seconds=0 if hold['start_censored'] else (start[1]-start[0])/2)
        if notes[head].get('timing_reconstruction',{}).get('status')=='failed' or notes[head].get('beat_reconstruction',{}).get('status')=='failed':
            notes[head].update(status='excluded',reason='timing_reconstruction_failed')
        hold['display_note'] = head
        if notes[head]['status'] == 'estimated':
            projected.append(hold)
        else:
            unresolved_holds.append({**hold, 'projection_failure': notes[head]['reason']})
    from piu_timeline.play.note_types import project_types
    diagnostics=project_types(data,notes,projected)
    return {**data,'notes':notes,'note_type_diagnostics':diagnostics,
            'hold_analysis':{**data['hold_analysis'],'holds':projected,
                             'unresolved_holds':unresolved_holds,'observed_tail_roles':tail_roles}}


def presentation(data):
    """Attach independent recognition evidence to the projected visible chart."""
    view=chart_projection(data)
    if not data.get('hold_analysis'):return view
    notes=view['notes'];holds=data['hold_analysis'].get('holds',[])
    projected=view['hold_analysis']['holds'];tail_roles=view['hold_analysis']['observed_tail_roles']
    suppressed={index for hold in [*projected,*view['hold_analysis']['unresolved_holds']]
                for index in hold['covered_notes']}|{r['tail_note']for r in tail_roles}
    def during_hold(lo, hi):
        return any(hi >= (hold['start_range'][1] if hold['start_censored'] else sum(hold['start_range'])/2) + .04
                   and lo <= (sum(hold['end_range'])/2 if hold['end_range'] else hold['last_body_seconds'])
                   for hold in holds)
    # A dense interval is a warning about hold ticks, not proof that every
    # other lane is a hold. Retain strict row alignments until lane evidence
    # can distinguish an independent tap from sustained recognition.
    input_matches = list(data['matches'])
    assigned = {match['note'] for match in input_matches}
    deferred = []
    for match in data.get('deferred_matches', []):
        index = match['note']
        if index in assigned or notes[index]['status'] != 'estimated' or notes[index].get('note_type') == 'hold':
            continue
        event = data['combo_events'][match['combo_event']]
        if event.get('delta') != 1:
            continue
        lo, hi = match['combo_lower_seconds'], match['combo_upper_seconds']
        conflict = False
        for other in input_matches:
            other_lo = other.get('observation_lower_seconds', other.get('combo_lower_seconds'))
            other_hi = other.get('observation_upper_seconds', other.get('combo_upper_seconds'))
            if (other_lo is not None and other_hi is not None and abs(other_hi-hi) <= .025
                    and other_lo <= hi and other_hi >= lo
                    and abs(other['target_seconds']-match['target_seconds']) >= .025):
                conflict = True
                break
        if not conflict:
            deferred.append({**match, 'evidence_source': 'combo+lane_evidence',
                             'observation_lower_seconds': lo, 'observation_upper_seconds': hi,
                             'recovery_method': 'strict_row_alignment_with_independent_lane_evidence'})
    input_matches.extend(deferred)
    from piu_timeline.play.receptors import onset_overlaps
    guard = 2*(data.get('median_frame_interval_seconds') or .017)
    from piu_timeline.play.channels import receptor_evidence
    from piu_timeline.play.processing import processing_support
    runs = receptor_evidence(data)
    owners, note_runs = {}, {}
    for match in input_matches:
        index = match['note']
        if index in suppressed:
            continue
        lo = match.get('observation_lower_seconds', match.get('combo_lower_seconds'))
        hi = match.get('observation_upper_seconds', match.get('combo_upper_seconds'))
        if lo is None or hi is None:
            continue
        for ri, run in enumerate(runs):
            if run['lane'] == notes[index]['lane'] and onset_overlaps(run, lo, hi, guard):
                owners.setdefault(ri, set()).add(index)
                note_runs.setdefault(index, []).append(ri)
    def independent_onset(note_index):
        return any(owners[ri] == {note_index} for ri in note_runs.get(note_index, []))
    matches, ambiguous, processing_confirmed = [], [], set()
    recovered = []
    for match in input_matches:
        if match['note'] in suppressed or notes[match['note']]['status'] != 'estimated':
            continue
        lo = match.get('observation_lower_seconds', match.get('combo_lower_seconds'))
        hi = match.get('observation_upper_seconds', match.get('combo_upper_seconds'))
        if lo is not None and hi is not None and processing_support(data, match['note'], lo, hi, guard):
            processing_confirmed.add(match['note'])
        needs_lane_evidence = match.get('recovery_method') == 'strict_row_alignment_with_independent_lane_evidence'
        if (needs_lane_evidence or lo is not None and hi is not None and during_hold(lo, hi)) and not (independent_onset(match['note']) or processing_support(data, match['note'], lo, hi, guard)):
            ambiguous.append(match['note'])
        else:
            if needs_lane_evidence:
                match = {**match, 'evidence_source': 'combo+'+('lane_onset' if independent_onset(match['note']) else 'note_disappearance')}
            matches.append(match)
            if needs_lane_evidence:
                recovered.append(match['note'])
    def lane_reason(event_index, key, suffix):
        source = 'combo_event' if key == 'combo_events' else 'judgment_event'
        uses_processing = any(m.get(source) == event_index and m['note'] in processing_confirmed for m in matches)
        return 'tap_with_'+('note_disappearance' if uses_processing else 'independent_lane_onset')+'_during_'+suffix
    def events(key):
        result = []
        owned = {match.get('combo_event' if key == 'combo_events' else 'judgment_event') for match in matches}
        for event_index, event in enumerate(data.get(key, [])):
            event = dict(event)
            if key == 'combo_events' and any(m.get('combo_event') == event_index and m.get('aggregate_evidence_method') for m in matches):
                event.update(status='matched', reason='aggregate_counter_with_exclusive_lane_onsets')
            if key == 'combo_events' and event_index in owned and event.get('reason') == 'possible_hold_or_dense_stack':
                event.update(status='matched', reason=lane_reason(event_index, key, 'dense_interval'))
            if event.get('label') != 'MISS' and event.get('delta', 1) > 0 and during_hold(event['lower_seconds'], event['upper_seconds']):
                if event_index in owned:
                    event.update(status='matched', reason=lane_reason(event_index, key, 'hold'))
                else:
                    event.update(status='hold_state_or_tap', reason='ongoing_hold_tick_not_new_press')
            result.append(event)
        return result
    from piu_timeline.play.recovery import recover_rows
    matches, lane_recovered = recover_rows({**data, 'notes': notes, 'matches': matches,
                                          'combo_events': events('combo_events'),
                                          'judgment_events': events('judgment_events'),
                                          'hold_analysis': {**data['hold_analysis'], 'holds': projected,'observed_tail_roles':tail_roles}})
    from piu_timeline.play.recovered_judgments import attach_recovered_labels
    labeled = attach_recovered_labels({**data, 'matches': matches,
                                      'combo_events': events('combo_events'),
                                      'judgment_events': events('judgment_events')})
    matches = labeled['matches']
    for match in matches:
        proof = data.get('counter_judgment_labels', {}).get(str(match.get('combo_event')))
        if proof and not match.get('judgment_label'):
            # The counter bracket is already owned by this recovered row.
            # Reuse its word reads without inventing a word-refresh event.
            match.update(judgment_label=proof['label'], judgment_event=None,
                         judgment_label_source='post_combo_frames',
                         judgment_observations=[dict(item) for item in proof['observations']],
                         evidence_source=match.get('evidence_source', 'combo')+'+judgment')
    coverage = dict(data.get('coverage', {}))
    coverage.update(visible_note_heads=sum(note['status']=='estimated' for note in notes),
                    timed_note_heads=len(matches),
                    matched_combo_updates=len({match['combo_event'] for match in matches if match.get('combo_event') is not None}),
                    judgment_only_note_heads=sum(match.get('evidence_source') == 'judgment' for match in matches),
                    judgment_labeled_note_heads=sum(bool(match.get('judgment_label')) for match in matches),
                    unlabeled_timed_note_heads=sum(not match.get('judgment_label') for match in matches),
                    combo_frame_labeled_note_heads=sum(match.get('judgment_label_source') == 'post_combo_frames' for match in matches),
                    long_notes=len(projected),
                    sustained_recognition_spans=sum(len(hold['input']['segments']) for hold in projected))
    limitations = [item.replace('Holds, rolls', 'Rolls') for item in data.get('limitations', [])]
    limitations.append('Long-note recognition is a sustained visual state; neither a separate press per tick nor physical release is measured.')
    from piu_timeline.play.note_types import project_types
    type_diagnostics = project_types(data, notes, projected)
    from piu_timeline.play.channels import annotate_matches
    return annotate_matches({**data, 'notes': notes, 'matches': matches, 'limitations': limitations,
            'excluded_notes': dict(Counter(note.get('reason') for note in notes if note['status'] == 'excluded')),
            'miss_candidates': [candidate for candidate in data.get('miss_candidates', []) if candidate['note'] not in suppressed],
            'combo_events': events('combo_events'), 'judgment_events': labeled['judgment_events'],
            'hold_tick_ambiguous_notes': [index for index in ambiguous if index not in lane_recovered],
            'recovered_dense_notes': recovered, 'recovered_lane_supported_notes': lane_recovered,
            'hold_analysis': view['hold_analysis'], 'coverage': coverage,
            'note_type_diagnostics': type_diagnostics})
