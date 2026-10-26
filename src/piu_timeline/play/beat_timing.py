"""Fit natural UCS subdivisions with explicit ambiguity and failure states."""
from collections import defaultdict
from hashlib import sha256
import json
import math
from pathlib import Path

FORMAT={'schema':1,'revision':2,'group_beats':4,'natural_splits':[1,2,3,4,6,8,12,16,24,32,48,64,96,192]}


def fit_grid(targets, uncertainties, bpm, origin, splits=None, phase_uncertainty=0):
    """Choose the smallest explanatory split, never an arbitrarily fine nearest row."""
    for split in splits or FORMAT['natural_splits']:
        step=60/(bpm*split)
        options=[]
        for time,error in zip(targets,uncertainties,strict=True):
            lo=math.ceil((time-error-phase_uncertainty-origin)/step-1e-8)
            hi=math.floor((time+error+phase_uncertainty-origin)/step+1e-8)
            options.append((lo,hi))
        if any(lo>hi for lo,hi in options):continue
        if any(hi>lo for lo,hi in options):
            return {'status':'failed','reason':'ambiguous_beat_rows','split':split}
        rows=[lo for lo,hi in options]
        if any(b-a>.025 and rb<=ra for a,b,ra,rb in zip(targets,targets[1:],rows,rows[1:])):continue
        exact=[origin+row*step for row in rows]
        phase_lo=max([-phase_uncertainty]+[t-e-g for t,e,g in zip(targets,uncertainties,exact)])
        phase_hi=min([phase_uncertainty]+[t+e-g for t,e,g in zip(targets,uncertainties,exact)])
        if phase_lo>phase_hi+1e-8:continue
        return {'status':'restored','split':split,'rows':rows,'targets':exact,'phase_range':[phase_lo,phase_hi]}
    return {'status':'failed','reason':'no_natural_beat_subdivision'}


def reference(data, directory):
    from piu_timeline.charts.data import default_repository, resolve_code
    from piu_timeline.charts.gimmicks import known_origin
    directory=Path(directory);repo=default_repository();registration=directory/'chart-registration.json'
    saved=json.loads(registration.read_text()) if registration.is_file() else {}
    if saved.get('repository'):repo=Path(saved['repository'])
    code=saved.get('index') or (resolve_code(repo,data.get('song')) if (repo/'catalog.json').is_file() else None)
    chart=Path(saved['chart']) if saved.get('chart') else repo/'charts'/str(code)/str(data.get('chart'))/'phoenix/chart.ucs'
    metadata=chart.with_name('metadata.json');timing=repo/'timing'/f'{code}.ucs'
    if not code or not metadata.is_file() or not timing.is_file():
        return {'status':'unavailable','reason':'official_timing_or_chart_identity_missing'}
    meta=json.loads(metadata.read_text());origin=known_origin(data,directory,meta)
    explicit=saved.get('alignment',{})
    if explicit.get('method')=='explicit_song_start' and saved.get('alignment_media')==data.get('media'):
        origin=explicit['song_start_seconds']
    if origin is None:return {'status':'unavailable','reason':'verified_song_alignment_missing','ucs_index':code}
    uncertainty=0 if explicit.get('method')=='explicit_song_start' and saved.get('alignment_media')==data.get('media') else meta.get('alignment',{}).get('uncertainty_seconds',0)
    cached=directory/'chart-policy-alignment.json'
    if cached.is_file():
        saved_alignment=json.loads(cached.read_text())
        if saved_alignment.get('contract',{}).get('media')==data.get('media') and saved_alignment.get('alignment',{}).get('song_start_seconds')==origin:
            uncertainty=saved_alignment['alignment'].get('uncertainty_seconds',uncertainty)
    return {'status':'available','ucs_index':code,'timing':str(timing),'sha256':sha256(timing.read_bytes()).hexdigest(),
            'song_start_seconds':origin,'alignment_uncertainty_seconds':uncertainty}


def current(data,directory):
    return data.get('beat_timing',{}).get('contract')=={'format':FORMAT,'reference':reference(data,directory)}


