"""Interpret concrete chart effects without changing native evidence or grades."""
from collections import Counter

from piu_timeline.play.channels import processing_evidence, receptor_evidence, annotate_matches
from piu_timeline.play.frames import TIME_EPSILON
from piu_timeline.play.receptors import onset_overlaps
from piu_timeline.play.processing import processing_support
from piu_timeline.play.tracking import associate


FORMAT = {'schema':1, 'revision':5}


def active_effects(data, kind):
    return [effect for effect in data.get('chart_policy',{}).get('gimmick_candidates',[])
            if effect['kind'] == kind and effect['review_status'] != 'rejected']


def contains(effect, lo, hi):
    return effect['playback_start_seconds'] <= lo and hi < effect['playback_end_seconds']


def visibility_modifier(data):
    """Expected pre-receptor loss is hidden visibility, never consumption/input."""
    effects = active_effects(data,'suspected_visibility_modifier')
    if not effects:
        return data
    records = []
    for record in processing_evidence(data):
        # The native boundary record names the independently observed losses.
        owners = [e for e in effects if any(
            boundary['notes'] and record['note'] in boundary['notes']
            and e['playback_start_seconds'] <= boundary['playback_range'][0]
            and boundary['playback_range'][1] <= e['playback_end_seconds']+TIME_EPSILON
            for boundary in data['visual_channels']['processing'].get('visibility_boundaries',[]))]
        if record.get('reason') == 'pre_receptor_visibility_boundary' and owners:
            record = {**record, 'status':'visibility_modified', 'reason':'chart_visibility_modifier',
                      'gimmick_candidates':[e['id'] for e in owners],
                      'native_status':record['status'], 'native_reason':record['reason']}
        records.append(record)
    channels = data['visual_channels']
    processing = {**channels['processing'],'notes':records,'counts':dict(Counter(r['status'] for r in records))}
    return {**data,'visual_channels':{**channels,'processing':processing}}


