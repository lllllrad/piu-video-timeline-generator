"""Infer a connected cap's kind from a same-frame, independently typed cap."""
from collections import defaultdict

FORMAT={'schema':1,'revision':1,'minimum_connected_frames':8,'minimum_span_seconds':.12,
        'minimum_connected_fraction':.8,'propagation':'one_step_from_native_hold_cap'}


def augment_types(data,records,frames):
    """One topology step only; preserve unknown reads and contradictory taps."""
    timeline={f['source_pts_seconds']:f['playback_seconds'] for f in frames}
    native={r['note']:{**r,'observations':[o for o in r['observations']
                                        if o.get('reason')!='connected_to_native_hold_cap']}for r in records}
    positions=[{round(t,6):y for t,y in n.get('points',[])} for n in data['notes']]
    candidates={};owners=defaultdict(set)
    for track in data.get('hold_analysis',{}).get('unresolved_tracks',[]):
        proof=track.get('cap_continuity')or{}
        if proof.get('decision')!='connected_caps' or proof.get('gap_source_pts_seconds'):continue
        a,b=proof.get('head_note'),proof.get('tail_note')
        if (any(type(i)is not int or not 0<=i<len(positions) for i in (a,b))or a==b
                or data['notes'][a]['lane']!=data['notes'][b]['lane']):continue
        connected=set(proof.get('connected_source_pts_seconds',[]))
        total=connected|set(proof.get('weak_source_pts_seconds',[]))
        if (len(connected)<FORMAT['minimum_connected_frames']
                or len(connected)<FORMAT['minimum_connected_fraction']*len(total)
                or proof['visible_end_seconds']-proof['visible_start_seconds']<FORMAT['minimum_span_seconds']):continue
        verified={pts for pts in connected if pts in timeline
                  and round(timeline[pts],6)in positions[a]and round(timeline[pts],6)in positions[b]}
        if verified!=connected:continue
        times=[timeline[pts]for pts in verified]
        if max(times)-min(times)<FORMAT['minimum_span_seconds']:continue
        candidates.setdefault((a,b),set()).update(verified)
        owners[a].add(b);owners[b].add(a)
    additions=defaultdict(list)
    reasons={'complete_cap_with_connected_color_stripe','observed_cap_attached_to_extended_body'}
    for (a,b),pts in candidates.items():
        if owners[a]!={b}or owners[b]!={a}:continue
        for anchor,other in ((a,b),(b,a)):
            if any(o['kind']=='hold'for o in native.get(other,{}).get('observations',[])):continue
            kinds={o['kind']for o in native.get(anchor,{}).get('observations',[])}-{'unknown'}
            if kinds!={'hold'}:continue
            # Read only native pixel/body evidence, never newly inferred kinds.
            samples=[o for o in native.get(anchor,{}).get('observations',[])
                     if o['kind']=='hold'and o.get('reason')in reasons
                     and o.get('source_note')==anchor
                     and o.get('source_pts_seconds')in pts]
            seen=set()
            for sample in samples:
                source=sample['source_pts_seconds'];time=timeline[source]
                if abs(sample['playback_seconds']-time)>1e-6 or source in seen:continue
                seen.add(source)
                additions[other].append({'kind':'hold','reason':'connected_to_native_hold_cap',
                    'source_note':other,'source_pts_seconds':source,'playback_seconds':time,
                    'anchor_note':anchor,'anchor_observation':dict(sample),
                    'connected_pair':[a,b],'connection_source_pts_seconds':sorted(pts),
                    'trace':'hold_analysis.unresolved_tracks.cap_continuity'})
    result=[]
    for record in records:
        observations=[*native[record['note']]['observations'],*additions.get(record['note'],[])]
        observations.sort(key=lambda o:(o['playback_seconds'],o['kind']))
        kinds={o['kind']for o in observations}-{'unknown'}
        result.append({**record,'observations':observations,
                       'status':'conflict'if len(kinds)>1 else next(iter(kinds))if kinds else 'unknown'})
    return result