def apply(data,directory):
    from piu_timeline.charts.ucs import parse
    ref=reference(data,directory);contract={'format':FORMAT,'reference':ref}
    result={'contract':contract,'status':ref['status'],'warnings':[],'groups':[]}
    if ref['status']!='available':
        result['warnings']=[{'lane':0,'reason':'beat_reference_unavailable','check':'timing_reconstruction',
                             'failure_detail':ref['reason'],'observed_points':0,
                             'visible_start_seconds':data.get('start_seconds',0),
                             'visible_end_seconds':data.get('end_seconds',data.get('start_seconds',0))}]
        return {**data,'beat_timing':result}
    doc=parse(Path(ref['timing']).read_text());grid=list(doc.grid());settings={};sections=[]
    for si,section in enumerate(doc.sections):
        settings.update(section.directives)
        start=float(next(t for index,row,t in grid if index==si))
        bpm=float(settings['BPM']);end=start+len(section.rows)*60/(bpm*int(settings['Split']))
        sections.append((start,end,bpm))
    if any(b[0] < a[1]-1e-6 for a,b in zip(sections,sections[1:])):
        raise ValueError('Overlapping UCS timing sections prevent beat reconstruction')
    groups=defaultdict(list);origin=ref['song_start_seconds']
    notes=[dict(n) for n in data['notes']]
    for ni,note in enumerate(notes):
        if note['status']!='estimated':continue
        time=note['target_seconds']-origin
        for si,(lo,hi,bpm) in enumerate(sections):
            if lo<=time<hi:
                groups[(si,math.floor((time-lo)/(FORMAT['group_beats']*60/bpm)))].append(ni);break
        else:groups[(-1,0)].append(ni)
    if not groups:
        result.update(status='failed',warnings=[{'lane':0,'reason':'no_supported_note_targets',
            'check':'timing_reconstruction','observed_points':0,'visible_start_seconds':data.get('start_seconds',0),
            'visible_end_seconds':data.get('end_seconds',data.get('start_seconds',0))}])
        return {**data,'beat_timing':result}
    from piu_timeline.play.beat_phase import fit_phase
    proposals=[]
    for (si,bar),indices in groups.items():
        indices.sort(key=lambda i:notes[i]['target_seconds'])
        group={'notes':indices,'section':si,'beat_group':bar,
               'targets':[notes[i]['target_seconds'] for i in indices],
               'errors':[notes[i]['prediction_uncertainty_seconds'] for i in indices]}
        if si<0:group['invalid']='outside_official_timing_sections'
        else:
            lo,hi,bpm=sections[si];group.update(bpm=bpm,origin=origin+lo)
        proposals.append(group)
    phase=fit_phase(proposals,ref['alignment_uncertainty_seconds'])
    result.update(song_phase_range=phase.get('phase_range'),song_phase_correction_seconds=phase.get('phase'),
                  phase_resolution_seconds=phase.get('resolution_seconds'))
    for group,fit in zip(proposals,phase['fits'],strict=True):
        indices=group['notes']
        result['groups'].append({'notes':indices,'section':group['section'],'beat_group':group['beat_group'],**fit})
        for j,index in enumerate(indices):
            note=notes[index]
            before=note['target_seconds']
            note['video_target_range']=[before-note['prediction_uncertainty_seconds'],before+note['prediction_uncertainty_seconds']]
            note['beat_reconstruction']={k:v for k,v in fit.items() if k not in ('rows','targets')}
            if fit['status']=='failed':
                pts=note.get('points',[])
                result['warnings'].append({'note':index,'lane':note['lane'],'reason':'beat_timing_reconstruction_failed',
                    'check':'timing_reconstruction','failure_detail':fit['reason'],'observed_points':len(pts),
                    'visible_start_seconds':pts[0][0] if pts else note['target_seconds'],
                    'visible_end_seconds':pts[-1][0] if pts else note['target_seconds']})
                note.update(status='excluded',reason='beat_timing_reconstruction_failed',target_seconds=None)
            else:
                target=fit['targets'][j]
                note.update(target_seconds=target,prediction_uncertainty_seconds=max(
                    note['prediction_uncertainty_seconds']+abs(target-before),ref['alignment_uncertainty_seconds']))
    from piu_timeline.play.spacing_checks import spacing_failures
    if len(data.get('layout',{}).get('lanes',[]))>=2:
        spacing=(data['layout']['lanes'][1]['x']-data['layout']['lanes'][0]['x'])*data['analysis_width']
        conflicts=spacing_failures(notes,spacing)
        for conflict in conflicts:
            index=conflict['note'];conflict.update(reason='beat_grid_conflicts_with_spatial_spacing')
            notes[index].update(status='excluded',reason=conflict['reason'],target_seconds=None,
                                 beat_reconstruction={'status':'failed','reason':conflict['reason']})
        result['warnings'].extend(conflicts)
    result['status']='failed' if result['warnings'] else 'restored'
    return {**data,'notes':notes,'beat_timing':result}


def reassociate(data, display_delay_ms):
    """Changed chart times must be associated before reading judgment words."""
    if data['beat_timing']['status'] not in ('restored','failed'):
        return data
    from types import SimpleNamespace
    from piu_timeline.play.analysis import resolve_timing
    from piu_timeline.play.frames import TIME_EPSILON
    events=[{**e,'status':'candidate' if 1<=e['delta']<=10 and e['upper_seconds']-e['lower_seconds']<=.1+TIME_EPSILON else 'excluded'}
            for e in data['combo_events']]
    tracker=SimpleNamespace(finish=lambda:data['notes'],unsupported_intervals=data['unsupported_intervals'])
    updated=resolve_timing(tracker,SimpleNamespace(events=events,observations=[]),display_delay_ms)
    updated['timing_reconstruction']=data['timing_reconstruction']
    return {**data,**updated}
