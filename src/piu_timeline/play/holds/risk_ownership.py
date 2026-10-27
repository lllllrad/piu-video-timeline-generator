"""Account every native proximity cause before a measured future hold."""
from piu_timeline.play.holds.risk_cache import context
from piu_timeline.play.holds.risk_evidence import FORMAT


def account_interval(data,interval,guards,word_hi):
    evidence=data.get('body_risk_evidence',{})
    if evidence.get('status')!='available' or evidence.get('verified_native_flags')is not True:return None
    contract=evidence.get('contract',{})
    if contract.get('format')!=FORMAT:return None
    if any(contract.get(k)!=v for k,v in context(data).items()):return None
    frames=[f for f in evidence['frames']if interval['start_seconds']<=f['playback_seconds']<=interval['end_seconds']]
    if not frames or frames[0]['playback_seconds']!=interval['start_seconds']or frames[-1]['playback_seconds']!=interval['end_seconds']:return None
    holds={h['id']:(h,g)for h,g in guards};seen=set();records=[]
    for frame in frames:
        if not frame['causes']:return None
        current=set()
        for cause in frame['causes']:
            identifier=cause.get('owner_hold')
            if identifier not in holds or cause.get('candidate_holds')!=[identifier]:return None
            hold,guard=holds[identifier]
            if word_hi>=hold['start_range'][0]-guard:return None
            # Later frames may reach the receptor, but their first measured
            # component must still be entirely below it, moving upward.
            if identifier not in seen and cause.get('state')!='approaching':return None
            current.add(identifier)
        seen.update(current)
        records.append({'playback_seconds':frame['playback_seconds'],
                        'source_pts_seconds':frame['source_pts_seconds'],'causes':frame['causes']})
    return {'method':FORMAT['ownership'],'holds':sorted(seen),'frames':records}
