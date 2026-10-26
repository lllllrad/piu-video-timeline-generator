"""Measure bounded speed transitions from retained registered peer displacement."""
from collections import Counter, defaultdict
from bisect import bisect_left, bisect_right

import numpy as np

FORMAT={'schema':1,'revision':2,'window_seconds':.3,'confirmation_seconds':.45,'minimum_independent_fraction':.7}


def window(samples, spacing):
    if len(samples)<12 or samples[-1]['time']-samples[0]['time']<.24:
        return None,'insufficient_native_span'
    independent=sum(s['support']>=2 and s['lanes']>=2 for s in samples)
    if independent/len(samples)<FORMAT['minimum_independent_fraction']:
        return None,'insufficient_independent_peers'
    times=np.array([s['time']-samples[0]['time'] for s in samples]);phase=np.array([s['phase'] for s in samples])
    speed,intercept=np.polyfit(times,phase,1)
    if speed<=spacing or phase[-1]-phase[0]<.5*spacing:
        return None,'stationary_or_small_displacement'
    errors=phase-(speed*times+intercept);residual=float(np.sqrt(np.mean(errors**2)))
    cadence=float(np.median(np.diff(times)));limit=max(.75,.55*cadence*speed+.5)
    if residual>limit:
        return None,'nonlinear_or_inconsistent_displacement'
    spread=float(np.sum((times-times.mean())**2))
    error=max(3*float(np.sqrt(np.dot(errors,errors)/max(1,len(times)-2)/spread)),1.5/times[-1])
    if error>.15*speed:
        return None,'speed_uncertainty_too_wide'
    return {'start':samples[0]['time'],'end':samples[-1]['time'],'speed':float(speed),'error':error,
            'intercept':float(intercept),'residual':residual,'position_limit':float(limit),
            'source_pts_seconds':[samples[0]['source_pts'],samples[-1]['source_pts']],
            'frames':len(samples),'independent_frames':independent,
            'median_peer_heads':float(np.median([s['support'] for s in samples]))},None


def transition(before, after, samples, spacing):
    ratio=after['speed']/before['speed']
    bounds=[(after['speed']-after['error'])/(before['speed']+before['error']),
            (after['speed']+after['error'])/(before['speed']-before['error'])]
    if bounds[0]<=1<=bounds[1] or abs(ratio-1)<.15:
        return None
    # Both windows share a registered phase origin. Their intersection must
    # lie in the observed gap, rather than inventing a new phase offset.
    gap=after['start']-before['end']
    if not -1e-6<=gap<=.3+1e-6:
        return None
    origin=before['start'];relative=after['start']-origin
    crossing=(before['intercept']-after['intercept']+after['speed']*relative)/(after['speed']-before['speed'])
    time=origin+crossing
    cadence=float(np.median(np.diff([s['time'] for s in samples])))
    if not before['end']-cadence<=time<=after['start']+cadence:
        return None
    middle=[s for s in samples if before['end']<=s['time']<=after['start']]
    phase=before['intercept']+before['speed']*crossing
    residuals=[abs(s['phase']-(phase+(s['time']-time)*(before['speed'] if s['time']<time else after['speed']))) for s in middle]
    if residuals and max(residuals)>max(before['position_limit'],after['position_limit'])+1.5:
        return None
    return {'start_seconds':before['start'],'end_seconds':after['end'],
            'transition_range_seconds':[before['end'],after['start']],
            'estimated_transition_seconds':float(time),'speed_multiplier':float(ratio),'speed_ratio_range':bounds,
            'before':before,'after':after,'lane_spacing_pixels':spacing,
            'reference_speed_lane_spacings_per_second':before['speed']/spacing,
            'result_speed_lane_spacings_per_second':after['speed']/spacing}


