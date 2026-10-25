"""Split confirmed bursts only at independently observed intermediate values."""
from piu_timeline.play.frames import TIME_EPSILON


def refine_events(events, observations):
    if not observations:
        return list(events)
    result = []
    for event in events:
        before,after = event['before'],event['after']
        lo,hi = event['lower_seconds'],event['upper_seconds']
        confirmation = event.get('confirmation_seconds')
        if (not 2 <= event['delta'] <= 10 or not 0 < hi-lo <= .1+TIME_EPSILON
                or confirmation is None or not 0 <= confirmation-hi <= .075+TIME_EPSILON):
            result.append(event);continue
        reads = [r for r in observations if lo <= r['playback_seconds'] <= hi]
        if not reads or any(not before <= r['value'] <= after for r in reads):
            result.append(event);continue
        if any(a['value'] > b['value'] for a,b in zip(reads,reads[1:])):
            result.append(event);continue
        states = {value:[r for r in reads if r['value']==value] for value in range(before,after+1)}
        if (not states[before] or not states[after]
                or any(not states[value] or any(r.get('confidence',0) < .9
                       or r.get('read_mode') != 'independent_template' for r in states[value])
                       for value in range(before+1,after))):
            result.append(event);continue
        proof = {'before':before,'after':after,'lower_seconds':lo,'upper_seconds':hi,
                 'confirmation_seconds':confirmation,
                 'intermediate_observations':[dict(r) for r in reads if before < r['value'] < after]}
        for value in range(before,after):
            old,new = states[value][-1],states[value+1][0]
            result.append({**event,'before':value,'after':value+1,'delta':1,
                           'lower_seconds':old['playback_seconds'],'upper_seconds':new['playback_seconds'],
                           'source_pts_seconds':[old.get('source_pts_seconds'),new.get('source_pts_seconds')],
                           'refinement_method':'independently_observed_intermediate_counter',
                           'aggregate_origin':proof})
    return result


def refinement_constraints(notes, original_events, baseline_matches, refined_events):
    """Keep unique unaffected row identities from drifting when events are split."""
    def key(event):
        return tuple(event.get(k) for k in ('before','after','lower_seconds','upper_seconds'))
    original = {key(event):i for i,event in enumerate(original_events)}
    groups = {}
    for match in baseline_matches:
        groups.setdefault(match['combo_event'],set()).add(match['note'])
    owned = {ni:ei for ei,group in groups.items() for ni in group}
    estimated = {ni for ni,note in enumerate(notes) if note['status']=='estimated'}
    constraints = {}
    for i,event in enumerate(refined_events):
        parent = original[key(event.get('aggregate_origin',event))]
        # A baseline aggregate gives a uniquely aligned constituent set, not
        # permission to violate any tighter native sub-bracket. The associator
        # still checks timing, ordering and ambiguity within this set.
        constraints[i] = groups.get(parent,estimated-{ni for ni,ei in owned.items() if ei != parent})
    return constraints
