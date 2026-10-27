"""Reconsider early native words only before fully accounted future hold risk."""
from piu_timeline.play.frames import TIME_EPSILON
from piu_timeline.play.tracking import associate
from piu_timeline.play.holds.input_risk import pre_hold_accounting,cap_extent_spacing,native_body_risk_available
from piu_timeline.play.associations import disputed_refresh,partition

METHOD='strict_judgment_before_accounted_hold'


def interval(match):
    return (match.get('observation_lower_seconds',match.get('combo_lower_seconds')),
            match.get('observation_upper_seconds',match.get('combo_upper_seconds')))


def recover(data,notes,matches,suppressed):
    data=partition({**data,'matches':matches});matches=data['matches']
    if not native_body_risk_available(data):return matches,[]
    assigned={m['note']for m in matches}|{c['note']for c in data.get('miss_candidates',[])}|suppressed
    owned={m.get('judgment_event')for m in matches};guard=2*(data.get('median_frame_interval_seconds')or .017)
    candidates=[];safe={};constraints={};extent=None
    anchors=[(m,interval(m))for m in matches if None not in interval(m)]
    for index,event in enumerate(data.get('judgment_events',[])):
        lo,hi=event['lower_seconds'],event['upper_seconds']
        native=(event.get('detection_status')=='candidate'and event.get('delta',1)==1
                and event.get('label')in('PERFECT','GREAT','GOOD','BAD')and 0<hi-lo<=.1+TIME_EPSILON)
        occupied=index in owned or any(a<=hi+guard and b>=lo-guard for _,(a,b)in anchors)
        candidates.append({**event,'status':'candidate'if native and not occupied else'excluded'})
        if not native or occupied:continue
        lower=max((m['target_seconds']for m,(a,b)in anchors if b<lo),default=-float('inf'))
        upper=min((m['target_seconds']for m,(a,b)in anchors if a>hi),default=float('inf'))
        constraints[index]={i for i,n in enumerate(notes)if n['status']=='estimated'
                            and i not in assigned and lower<n['target_seconds']<upper}
        if event.get('reason')!='possible_hold_or_dense_stack':continue
        if extent is None:
            extent=cap_extent_spacing(data)
            if extent is None:return matches,[]
        proof=pre_hold_accounting(data,lo,hi,extent)
        if proof is not None:safe[index]=proof
    if not safe:return matches,[]
    # All valid unowned word refreshes compete, including those which cannot
    # themselves be recovered. Existing matches keep their identities and bounds.
    eligible=[{**n,'status':'excluded'}if i in assigned else n for i,n in enumerate(notes)]
    proposals=associate(eligible,candidates,display_delay=data.get('display_delay_correction_ms',0)/1000,
                        event_note_constraints=constraints)
    result=list(matches);recovered=[]
    for proposal in proposals:
        index=proposal['note'];event_index=proposal['combo_event']
        if event_index not in safe or notes[index].get('type_status')!='tap'or notes[index].get('note_type')=='hold':continue
        event=data['judgment_events'][event_index];target=notes[index]['target_seconds']
        if disputed_refresh(data,index,[{**event,'source':'judgment','event':event_index}]):continue
        lo,hi=event['lower_seconds'],event['upper_seconds']
        result.append({'note':index,'target_seconds':target,'row_note_count':proposal['row_note_count'],
                       'aggregate_row_count':1,'combo_event':None,'judgment_event':event_index,
                       'evidence_source':'judgment','judgment_label':event['label'],
                       'judgment_label_source':'native_refresh_before_accounted_hold',
                       'observation_lower_seconds':lo,'observation_upper_seconds':hi,
                       'raw_offset_lower_ms':(lo-target)*1000,'raw_offset_upper_ms':(hi-target)*1000,
                       'recovery_method':METHOD,'hold_risk_accounting':safe[event_index]})
        recovered.append(index)
    return result,recovered
