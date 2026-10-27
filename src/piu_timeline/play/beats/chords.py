"""Constrain beat domains with independently measured concurrent cap positions."""
from collections import defaultdict
from itertools import combinations

import numpy as np

FORMAT={'schema':1,'revision':1,'minimum_frames':4,'minimum_span_seconds':.065,
        'maximum_gap_pixels':1.,'maximum_motion_residual_pixels':1.5,
        'minimum_displacement_spacing':.8,'coordinate_error_pixels':1.}


def prepare(data,spacing):
    """Use native measured centers only, never target times or input evidence."""
    at=defaultdict(list)
    for record in data.get('head_registration',{}).get('notes',[]):
        if record.get('coordinate_method')!='native_cap_measurements':continue
        if record.get('coordinate_uncertainty_pixels',float('inf'))>FORMAT['coordinate_error_pixels']:continue
        index=record['note'];note=data['notes'][index];points=dict(note['points'])
        for sample in record['observations']:
            time=sample['time']
            if time in points:at[time].append((index,note['lane'],points[time],sample['source_pts_seconds']))
    pairs=defaultdict(list)
    for time,points in sorted(at.items()):
        if max(p[3]for p in points)-min(p[3]for p in points)>1e-6:
            raise ValueError('Native cap measurements disagree on source PTS')
        for a,b in combinations(sorted(points),2):
            if a[1]!=b[1]and abs(a[3]-b[3])<=1e-6:
                pairs[a[0],b[0]].append((time,a[2],b[2],a[3]))
    result=[]
    for (a,b),samples in sorted(pairs.items()):
        if (len(samples)<FORMAT['minimum_frames']or samples[-1][0]-samples[0][0]<FORMAT['minimum_span_seconds']
                or len({s[3]for s in samples})!=len(samples)):continue
        gap=max(abs(s[1]-s[2])for s in samples)
        if gap>FORMAT['maximum_gap_pixels']:continue
        time=np.array([s[0]-samples[0][0]for s in samples])
        y=np.array([(s[1]+s[2])/2 for s in samples]);velocity,intercept=np.polyfit(time,y,1)
        error=float(max(abs(y-velocity*time-intercept)))
        displacement=float(y[0]-y[-1])
        if (displacement<FORMAT['minimum_displacement_spacing']*spacing
                or error>FORMAT['maximum_motion_residual_pixels']):continue
        lower=(displacement-2*FORMAT['coordinate_error_pixels'])/float(time[-1])
        if lower<=0:continue
        result.append({'peer_notes':[a,b],'observed_points':len(samples),'maximum_gap_pixels':gap,
                       'visible_start_seconds':samples[0][0],'visible_end_seconds':samples[-1][0],
                       'source_pts_seconds':[s[3]for s in samples],
                       'minimum_velocity_pixels_per_second':lower,'maximum_motion_residual_pixels':error})
    return result


def constrain(domains,step,constraints):
    """Intersect equality domains only when distinct rows are pixel-resolvable."""
    parents=list(range(len(domains)));used=[]
    def root(i):
        while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
        return i
    threshold=FORMAT['maximum_gap_pixels']+2*FORMAT['coordinate_error_pixels']
    for constraint in constraints:
        if step*constraint['minimum_velocity_pixels_per_second']<=threshold:continue
        a,b=constraint['indices'];parents[root(a)]=root(b);used.append(constraint)
    groups=defaultdict(list)
    for i in range(len(domains)):groups[root(i)].append(i)
    result=list(domains)
    for members in groups.values():
        domain=max(domains[i][0]for i in members),min(domains[i][1]for i in members)
        for i in members:result[i]=domain
    return result,used


def conflicts(notes,constraints):
    """Cross-group assignments must also agree with the measured concurrency."""
    result=[];threshold=FORMAT['maximum_gap_pixels']+2*FORMAT['coordinate_error_pixels']
    for proof in constraints:
        a,b=proof['peer_notes']
        if any(notes[i]['status']!='estimated'for i in (a,b)):continue
        distance=abs(notes[a]['target_seconds']-notes[b]['target_seconds'])*proof['minimum_velocity_pixels_per_second']
        if distance<=threshold:continue
        for i in (a,b):
            result.append({**proof,'note':i,'lane':notes[i]['lane'],'check':'timing_reconstruction',
                           'reason':'beat_grid_conflicts_with_native_chord',
                           'reconstructed_minimum_gap_pixels':distance,'maximum_compatible_gap_pixels':threshold})
    return result
