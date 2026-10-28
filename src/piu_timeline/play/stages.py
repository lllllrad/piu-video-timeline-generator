"""Persist independently reusable coordinate output before musical inference."""
from hashlib import sha256
import json

FORMAT={'schema':1,'producer':'registered_coordinates_before_musical_timing'}
FIELDS=('notes','scroll_motion','head_registration','timing_reconstruction','combo_events',
        'matches','deferred_matches','unsupported_intervals','coverage','excluded_notes','timing_format')
IDENTITY=('media','game_roi','start_seconds','end_seconds','player','participant_slots',
          'analysis_width','analysis_height','layout','native_frame_format','timing_format')


def fingerprint(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def identity(data):
    return {**{key:data.get(key)for key in IDENTITY},
            'skin_detector':data.get('skin_detector',{}).get('contract')}


def paths(value,before,after):
    if isinstance(value,str)and value.startswith(before):return after+value[len(before):]
    if isinstance(value,list):return [paths(v,before,after)for v in value]
    if isinstance(value,tuple):return [paths(v,before,after)for v in value]
    if isinstance(value,dict):return {k:paths(v,before,after)for k,v in value.items()}
    return value


def save_coordinates(data,directory):
    payload={'format':FORMAT,'identity':identity(data),'output':{key:data[key]for key in FIELDS if key in data}}
    payload=paths(payload,str(directory.resolve())+'/', '@segment/')
    digest=fingerprint(payload)
    destination=directory/'coordinates.json'
    temporary=directory/'coordinates.build.json'
    temporary.write_text(json.dumps({**payload,'fingerprint':digest},ensure_ascii=False)+'\n')
    temporary.replace(destination)
    return {**data,'coordinate_stage':{'format':FORMAT,'fingerprint':digest}}


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
    return {**result,**restored['output']}
