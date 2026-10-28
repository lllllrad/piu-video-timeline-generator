"""Prepare source-bound image risk proofs before TypeScript row recovery."""
from piu_timeline.derived import call,recovery_input
from piu_timeline.play.holds.input_risk import pre_hold_accounting,cap_extent_spacing,native_body_risk_available
METHOD='strict_judgment_before_accounted_hold'


def interval(match):
    return (match.get('observation_lower_seconds',match.get('combo_lower_seconds')),
            match.get('observation_upper_seconds',match.get('combo_upper_seconds')))


def prepare_risk_proofs(data):
    if not native_body_risk_available(data):return {}
    eligible=[(i,e)for i,e in enumerate(data.get('judgment_events',[]))
              if e.get('detection_status')=='candidate'and e.get('delta',1)==1
              and e.get('label')in('PERFECT','GREAT','GOOD','BAD')
              and e.get('reason')=='possible_hold_or_dense_stack'
              and 0<e['upper_seconds']-e['lower_seconds']<=.1+1e-6]
    if not eligible:return {}
    extent=cap_extent_spacing(data)
    if extent is None:return {}
    result={}
    for i,e in eligible:
        proof=pre_hold_accounting(data,e['lower_seconds'],e['upper_seconds'],extent)
        if proof is not None:result[i]=proof
    return result


def recover(data,notes,matches,suppressed):
    return tuple(call('labels.recoverPreHold',recovery_input(data),notes,matches,suppressed,prepare_risk_proofs(data)))
