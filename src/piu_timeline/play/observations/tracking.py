"""Source-bound per-frame position input, independent of provisional track identities."""
import json

from piu_timeline.derived import CONTRACTS, call
from piu_timeline.play.observations.artifacts import save_input
from piu_timeline.play.stages import fingerprint

FORMAT={'schema':1,'measurement':'retained_qualified_image_positions_without_track_identity'}


def identity(data):
    return {'source':{k:data.get(k)for k in ('media','game_roi','start_seconds','end_seconds')},
            'geometry':{k:data.get(k)for k in ('analysis_width','analysis_height','layout')},
            'skin':data.get('skin_detector',{}).get('contract'),'coordinates':CONTRACTS['image_coordinates']}


def save(data,directory,frames,source_digest,unsupported_intervals=None):
    payload={'format':FORMAT,'identity':identity(data),'frames':frames,'frame_observations_sha256':source_digest,
             'unsupported_intervals':data.get('unsupported_intervals',[])if unsupported_intervals is None else unsupported_intervals}
    save_input(directory/'tracking-observations.json',{**payload,'fingerprint':fingerprint(payload)})


def retained(data,directory,bank):
    path=directory/'tracking-observations.json'
    if path.is_file():
        saved=json.loads(path.read_text());digest=saved.pop('fingerprint',None)
        if fingerprint(saved)!=digest:raise ValueError('Corrupt per-frame tracking observations')
        if saved.get('format')==FORMAT and saved.get('identity')==identity(data):return saved
    # Older tracking artifacts also retain original observations. Discard their
    # grouping completely: not one previous identity or target enters this view.
    source=directory/'tracking.json'
    if not source.is_file():return None
    document=json.loads(source.read_text());binding=document.get('input',{})
    if document.get('input_fingerprint')!=fingerprint(binding):raise ValueError('Corrupt saved tracking acquisition identity')
    expected=identity(data)
    if (binding.get('source')!=expected['source']or binding.get('detector_contract')!=expected['skin']
            or binding.get('coordinate_contract')!=expected['coordinates']
            or binding.get('geometry')!={'width':data['analysis_width'],'height':data['analysis_height'],'layout':data['layout']}):return None
    frames={s['time']:{'time':s['time'],'source_pts':s['source_pts'],'detections':[],'observations':[]}
            for s in document['timeline']}
    samples=[]
    for note in document['notes']:
        records=note.get('coordinate_measurements',[])
        if len(records)!=len(note['points']):return None
        for (time,y),sample in zip(note['points'],records,strict=True):
            if sample['time']!=time or abs(sample['detected_y_pixels']-y)>1e-8:
                raise ValueError('Saved position differs from original detection')
            if time not in frames or sample['source_pts_seconds']!=frames[time]['source_pts']:
                raise ValueError('Saved position has another source timeline')
            samples.append((note['lane'],sample))
    requests=[{'sample':s,'trajectoryY':s['native_y_pixels']}for _,s in samples]
    positions=call('coordinateMeasurements.imagePositions',requests,CONTRACTS['image_coordinates'])
    templates={t['id']:t for t in bank['templates']}
    for (lane,s),p in zip(samples,positions,strict=True):
        raw=s['detected_y_pixels'];frame=frames[s['time']]
        anchor={'yPixels':raw,'uncertaintyPixels':0,'basis':{'kind':'image_reference_anchor',
                'reference':{'kind':'sha256','value':s['cap_reference_sha256']}}}
        center={'yPixels':p['yPixels'],'uncertaintyPixels':p['uncertaintyPixels'],'basis':{'kind':'native_cap_center'}}if p['kind']=='native_cap_center'else None
        frame['detections'].append({'lane':lane,'y':raw/data['analysis_height']})
        frame['observations'].append({'time':s['time'],'sourcePtsSeconds':s['source_pts_seconds'],
            'anchor':anchor,'anchors':[]if p['kind']=='unavailable'else[anchor],'center':center,'measurement':s,
            'coordinateSampling':'sampled_image_grid','capRole':templates[s['template']]['role']
                if s['classification_status']in('full_pattern','cap_role_pattern')else None})
    ordered=sorted(frames.values(),key=lambda f:f['time'])
    if len(ordered)!=data['frame_count']:raise ValueError('Saved tracking observation frame count changed')
    save(data,directory,ordered,binding.get('frame_observations_sha256'))
    return {'frames':ordered,'frame_observations_sha256':binding.get('frame_observations_sha256')}
