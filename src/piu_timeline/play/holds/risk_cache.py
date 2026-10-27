"""Retain native risk provenance without re-reading a recording."""
from hashlib import sha256
from copy import deepcopy
import json

from piu_timeline.play.holds.risk_evidence import FORMAT,derive


def digest(value):
    return sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def context(data):
    fields=('id','lane','head_note','tail_note','start_censored','end_censored','body_frames','body_evidence','image_connection_evidence')
    contract={'format':FORMAT,'source':{k:data[k]for k in('media','layout','game_roi','analysis_width','analysis_height','frame_count')},
              'skin':data['skin_detector']['contract'],'head_registration':digest(data.get('head_registration',{})),
              'geometry':digest([{k:h.get(k)for k in fields}for h in data.get('hold_analysis',{}).get('holds',[])]),
              'object_roles':data.get('object_interpretation',{}).get('effects',[]),
              'intervals':data.get('unsupported_intervals',[]),
              }
    return deepcopy(contract)


def prepare(data,directory):
    data={k:v for k,v in data.items()if k!='body_risk_evidence'}
    if not data.get('skin_detector'):return data
    trace=directory/'frames.jsonl'
    contract={**context(data),'native_trace':[trace.stat().st_size,trace.stat().st_mtime_ns]if trace.is_file()else None}
    path=directory/'body-risk-evidence.json'
    if path.is_file():
        try:saved=json.loads(path.read_text())
        except (OSError,ValueError):saved={}
        if saved.get('contract')==contract:return {**data,'body_risk_evidence':saved}
    from piu_timeline.play.skins.bank import load_bank
    from piu_timeline.play.object_roles import filter_frames
    try:
        with trace.open()as stream:frames=filter_frames(data,[json.loads(line)for line in stream])
        if len(frames)!=data['frame_count']:raise ValueError('Native risk frame count differs')
        result=derive(data,frames,load_bank(data['skin_detector']['bank_path']))
    except (OSError,ValueError,KeyError)as error:
        result={'status':'failed','frames':[],'warnings':[{'reason':'native_body_risk_evidence_unavailable',
            'failure_detail':str(error),'lane':0,'check':'note_processing_unresolved','observed_points':0,
            'visible_start_seconds':data['start_seconds'],'visible_end_seconds':data['end_seconds']}]}
    result['contract']=contract
    temporary=path.with_suffix('.build-json');temporary.write_text(json.dumps(result,ensure_ascii=False)+'\n');temporary.replace(path)
    return {**data,'body_risk_evidence':result}
