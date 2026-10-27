"""Simplify interrupted holds in derived UCS without changing observations."""
import math

from piu_timeline.charts.transcription import measures


POLICY={'revision':1,'maximum_gap_seconds':.12,'maximum_gap_beats':.25,
        'purpose':'similar_judgments_and_continuous_held_state',
        'hold_tick_equivalence':'unverified'}


def simplify(document, observations, endpoints, notes, origin):
    """Bridge short, bounded same-lane gaps unless another head intervenes."""
    spans=measures(document)
    eligible={item['note'] for item in observations if item['kind']=='hold'}
    blockers={}
    for index,note in enumerate(notes):
        if index in eligible:continue
        target=note.get('target_seconds');error=note.get('prediction_uncertainty_seconds',.02)
        bounded=(type(target)in (int,float)and math.isfinite(target)
                 and type(error)in (int,float)and math.isfinite(error)and 0<=error<=.08)
        blockers.setdefault(note.get('lane'),[]).append(
            [target-origin-error,target-origin+error] if bounded else None)
    result=[];edges=dict(endpoints);merges=[]
    holds=sorted((o for o in observations if o['kind']=='hold'),
                 key=lambda o:(o['lane'],sum(edges[o['note'],'head'])))
    for current in holds:
        item=dict(current);ni=item['note'];head=edges[ni,'head'];tail=edges[ni,'tail']
        previous=result[-1] if result else None
        if previous is not None and previous['lane']==item['lane']:
            pi=previous['note'];old_tail=edges[pi,'tail'];lower=head[0]-old_tail[1];upper=head[1]-old_tail[0]
            bridge=[min(old_tail[0],head[0]),max(old_tail[1],head[1])]
            tempos=[float(s['beat_duration']) for s in spans
                    if float(s['end'])>=bridge[0] and float(s['start'])<=bridge[1]]
            limit=min(POLICY['maximum_gap_seconds'],min(tempos,default=0)*POLICY['maximum_gap_beats'])
            blocked=any(b is None or b[0]<=bridge[1] and b[1]>=bridge[0]
                        for b in blockers.get(item['lane'],[]))
            if (limit>0 and -limit<=lower<=upper<=limit and tail[0]>old_tail[1]
                    and head[0]>edges[pi,'head'][1] and not blocked):
                if 'source_hold_intervals' not in previous:
                    previous['source_hold_intervals']=[dict(previous)]
                    previous['bridged_gaps']=[]
                previous['source_hold_intervals'].append(dict(item))
                previous['bridged_gaps'].append({'song_range':bridge,'gap_range_seconds':[lower,upper],
                                                  'maximum_gap_seconds':limit})
                previous['observed_end_range']=item['observed_end_range']
                edges[pi,'tail']=tail
                del edges[ni,'head'];del edges[ni,'tail']
                continue
        result.append(item)
    for item in result:
        if 'source_hold_intervals' in item:
            merges.append({'note':item['note'],'lane':item['lane'],
                           'source_hold_intervals':item['source_hold_intervals'],
                           'bridged_gaps':item['bridged_gaps']})
    result.extend(dict(o)for o in observations if o['kind']!='hold')
    return result,edges,{'policy':POLICY,'merges':merges}
