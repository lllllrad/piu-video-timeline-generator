"""Fit natural UCS subdivisions with explicit ambiguity and failure states."""
from collections import defaultdict
from hashlib import sha256
import json
import math
import subprocess
from pathlib import Path
from piu_timeline.play.beats.coordinates import FORMAT as COORDINATE_FORMAT
from piu_timeline.play.beats.chords import FORMAT as CHORD_FORMAT
from piu_timeline.play.beats.domains import FORMAT as DOMAIN_FORMAT

from piu_timeline.charts.ucs import NATURAL_SPLITS

FORMAT={'schema':1,'revision':8,'group_beats':4,'natural_splits':list(NATURAL_SPLITS),
        'phase_selection':'native_spacing_constrained','independent_coordinates':COORDINATE_FORMAT,'native_chords':CHORD_FORMAT,'native_row_domains':DOMAIN_FORMAT}


def fit_grid(targets, uncertainties, bpm, origin, splits=None, phase_uncertainty=0,native_chords=(),native_coordinates=()):
    """Choose the smallest explanatory split, never an arbitrarily fine nearest row."""
    incompatible=None
    for split in splits or FORMAT['natural_splits']:
        step=60/(bpm*split)
        options=[]
        for time,error in zip(targets,uncertainties,strict=True):
            lo=math.ceil((time-error-phase_uncertainty-origin)/step-1e-8)
            hi=math.floor((time+error+phase_uncertainty-origin)/step+1e-8)
            options.append((lo,hi))
        if any(lo>hi for lo,hi in options):continue
        from piu_timeline.play.beats.chords import constrain
        original_options=options
        options,proofs=constrain(options,step,native_chords)
        if any(lo>hi for lo,hi in options):incompatible='native_chord_domains_incompatible';continue
        from piu_timeline.play.beats.domains import constrain as constrain_coordinates
        options,coordinate_proofs=constrain_coordinates(options,step,origin,native_coordinates)
        if any(lo>hi for lo,hi in options):incompatible='native_coordinate_domains_incompatible';continue
        rows=[lo if lo==hi else None for lo,hi in options]
        known=[(time,row)for time,row in zip(targets,rows)if row is not None]
        if any(b-a>.025 and rb<=ra for (a,ra),(b,rb)in zip(known,known[1:])):continue
        constraints={**({'native_chord_constraints':proofs}if proofs else {}),
                     **({'native_coordinate_constraints':coordinate_proofs}if coordinate_proofs else {}),
                     **({'unconstrained_row_domains':original_options}if proofs or coordinate_proofs else {})}
        if any(row is None for row in rows):
            result={'status':'failed','reason':'ambiguous_beat_rows','split':split,'row_domains':options,**constraints}
            # A fixed common phase can establish some rows without resolving
            # every other head. Unknown phase requires the common-phase search.
            if known and phase_uncertainty==0:
                result.update(status='partial',rows=rows,targets=[origin+r*step if r is not None else None for r in rows],
                              phase_range=[0,0],unresolved_indices=[i for i,row in enumerate(rows)if row is None])
            return result
        exact=[origin+row*step for row in rows]
        phase_lo=max([-phase_uncertainty]+[t-e-g for t,e,g in zip(targets,uncertainties,exact)])
        phase_hi=min([phase_uncertainty]+[t+e-g for t,e,g in zip(targets,uncertainties,exact)])
        if phase_lo>phase_hi+1e-8:continue
        return {'status':'restored','split':split,'rows':rows,'targets':exact,'phase_range':[phase_lo,phase_hi],
                **constraints}
    return {'status':'failed','reason':incompatible or'no_natural_beat_subdivision'}


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
    if origin is None:return {'status':'unavailable','reason':'verified_song_alignment_missing','ucs_index':code,
                              'metadata_path':str(metadata),'timing':str(timing),'sha256':sha256(timing.read_bytes()).hexdigest()}
    uncertainty=0 if explicit.get('method')=='explicit_song_start' and saved.get('alignment_media')==data.get('media') else meta.get('alignment',{}).get('uncertainty_seconds',0)
    cached=directory/'chart-policy-alignment.json'
    if cached.is_file():
        saved_alignment=json.loads(cached.read_text())
        if saved_alignment.get('contract',{}).get('media')==data.get('media') and saved_alignment.get('alignment',{}).get('song_start_seconds')==origin:
            uncertainty=saved_alignment['alignment'].get('uncertainty_seconds',uncertainty)
    catalogue=repo/'catalog.json'
    entries=json.loads(catalogue.read_text()).get('songs',[]) if catalogue.is_file() else []
    bpm=next((entry.get('bpm') for entry in entries if entry['index']==code),None)
    return {'status':'available','ucs_index':code,'constant_tempo_bpm':bpm,'timing':str(timing),'sha256':sha256(timing.read_bytes()).hexdigest(),
            'song_start_seconds':origin,'alignment_uncertainty_seconds':uncertainty}


