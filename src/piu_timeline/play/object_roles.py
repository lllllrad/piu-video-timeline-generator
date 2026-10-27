"""Interpret configured non-playable artwork before reconstructing note tracks."""
import json
from pathlib import Path

import numpy as np
from piu_timeline.play.object_boundaries import FORMAT as BOUNDARY_FORMAT
from piu_timeline.play.frames import TIME_EPSILON

KIND='decorative_note_art'
FORMAT={'schema':1,'revision':3,'cap_radius_spacing':.5,'boundary_frames':BOUNDARY_FORMAT}


def reference(data,directory):
    """Read chart annotations without aligning, decoding or writing caches."""
    from piu_timeline.charts.data import default_repository,resolve_code
    directory=Path(directory);registration=directory/'chart-registration.json'
    saved=json.loads(registration.read_text())if registration.is_file()else{}
    path=Path(saved['chart']).with_name('metadata.json')if saved.get('chart')else None
    if path is None:
        repo=default_repository()
        code=resolve_code(repo,data.get('song'))if (repo/'catalog.json').is_file()else None
        if code and data.get('chart'):path=repo/'charts'/code/data['chart']/'phoenix/metadata.json'
    metadata=json.loads(path.read_text())if path and path.is_file()else{}
    from piu_timeline.charts.gimmicks import validate_candidates
    candidates=[e for e in validate_candidates(metadata)if e['kind']==KIND and e['review_status']!='rejected']
    return {'format':FORMAT,'metadata_path':str(path)if path else None,'candidates':candidates}


def current(data,directory):
    try:ref=reference(data,directory)
    except (OSError,ValueError,KeyError,TypeError):return False
    artifact=data.get('object_interpretation',{});saved=artifact.get('contract')
    if saved is None:return not ref['candidates']
    if saved!=ref:return False
    if not ref['candidates']:return True
    return (artifact.get('status')=='applied' and (Path(directory)/'object-interpretation.json').is_file()
            and all(any(all(record.get(k)==v for k,v in candidate.items())for record in artifact.get('effects',[]))
                    for candidate in ref['candidates']))


def effects(data):
    return data.get('object_interpretation',{}).get('effects',[])


def ownership(bounds,time,candidates):
    """Only fully contained objects inside the certain time interior are art."""
    owners=[];ambiguous=[]
    for effect in candidates:
        lo,hi=effect['playback_start_seconds'],effect['playback_end_seconds']
        error=effect['boundary_uncertainty_seconds']+effect.get('alignment_uncertainty_seconds',0)
        x,y,w,h=effect['game_image_bounds'];left,top,right,bottom=bounds
        intersects=left<x+w and x<right and top<y+h and y<bottom
        if not intersects or not lo-error<=time<=hi+error:continue
        role=next((r['role']for r in effect.get('source_frame_roles',[])
                   if abs(time-r['playback_seconds'])<=TIME_EPSILON),None)
        if role=='ordinary_candidate':continue
        certain=lo+error<=time<hi-error or role=='decorative_art'
        if certain and x<=left and right<=x+w and y<=top and bottom<=y+h:
            owners.append(effect['id'])
        else:ambiguous.append(effect['id'])
    return owners,ambiguous


def cap_bounds(data,note):
    width,height=data['analysis_width'],data['analysis_height']
    spacing=float(np.median(np.diff([l['x']*width for l in data['layout']['lanes']])))
    radius=FORMAT['cap_radius_spacing']*spacing
    return [note['x']-radius/width,note['y']-radius/height,
            note['x']+radius/width,note['y']+radius/height]


def filter_frames(data,frames,bodies=False):
    """Return a derived view; native files and individual observations stay intact."""
    candidates=effects(data)
    if not candidates:return frames
    result=[]
    for frame in frames:
        kept=[]
        for observation in frame.get('bodies'if bodies else'notes',[]):
            if bodies:
                bounds=observation.get('foreground_bounds')
                if bounds is None:kept.append(observation);continue
                from piu_timeline.play.holds.features import FEATURE_FORMAT
                width=FEATURE_FORMAT['width'];height=round(width*data['game_roi'][3]/data['game_roi'][2])
                bounds=[bounds[0]/width,bounds[1]/height,bounds[2]/width,bounds[3]/height]
            else:bounds=cap_bounds(data,observation)
            owners,_=ownership(bounds,frame['playback_seconds'],candidates)
            if not owners:kept.append(observation)
        result.append({**frame,('bodies'if bodies else'notes'):kept})
    return result


