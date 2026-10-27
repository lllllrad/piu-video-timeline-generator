"""Measure a head's outline-to-silhouette offset from retained native pixels."""
from collections import defaultdict
import json

import cv2
import numpy as np

from piu_timeline.play.note_types import cap_envelope, shape

FORMAT={'schema':1,'revision':3,'minimum_frames':8,'minimum_span_seconds':.12,
        'offset_inlier_pixels':1.,'minimum_inlier_fraction':.95,'maximum_median_error_pixels':.5,
        'maximum_offset_spacing':.1,'coordinate_uncertainty_pixels':1.}


def patch_offset(packed, columns, spacing):
    """Only a complete isolated cap can define its outer registration box."""
    color,white,visible,relaxed,valid=np.unpackbits(packed,axis=-1)[...,:columns].astype(bool)
    center=(color.shape[0]-1)/2;cx=(color.shape[1]-1)/2
    if shape(color,white,visible,center,spacing,relaxed,valid)[0]!='tap':return None
    boxes=set()
    for contour in cv2.findContours(white.astype('uint8'),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,w,h=cv2.boundingRect(contour)
        if not (.65*spacing<w<1.25*spacing and .65*spacing<h<1.25*spacing
                and abs(y+h/2-center)<.2*spacing and abs(x+w/2-cx)<.2*spacing):continue
        box=cap_envelope(relaxed,white,(x,y,w,h),spacing)
        if box and valid[box[1]:box[1]+box[3],box[0]:box[0]+box[2]].all():boxes.add(box)
    if len(boxes)!=1:return None
    x,y,w,h=next(iter(boxes));offset=y+h/2-center
    return (float(offset),list((x,y,w,h))) if abs(offset)<=FORMAT['maximum_offset_spacing']*spacing else None


def fit_offset(samples):
    if len(samples)<FORMAT['minimum_frames'] or samples[-1]['time']-samples[0]['time']<FORMAT['minimum_span_seconds']:
        return None
    values=np.array([s['offset_pixels']for s in samples]);offset=float(np.median(values))
    errors=abs(values-offset);inliers=errors<=FORMAT['offset_inlier_pixels']
    stable=(float(inliers.mean())>=FORMAT['minimum_inlier_fraction']
            and float(np.median(errors))<=FORMAT['maximum_median_error_pixels'])
    return {'status':'registered' if stable else 'unresolved','offset_pixels':offset,
            'coordinate_uncertainty_pixels':FORMAT['coordinate_uncertainty_pixels'],
            'inlier_fraction':float(inliers.mean()),'median_error_pixels':float(np.median(errors)),
            'observations':samples,'conflicting_observations':[s for s,keep in zip(samples,inliers,strict=True)if not keep]}


def measure(data,path):
    """Calibrate each observed identity without using timing, grid or input fits."""
    from piu_timeline.play.holds.features import ui_regions
    records=[]
    with np.load(path,allow_pickle=False)as saved:
        masks,times,pts,lanes,ys=(saved[k]for k in ('masks','times','pts','lanes','ys'))
        spacing,columns=float(saved['spacing']),int(saved['columns'])
        by=defaultdict(list)
        for i,(time,lane)in enumerate(zip(times,lanes,strict=True)):by[round(float(time),6),int(lane)].append(i)
        height=data['analysis_height'];receptor=data['layout']['receptor_y']*height
        for ni,note in enumerate(data['notes']):
            samples=[]
            for time,y in note.get('detected_points',note.get('points',[])):
                if not receptor+1.3*spacing<y<data['layout'].get('note_y_max',.95)*height-.8*spacing:continue
                x=data['layout']['lanes'][note['lane']]['x']
                if any(rx<=x<=rx+rw and ry*height-.8*spacing<=y<=(ry+rh)*height+.8*spacing
                       for rx,ry,rw,rh in ui_regions(data['layout'])):continue
                options=sorted((abs(float(ys[i])-y),i)for i in by.get((round(time,6),note['lane']),[]))
                if not options or options[0][0]>1e-5 or len(options)>1 and options[1][0]<1:continue
                i=options[0][1];anchor=patch_offset(masks[i],columns,spacing)
                if anchor is not None:
                    offset,box=anchor
                    # Appearance patches are centered on rounded pixel rows;
                    # tracked outline centers retain their fractional row.
                    patch_shift=round(float(ys[i]))-float(ys[i])
                    offset+=patch_shift
                    if abs(offset)>FORMAT['maximum_offset_spacing']*spacing:continue
                    samples.append({'time':time,'source_pts_seconds':float(pts[i]),
                                    'offset_pixels':offset,'patch_center_shift_pixels':patch_shift,
                                    'outer_bounds_in_patch':box})
            fitted=fit_offset(samples)
            if fitted is not None:records.append({'note':ni,'lane':note['lane'],**fitted})
    warnings=[]
    for record in records:
        uncertain=record['status']=='unresolved'
        samples=record['observations']if uncertain else record['conflicting_observations']
        if not samples:continue
        warnings.append({'note':record['note'],'lane':record['lane'],
                         'reason':'head_registration_unresolved'if uncertain else 'head_registration_observation_conflict',
                         'check':'timing_reconstruction','observed_points':len(samples),
                         'visible_start_seconds':samples[0]['time'],'visible_end_seconds':samples[-1]['time'],
                         'source_pts_seconds':[samples[0]['source_pts_seconds'],samples[-1]['source_pts_seconds']],
                         'offset_pixels':record['offset_pixels'],'inlier_fraction':record['inlier_fraction']})
    return {'format':FORMAT,'trace':'appearance-features.npz','notes':records,'warnings':warnings}


def apply(data,directory,display_delay_ms=0):
    """Register derived coordinates while keeping every original detection/PTS."""
    from piu_timeline.play.appearance import acquire
    if not data.get('media',{}).get('video_streams'):
        return {**data,'head_registration':{'format':FORMAT,'notes':[],'status':'unavailable'}}
    frames=[json.loads(line)for line in (directory/'frames.jsonl').open()]
    path=acquire(data,directory,frames)
    if path is None:return {**data,'head_registration':{'format':FORMAT,'notes':[],'status':'unavailable'}}
    registration=measure(data,path)
    (directory/'head-registration.json').write_text(json.dumps(registration)+'\n')
    accepted={r['note']:r for r in registration['notes']if r['status']=='registered'}
    if not accepted:return {**data,'head_registration':registration}
    from piu_timeline.play.tracking import Track,fit_track
    from piu_timeline.play.shared_timing import restore
    width,height=data['analysis_width'],data['analysis_height']
    spacing=float(np.median(np.diff([l['x']*width for l in data['layout']['lanes']])))
    tracks=[];notes=[]
    for i,original in enumerate(data['notes']):
        raw=original.get('detected_points',original['points']);record=accepted.get(i)
        points=[[t,y+record['offset_pixels']]for t,y in raw]if record else raw
        track=Track(original['lane'],points)
        track.registration_uncertainty_pixels=record['coordinate_uncertainty_pixels']if record else 0
        note=fit_track(track,data['layout']['receptor_y']*height,spacing,layout=data['layout'])
        if record:note.update(detected_points=raw,head_registration={k:v for k,v in record.items()if k not in ('observations','conflicting_observations')})
        for key in ('tracking_method','source_track_fragments'):
            if key in original:note[key]=original[key]
        tracks.append(track);notes.append(note)
    motion,timing=restore(notes,tracks,data['scroll_motion']['samples'],data['layout'],width,height)
    for i,original in enumerate(data['notes']):
        if original.get('reason')=='duplicate_head_component':
            notes[i].update(status='excluded',reason=original['reason'],duplicate_of=original['duplicate_of'])
    from types import SimpleNamespace
    from piu_timeline.play.analysis import resolve_timing
    from piu_timeline.play.frames import TIME_EPSILON
    events=[{**e,'status':'candidate'if 1<=e['delta']<=10 and e['upper_seconds']-e['lower_seconds']<=.1+TIME_EPSILON else 'excluded'}for e in data['combo_events']]
    tracker=SimpleNamespace(finish=lambda:notes,motion=motion,timing_reconstruction=timing,unsupported_intervals=data['unsupported_intervals'])
    updated=resolve_timing(tracker,SimpleNamespace(events=events,observations=[]),display_delay_ms)
    return {**data,**updated,'head_registration':registration}