def simultaneous_increment(data):
    """A configured +N represents one refresh row, with independent ownership."""
    effects = active_effects(data,'suspected_multi_increment')
    if not effects:
        return data
    events = [dict(e) for e in data.get('combo_events',[])]
    adapted = {}
    for i,event in enumerate(events):
        owners = [e for e in effects if contains(e,event['lower_seconds'],event['upper_seconds'])]
        increments = {e['combo_increment'] for e in owners}
        if len(increments) != 1:
            if owners:
                event.update(gimmick_error='conflicting_simultaneous_increments',judged_row_count=None,
                             status='excluded',reason='conflicting_simultaneous_increments')
                adapted[i] = None
            continue
        increment = increments.pop()
        if event.get('delta',0) <= 1:
            continue
        event.update(gimmick_candidates=[e['id'] for e in owners],combo_increment=increment)
        # A missing whole refresh is not a new opportunity to guess rows.
        if (event.get('delta') != increment or not 0 < event['upper_seconds']-event['lower_seconds'] <= .1+TIME_EPSILON):
            event.update(judged_row_count=None,status='excluded',reason='counter_change_not_one_configured_increment',
                         gimmick_error='counter_change_not_one_configured_increment')
            adapted[i] = None
        else:
            event.update(judged_row_count=1,status='candidate',reason=None)
            adapted[i] = {**event,'delta':1}
    if not adapted:
        return {**data,'combo_events':events}
    # Remove associations that relied on treating +N as N distinct rows. An
    # independently associated word keeps its own bracket and grade.
    matches = []
    for match in data.get('matches',[]):
        if match.get('combo_event') not in adapted:
            matches.append(dict(match));continue
        if match.get('judgment_event') is not None:
            event = data['judgment_events'][match['judgment_event']]
            lo,hi = event['lower_seconds'],event['upper_seconds']
            target = match['target_seconds']
            kept = {**match,'combo_event':None,'evidence_source':'judgment',
                    'observation_lower_seconds':lo,'observation_upper_seconds':hi,
                    'raw_offset_lower_ms':1000*(lo-target),'raw_offset_upper_ms':1000*(hi-target)}
            kept.pop('combo_lower_seconds',None);kept.pop('combo_upper_seconds',None)
            matches.append(kept)
    matched = {m['note']:m for m in matches}
    missed = {m['note'] for m in data.get('miss_candidates',[])}
    runs = receptor_evidence(data)
    guard = 2*(data.get('median_frame_interval_seconds') or .017)
    proposals,indices,constraints = [],[],{}
    for i,event in adapted.items():
        if event is None:
            continue
        lo,hi = event['lower_seconds'],event['upper_seconds']
        if any(e.get('label') == 'MISS' and e['lower_seconds'] <= hi+guard and e['upper_seconds'] >= lo-guard
               for e in data.get('judgment_events',[])):
            events[i].update(status='excluded',reason='competing_miss_evidence')
            continue
        allowed = []
        for ni,note in enumerate(data['notes']):
            if note['status'] != 'estimated' or note.get('note_type') == 'hold' or ni in missed or note.get('prediction_uncertainty_seconds',1) > .05:
                continue
            hold_data = data.get('hold_analysis',{})
            if any(h.get('lane') == note['lane'] and h['start_range'][0]-guard <= hi
                   and (h['end_range'][1] if h.get('end_range') else h['last_body_seconds']+.25)+guard >= lo
                   for h in hold_data.get('holds',[])):
                continue
            if any(t['lane']==note['lane'] and t['visible_start_seconds']-guard <= hi
                   and t['visible_end_seconds']+.25+guard >= lo for t in hold_data.get('unresolved_tracks',[])):
                continue
            if ni in matched:
                m=matched[ni]
                if not (lo <= m.get('observation_upper_seconds',-1)+guard and hi >= m.get('observation_lower_seconds',float('inf'))-guard):
                    continue
            onset = [r for r in runs if r['lane']==note['lane'] and onset_overlaps(r,lo,hi,guard)]
            owned = any(m['note'] != ni and data['notes'][m['note']]['lane']==note['lane']
                        and onset and onset_overlaps(onset[0],
                            m.get('observation_lower_seconds',m.get('combo_lower_seconds',-10)),
                            m.get('observation_upper_seconds',m.get('combo_upper_seconds',-10)),guard)
                        for m in matches)
            if not owned and (len(onset)==1 or processing_support(data,ni,lo,hi,guard)):
                allowed.append(ni)
        constraints[len(proposals)] = allowed
        indices.append(i);proposals.append(event)
    recovered = associate(data['notes'],proposals,display_delay=data.get('display_delay_correction_ms',0)/1000,
                          event_note_constraints=constraints)
    for match in recovered:
        local = match['combo_event'];index = indices[local]
        match.update(combo_event=index,combo_increment=events[index]['combo_increment'],
                     recovery_method='configured_simultaneous_increment_with_lane_evidence',
                     evidence_source='combo+lane_evidence')
        existing = matched.get(match['note'])
        if existing is not None:
            existing.update(combo_event=index,combo_lower_seconds=match['combo_lower_seconds'],
                            combo_upper_seconds=match['combo_upper_seconds'],combo_increment=match['combo_increment'],
                            evidence_source=existing.get('evidence_source','judgment')+'+configured_combo')
        else:
            matches.append(match);matched[match['note']]=match
    for local,index in enumerate(indices):
        events[index].update(status=proposals[local]['status'],reason=proposals[local].get('reason'))
    coverage = {**data.get('coverage',{}),'timed_note_heads':len(matches),
                'matched_combo_updates':len({m['combo_event'] for m in matches if m.get('combo_event') is not None}),
                'judgment_labeled_note_heads':sum(bool(m.get('judgment_label')) for m in matches),
                'unlabeled_timed_note_heads':sum(not m.get('judgment_label') for m in matches)}
    return annotate_matches({**data,'combo_events':events,'matches':sorted(matches,key=lambda m:m['target_seconds']),
                             'coverage':coverage})


from piu_timeline.play.scroll_pauses import apply as scroll_pauses
from piu_timeline.play.scroll_speeds import apply as scroll_speeds

HANDLERS = {'scroll_pause':scroll_pauses, 'scroll_speed_change':scroll_speeds, 'suspected_visibility_modifier':visibility_modifier,
            'suspected_multi_increment':simultaneous_increment}


def apply_gimmicks(data, directory=None):
    for kind,handler in HANDLERS.items():
        data = handler(data)
        if kind=='scroll_speed_change' and directory is not None:
            from piu_timeline.play.scroll_pauses import refresh_processing
            data=refresh_processing(data,directory)
    policy = data.get('chart_policy')
    if policy:
        unsupported = [e['id'] for e in policy.get('gimmick_candidates',[])
                       if e['review_status'] != 'rejected' and e['kind'] not in HANDLERS]
        data = {**data,'chart_policy':{**policy,'gimmick_format':FORMAT,'unsupported_gimmicks':unsupported}}
    return data
