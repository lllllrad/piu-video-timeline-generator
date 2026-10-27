"""Cache opt-in image-role evidence without changing native detections."""
from hashlib import sha256
import json

from piu_timeline.play.pixel_cache import FORMAT as PIXEL_FORMAT,read_chunks,source_contract
from piu_timeline.play.skins.clearance import FORMAT,derive


def selected_profile(data,directory):
    path=directory.parent.parent/'note-skins.json'
    if not path.is_file():return None
    document=json.loads(path.read_text())
    if document.get('schema')!=1:raise ValueError('Unsupported note-skin profile schema')
    matches=[p for p in document['profiles']if data['segment_number']in p['segments']]
    if len(matches)>1:raise ValueError('Multiple note-skin profiles for clearance')
    return matches[0].get('role_clearance')if matches else None


def prepare(data,directory):
    data={k:v for k,v in data.items()if k!='skin_role_evidence'}
    profile=selected_profile(data,directory)
    if profile is None:return data
    native=directory/'native-features';manifest_path=native/'manifest.json'
    manifest=json.loads(manifest_path.read_text())if manifest_path.is_file()else None
    inputs=[directory/'frames.jsonl',manifest_path,*[native/name for name in(manifest or{}).get('chunks',[])]]
    contract={'format':FORMAT,'profile':profile,'skin':data['skin_detector']['contract'],
              'source':source_contract(data),'analysis_dimensions':[data['analysis_width'],data['analysis_height']],
              'frame_count':data['frame_count'],'object_effects':data.get('object_interpretation',{}).get('effects',[]),
              'native_trajectories':sha256(json.dumps([[n['lane'],n.get('detected_points',n.get('points',[]))]
                                       for n in data['notes']],sort_keys=True).encode()).hexdigest(),
              'inputs':{str(p.relative_to(directory)):[p.stat().st_size,p.stat().st_mtime_ns]if p.is_file()else None for p in inputs}}
    path=directory/'skin-role-evidence.json'
    if path.is_file():
        saved=json.loads(path.read_text())
        if saved.get('contract')==contract:return {**data,'skin_role_evidence':saved}
    from piu_timeline.play.skins.bank import load_bank
    from piu_timeline.play.object_roles import filter_frames
    try:
        if manifest is None:raise ValueError('Native feature masks are unavailable')
        if manifest['contract']!={'format':PIXEL_FORMAT,'source':source_contract(data)}:
            raise ValueError('Native clearance features differ from source or geometry')
        if manifest['frame_count']!=data['frame_count']:raise ValueError('Native clearance frame count differs')
        with (directory/'frames.jsonl').open()as stream:frames=filter_frames(data,[json.loads(line)for line in stream])
        if len(frames)!=data['frame_count']:raise ValueError('Clearance frame observations are incomplete')
        result=derive(data,frames,read_chunks(native,manifest),load_bank(data['skin_detector']['bank_path']),profile)
    except (OSError,ValueError,KeyError)as error:
        result={'status':'failed','notes':{},'warnings':[{'reason':'skin_clearance_profile_unavailable',
            'failure_detail':str(error),'lane':0,'check':'note_type_unresolved','observed_points':0,
            'visible_start_seconds':data['start_seconds'],'visible_end_seconds':data['end_seconds']}]}
    result['contract']=contract
    temporary=path.with_suffix('.build-json');temporary.write_text(json.dumps(result,ensure_ascii=False)+'\n');temporary.replace(path)
    return {**data,'skin_role_evidence':result}
