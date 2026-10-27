"""Retain connected cap roles when a hold's chart timing remains unresolved."""
from collections import defaultdict


def observed_tail_roles(data):
    if data.get('skin_detector'):
        from piu_timeline.play.skins.observations import tail_roles
        return tail_roles(data)
    types={r['note']:{o['kind']for o in r.get('observations',[])}-{'unknown'}
           for r in data.get('visual_channels',{}).get('note_types',{}).get('notes',[])}
    pairs=defaultdict(list);heads=defaultdict(set);tails=defaultdict(set)
    for record in data.get('hold_analysis',{}).get('unresolved_tracks',[]):
        proof=record.get('cap_continuity')or{}
        if proof.get('decision')!='connected_caps' or proof.get('gap_source_pts_seconds'):continue
        head,tail=proof.get('head_note'),proof.get('tail_note')
        if any(type(i)is not int or not 0<=i<len(data['notes'])for i in (head,tail))or head==tail:continue
        if data['notes'][head]['lane']!=data['notes'][tail]['lane']:continue
        connected=set(proof.get('connected_source_pts_seconds',[]))
        count=len(connected|set(proof.get('gap_source_pts_seconds',[]))|set(proof.get('weak_source_pts_seconds',[])))
        if (len(connected)<8 or len(connected)<.8*count
                or proof['visible_end_seconds']-proof['visible_start_seconds']<.12):continue
        # A clear isolated-cap observation contradicts an automatic tail role.
        # Keep that conflict unresolved, rather than voting it away.
        if types.get(head)!={'hold'}or types.get(tail)!={'hold'}:continue
        pairs[head,tail].append(proof);heads[head].add(tail);tails[tail].add(head)
    result=[]
    for (head,tail),proofs in pairs.items():
        if len(heads[head])!=1 or len(tails[tail])!=1 or head in tails or tail in heads:continue
        result.append({'head_note':head,'tail_note':tail,'lane':data['notes'][tail]['lane'],
                       'status':'observed_connection_timing_unresolved',
                       'visible_start_seconds':min(p['visible_start_seconds']for p in proofs),
                       'visible_end_seconds':max(p['visible_end_seconds']for p in proofs),
                       'source_pts_seconds':sorted({t for p in proofs for t in p['connected_source_pts_seconds']})})
    return result