def current(data,directory):
    return data.get('beat_timing',{}).get('contract')=={'format':FORMAT,'reference':reference(data,directory)}



def prepare_reference(data,directory):
    """Prepare audio-only alignment before beat inference, without policy gates.

    Reference/current checks remain read-only. Failed preparation is retained
    as a diagnostic on this build, not retried by a cache-current check.
    """
    ref=reference(data,directory)
    if ref.get('reason')!='verified_song_alignment_missing':return None
    from piu_timeline.charts.audio import prepare_alignment
    try:
        prepare_alignment(data,Path(directory),json.loads(Path(ref['metadata_path']).read_text()),ref['ucs_index'])
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        return {'status':'failed','reason':str(error)}
    return {'status':'prepared','method':'reference_audio_translation'}


def spacing_supported_notes(notes,groups,fits,spacing,motion,coordinate_support=None,chords=()):
    """Score a candidate using the same native spacing constraints as its output."""
    from piu_timeline.play.spacing_checks import spacing_failures
    candidate=[dict(note)for note in notes]
    for group,fit in zip(groups,fits,strict=True):
        for j,index in enumerate(group['notes']):
            if fit['status']in('restored','partial')and fit['targets'][j]is not None:
                candidate[index]['target_seconds']=fit['targets'][j]
            else:candidate[index]['status']='excluded'
    rejected={w['note']for w in spacing_failures(candidate,spacing,motion,coordinate_support)}
    from piu_timeline.play.beats.chords import conflicts
    rejected.update(w['note']for w in conflicts(candidate,chords))
    return tuple(i for i,note in enumerate(candidate)if note['status']=='estimated'and i not in rejected)


