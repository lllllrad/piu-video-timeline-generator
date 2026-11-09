"""Persist independently reusable coordinate output before musical inference."""
from hashlib import sha256
import json

FORMAT={'schema':3,'producer':'coordinates_without_clocks_or_associations'}
IDENTITY=('media','game_roi','start_seconds','end_seconds','player','participant_slots',
          'analysis_width','analysis_height','layout','native_frame_format')


def fingerprint(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def identity(data):
    return {**{key:data.get(key)for key in IDENTITY},
            'skin_detector':data.get('skin_detector',{}).get('contract'),
            'coordinate_contract':{key:value for key,value in data.get('timing_format',{}).items()
                if key not in ('native_clock','shared_motion','counter_reader','counter_revision','time_epsilon_seconds')}}


def paths(value,before,after):
    if isinstance(value,str)and value.startswith(before):return after+value[len(before):]
    if isinstance(value,list):return [paths(v,before,after)for v in value]
    if isinstance(value,tuple):return [paths(v,before,after)for v in value]
    if isinstance(value,dict):return {k:paths(v,before,after)for k,v in value.items()}
    return value


def save_coordinates(data,directory):
    from piu_timeline.derived import call
    fields=('notes','frame_timeline','head_registration','analysis_width','analysis_height','layout','start_seconds','end_seconds')
    source=call('stageCoordinates.capture',{k:data[k]for k in fields if k in data},str(directory.resolve())+'/')
    payload={'format':FORMAT,'identity':identity(data),'output':source}
    payload=paths(payload,str(directory.resolve())+'/', '@segment/')
    digest=fingerprint(payload)
    destination=directory/'coordinates.json'
    temporary=directory/'coordinates.build.json'
    temporary.write_text(json.dumps({**payload,'fingerprint':digest},ensure_ascii=False)+'\n')
    temporary.replace(destination)
    return {**data,'coordinate_stage':{'format':FORMAT,'fingerprint':digest},'_coordinate_source':source}


def load_coordinates(data,directory):
    """Missing legacy output requires refit; contradictory saved output is an error."""
    expected=data.get('coordinate_stage')
    if not expected or expected.get('format')!=FORMAT:return None
    path=directory/'coordinates.json'
    if not path.is_file():return None
    payload=json.loads(path.read_text());digest=payload.pop('fingerprint',None)
    if digest!=expected.get('fingerprint')or fingerprint(payload)!=digest:
        raise ValueError('Stored coordinate-stage fingerprint does not match its analysis')
    restored=paths(payload,'@segment/',str(directory.resolve())+'/')
    if restored.get('format')!=FORMAT or restored.get('identity')!=identity(data):return None
    result={k:v for k,v in data.items()if k not in ('conflicted_matches','association_view_format')}
    from piu_timeline.derived import call
    coordinates=call('stageCoordinates.materialize',restored['output'])
    return {**result,**coordinates,'_coordinate_source':restored['output']}


def physical_timing(data,directory):
    """Run or reuse physical timing from the completed coordinate artifact only."""
    from piu_timeline.derived import call
    from piu_timeline.play.analysis import TIMING_FORMAT
    timed=call('physicalTiming.saved',data['_coordinate_source'],str(directory.resolve()))
    composed=call('physicalTiming.materialize',timed)
    return {**data,**composed,'timing_format':TIMING_FORMAT,'_timing_source':timed}


def execute(directory,name,compute,outputs=()):
    """Expose an actual calculation boundary, including failed work before publication."""
    import time
    from piu_timeline.play.observations.artifacts import save_input
    path=directory.parent/(directory.name+'.pipeline-status.json')
    if directory.is_dir():path=directory/'pipeline-status.json'
    state=json.loads(path.read_text())if path.is_file()else {'schema':1,'stages':{}}
    record={'status':'running','started_seconds':time.time(),'outputs':list(outputs)}
    state['stage']=name;state['status']='running';state['stage_status']='running';state['stages'][name]=record
    save_input(path,state)
    print(f'Analysis stage: {name}',flush=True)
    try:
        result=compute()
        for output in outputs:
            if not (directory/output).is_file():raise ValueError(f'{name} did not produce {output}')
    except BaseException as error:
        if path.is_file():state=json.loads(path.read_text());state['stages'][name]=record
        state['stage']=name
        record.update(status='failed',error=type(error).__name__+': '+str(error),finished_seconds=time.time())
        state['status']='failed';state['stage_status']='failed';save_input(path,state)
        raise
    if path.parent!=directory and directory.is_dir():
        path.unlink(missing_ok=True);path=directory/'pipeline-status.json'
    if path.is_file():state=json.loads(path.read_text());state['stages'][name]=record
    state['stage']=name
    record.update(status='complete',finished_seconds=time.time())
    state['status']='running';state['stage_status']='complete';save_input(path,state)
    return result


def observation_context(data):
    """Retain acquisition metadata/cache identities, not a previous interpretation."""
    downstream={'notes','matches','conflicted_matches','deferred_matches','miss_candidates',
                'coverage','excluded_notes','scroll_motion','timing_reconstruction',
                'head_registration','beat_timing','coordinate_stage','visual_channels',
                'hold_analysis','association_view_format','judgment_events'}
    return {k:v for k,v in data.items()if k not in downstream and not k.startswith('_')}


def publish(pending,final):
    """Publish completed stages atomically; only publication sets overall success."""
    import time
    from uuid import uuid4
    from piu_timeline.storage import relocate_evidence
    from piu_timeline.play.observations.artifacts import save_input
    state=json.loads((pending/'pipeline-status.json').read_text())
    record={'status':'running','started_seconds':time.time(),'outputs':['report.html']}
    state.update(stage='publication',status='running',stage_status='running')
    state['stages']['publication']=record;save_input(pending/'pipeline-status.json',state)
    backup=final.with_name(f'{final.name}.previous-{uuid4().hex[:8]}')
    try:
        relocate_evidence(pending,final)
        if final.exists():final.rename(backup)
        pending.rename(final)
    except BaseException as error:
        if backup.exists()and not final.exists():backup.rename(final)
        record.update(status='failed',finished_seconds=time.time(),error=type(error).__name__+': '+str(error))
        state.update(status='failed',stage_status='failed');save_input(pending/'pipeline-status.json',state)
        raise
    record.update(status='complete',finished_seconds=time.time())
    state.update(status='published',stage_status='complete');save_input(final/'pipeline-status.json',state)
    if backup.exists():relocate_evidence(backup,backup,source=final)
    return backup