def estimate(data):
    motion=data.get('scroll_motion',{})
    if motion.get('format',{}).get('method')!='registered_peer_displacement':
        return {'format':FORMAT,'status':'unavailable','reason':'registered_native_displacement_required','transitions':[]}
    lanes=data.get('layout',{}).get('lanes',[])
    if len(lanes)<2:
        return {'format':FORMAT,'status':'unavailable','reason':'lane_geometry_required','transitions':[]}
    spacing=float(np.median(np.diff([lane['x']*data['analysis_width'] for lane in lanes])))
    chunks=defaultdict(list)
    for sample in motion['samples']:chunks[sample['chunk']].append(sample)
    proposals=[];rejected=Counter();accepted=0
    for chunk,samples in chunks.items():
        times=[s['time'] for s in samples];windows=[]
        for i in range(0,len(samples)-11,3):
            end=bisect_right(times,times[i]+FORMAT['window_seconds']+1e-6)
            fitted,reason=window(samples[i:end],spacing)
            if fitted:windows.append(fitted);accepted+=1
            else:rejected[reason]+=1
        starts=[w['start'] for w in windows]
        for before in windows:
            first=bisect_left(starts,before['end']-1e-6)
            for after in windows[first:]:
                if after['start']-before['end']>.3+1e-6:break
                proposal=transition(before,after,samples,spacing)
                if proposal:proposals.append({**proposal,'motion_chunk':chunk})
    # Prefer the narrowest native boundary bracket for overlapping proposals.
    proposals.sort(key=lambda p:(p['transition_range_seconds'][1]-p['transition_range_seconds'][0],
                                 p['speed_ratio_range'][1]-p['speed_ratio_range'][0]))
    kept=[]
    for p in proposals:
        lo,hi=p['transition_range_seconds']
        if any(p['motion_chunk']==q['motion_chunk']
               and lo<=q['transition_range_seconds'][1]+.05 and hi>=q['transition_range_seconds'][0]-.05
               and p['speed_ratio_range'][0]<=q['speed_ratio_range'][1] and p['speed_ratio_range'][1]>=q['speed_ratio_range'][0]
               for q in kept):continue
        kept.append(p)
    kept.sort(key=lambda p:p['estimated_transition_seconds'])
    for i,p in enumerate(kept):
        reasons=[]
        # A short-window difference can be capture jitter or a biased local
        # registration. Independent longer flanks must sustain the same change.
        samples=chunks[p['motion_chunk']];t=p['before']['end'];u=p['after']['start']
        before,_=window([s for s in samples if t-FORMAT['confirmation_seconds']-1e-6<=s['time']<=t+1e-6],spacing)
        after,_=window([s for s in samples if u-1e-6<=s['time']<=u+FORMAT['confirmation_seconds']+1e-6],spacing)
        confirmed=False
        if before and after and min(before['end']-before['start'],after['end']-after['start'])>=.4-1e-6:
            ratio=after['speed']/before['speed']
            bounds=[float((after['speed']-after['error'])/(before['speed']+before['error'])),
                    float((after['speed']+after['error'])/(before['speed']-before['error']))]
            confirmed=(not bounds[0]<=1<=bounds[1] and abs(ratio-1)>=.15
                       and p['speed_ratio_range'][0]<=ratio<=p['speed_ratio_range'][1])
            p['long_flank_confirmation']={'before':before,'after':after,'speed_multiplier':float(ratio),
                                          'speed_ratio_range':bounds,'consistent':bool(confirmed)}
        if not confirmed:reasons.append('longer_native_flanks_do_not_confirm_change')
        if (p['speed_ratio_range'][1]-p['speed_ratio_range'][0])/p['speed_multiplier']>.15:
            reasons.append('ratio_uncertainty_too_wide')
        if p['transition_range_seconds'][1]-p['transition_range_seconds'][0]>.1+1e-6:
            reasons.append('transition_bracket_too_wide')
        if min(p['before']['median_peer_heads'],p['after']['median_peer_heads'])<3:
            reasons.append('fewer_than_three_peer_heads')
        if any(j!=i and abs(q['estimated_transition_seconds']-p['estimated_transition_seconds'])<.6
               for j,q in enumerate(kept)):
            reasons.append('nearby_changes_need_complex_motion_review')
        p.update(auto_recordable=not reasons,review_reasons=reasons)
    return {'format':FORMAT,'status':'measured' if kept else 'no_verified_speed_transition',
            'transitions':kept,'stable_windows':accepted,'rejected_windows':dict(rejected),
            'semantics':'Upward-positive screen velocity. Ratios are measured, not forced to simple subdivisions; absence of a proposal does not clear warnings.'}