def apply(data,directory):
    from piu_timeline.charts.ucs import parse, constant_tempo
    preparation=prepare_reference(data,directory)
    ref=reference(data,directory);contract={'format':FORMAT,'reference':ref}
    result={'contract':contract,'status':ref['status'],'warnings':[],'groups':[]}
    if preparation:result['reference_preparation']=preparation
    if ref['status']!='available':
        result['warnings']=[{'lane':0,'reason':'beat_reference_unavailable','check':'timing_reconstruction',
                             'failure_detail':preparation['reason'] if preparation and preparation['status']=='failed' else ref['reason'],'observed_points':0,
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
    origin=ref['song_start_seconds']
    latest=max((n['target_seconds']+n['prediction_uncertainty_seconds']-origin
                for n in data['notes'] if n['status']=='estimated'),default=sections[-1][1])
    if latest>=sections[-1][1] and constant_tempo(doc,ref.get('constant_tempo_bpm')):
        lo,hi,bpm=sections[-1];step=60/(bpm*int(settings['Split']))
        end=lo+(math.ceil((latest-lo)/step)+1)*step
        if end-hi>900:raise ValueError('Timing extension exceeds supported song duration')
        sections[-1]=(lo,end,bpm)
        result['timing_extension']={'basis':'constant_tempo_catalogue_and_template',
            'original_end_seconds':hi,'extended_end_seconds':end,'review_required':True}
    groups=defaultdict(list)
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
    from piu_timeline.play.beats.phase import fit_phase
    spacing=None
    if len(data.get('layout',{}).get('lanes',[]))>=2:
        spacing=(data['layout']['lanes'][1]['x']-data['layout']['lanes'][0]['x'])*data['analysis_width']
    from piu_timeline.play.beats.chords import prepare as prepare_chords,conflicts as chord_conflicts
    chords=prepare_chords(data,spacing)if spacing else []
    result['native_chords']=chords
    proposals=[]
    for (si,bar),indices in groups.items():
        indices.sort(key=lambda i:notes[i]['target_seconds'])
        group={'notes':indices,'section':si,'beat_group':bar,
               'targets':[notes[i]['target_seconds'] for i in indices],
               'errors':[notes[i]['prediction_uncertainty_seconds'] for i in indices]}
        positions={index:j for j,index in enumerate(indices)}
        group['native_chords']=[{**p,'indices':[positions[i]for i in p['peer_notes']]}
                                for p in chords if all(i in positions for i in p['peer_notes'])]
        if si<0:group['invalid']='outside_official_timing_sections'
        else:
            lo,hi,bpm=sections[si];group.update(bpm=bpm,origin=origin+lo)
        proposals.append(group)
    from piu_timeline.play.beats.coordinates import prepare
    coordinate_support=prepare(data,spacing)if spacing else None
    if coordinate_support:
        for group in proposals:
            positions={index:j for j,index in enumerate(group['notes'])}
            group['native_coordinates']=[{'chunk':number,'heads':{positions[i]:{**head,'native_note':i} for i,head in heads.items()
                                         if i in positions}}for number,heads in coordinate_support['chunks'].items()
                                         if sum(i in positions for i in heads)>=DOMAIN_FORMAT['measurement_limits']['minimum_references']+1]
    validate=(lambda fits:spacing_supported_notes(notes,proposals,fits,spacing,data.get('scroll_motion'),coordinate_support,chords))if spacing else None
    phase=fit_phase(proposals,ref['alignment_uncertainty_seconds'],consistent_notes=validate)
    result.update(song_phase_range=phase.get('phase_range'),song_phase_correction_seconds=phase.get('phase'),
                  phase_resolution_seconds=phase.get('resolution_seconds'),
                  phase_trials=phase.get('phase_trials',[]),phase_consistent_notes=phase.get('consistent_notes'))
    for group,fit in zip(proposals,phase['fits'],strict=True):
        indices=group['notes']
        result['groups'].append({'notes':indices,'section':group['section'],'beat_group':group['beat_group'],**fit})
        for j,index in enumerate(indices):
            note=notes[index]
            before=note['target_seconds']
            note['video_target_range']=[before-note['prediction_uncertainty_seconds'],before+note['prediction_uncertainty_seconds']]
            accepted=fit['status']in('restored','partial')and fit['targets'][j]is not None
            note['beat_reconstruction']={'status':'restored'if accepted else'failed',
                'group_index':len(result['groups'])-1,**{k:fit[k]for k in ('split','phase_range')if k in fit},
                **({'reason':fit['reason']}if not accepted else{})}
            if not accepted:
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
        result['coordinate_checks']=[]
        conflicts=spacing_failures(notes,spacing,data.get('scroll_motion'),coordinate_support,result['coordinate_checks'])
        for conflict in conflicts:
            index=conflict['note'];conflict.update(reason='beat_grid_conflicts_with_spatial_spacing')
            notes[index].update(status='excluded',reason=conflict['reason'],target_seconds=None,
                                 beat_reconstruction={**notes[index]['beat_reconstruction'],'status':'failed','reason':conflict['reason']})
        result['warnings'].extend(conflicts)
    conflicts=chord_conflicts(notes,chords)
    for conflict in conflicts:
        notes[conflict['note']].update(status='excluded',reason=conflict['reason'],target_seconds=None,
                                     beat_reconstruction={**notes[conflict['note']]['beat_reconstruction'],'status':'failed','reason':conflict['reason']})
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