def apply(data,directory,display_delay_ms=0):
    """Replay native candidates with chart object roles before timing or input fits."""
    directory=Path(directory);ref=reference(data,directory)
    artifact={'contract':ref,'status':'not_applicable','effects':[],'observations':[],'warnings':[]}
    if not ref['candidates']:return {**data,'object_interpretation':artifact}
    from piu_timeline.charts.policy import attach_regions
    prepared=attach_regions({k:v for k,v in data.items()if k!='chart_policy'},directory)
    policy=prepared.get('chart_policy',{})
    if policy.get('status')!='applied':
        raise ValueError('Cannot interpret chart artwork: '+str(policy.get('reason','verified alignment unavailable')))
    candidates=[{**e,'alignment_uncertainty_seconds':policy['alignment'].get('uncertainty_seconds',0)}
                for e in policy['gimmick_candidates']if e['kind']==KIND and e['review_status']!='rejected']
    with (directory/'frames.jsonl').open()as stream:frames=[json.loads(line)for line in stream]
    if len(frames)!=data['frame_count']:raise ValueError('Object-role source frame count differs')
    from piu_timeline.play.object_boundaries import prepare as prepare_boundaries
    candidates=[prepare_boundaries(data,directory,e,frames)for e in candidates]
    for frame in frames:
        for index,note in enumerate(frame['notes']):
            owners,ambiguous=ownership(cap_bounds(data,note),frame['playback_seconds'],candidates)
            base={'playback_seconds':frame['playback_seconds'],'source_pts_seconds':frame['source_pts_seconds'],
                  'native_detection':index,'lane':note['lane'],'observation':note}
            if owners:artifact['observations'].append({**base,'role':'decorative_art','effects':owners})
            elif ambiguous:
                artifact['warnings'].append({'reason':'decorative_art_boundary_ambiguous','check':'chart_effect',
                    'lane':note['lane'],'visible_start_seconds':frame['playback_seconds'],
                    'visible_end_seconds':frame['playback_seconds'],'observed_points':1,
                    'source_pts_seconds':[frame['source_pts_seconds']],'effects':ambiguous,
                    'native_detection':index,'observation':note})
    artifact.update(status='applied',effects=candidates)
    (directory/'object-interpretation.json').write_text(json.dumps(artifact)+'\n')
    prepared={**prepared,'object_interpretation':artifact}
    from piu_timeline.play.tracking import NoteTracker,ComboTracker
    from piu_timeline.play.analysis import resolve_timing
    tracker=NoteTracker(data['layout'],data['analysis_width'],data['analysis_height']);combo=ComboTracker()
    for frame in filter_frames(prepared,frames):
        time=frame['playback_seconds'];pts=frame['source_pts_seconds']
        tracker.hold_candidate=frame.get('possible_hold_or_dense_stack',False)
        tracker.update(time,frame['notes'],pts)
        combo.update(time,frame['combo'],frame.get('combo_confidence'),frame.get('combo_read_mode'),pts)
    return {**prepared,**resolve_timing(tracker,combo,display_delay_ms)}


def verify(data):
    """A metadata edit cannot pretend an older object interpretation was applied."""
    active=[e for e in data.get('chart_policy',{}).get('gimmick_candidates',[])
            if e['kind']==KIND and e['review_status']!='rejected']
    saved=effects(data);artifact=data.get('object_interpretation',{})
    warnings=[]
    for effect in active:
        if any(all(record.get(k)==v for k,v in effect.items())for record in saved):continue
        warnings.append({'reason':'decorative_art_interpretation_missing','check':'chart_effect','lane':0,
                         'visible_start_seconds':effect['playback_start_seconds'],
                         'visible_end_seconds':effect['playback_end_seconds'],'observed_points':0,
                         'gimmick_candidate':effect['id']})
    return {**data,'object_interpretation':{**artifact,'warnings':[*artifact.get('warnings',[]),*warnings]}}
