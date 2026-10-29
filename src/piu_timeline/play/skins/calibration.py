"""Verify reference anchors against independent native measurements and source RGB."""
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import shutil
from statistics import median
from piu_timeline.play.observations.coordinates import detection_points

import numpy as np

from piu_timeline.play.frames import decode_frames
from piu_timeline.play.head_registration import FORMAT as MEASUREMENT_FORMAT
from piu_timeline.play.skins.anchors import native_geometry, certificate
from piu_timeline.play.skins.bank import load_bank


def proposal(bank,template,data,records):
    evidence=template.get('source_evidence',{})
    if evidence.get('media')!=data['media']or evidence.get('roi')!=data['game_roi']:
        raise ValueError('different_source_identity')
    if evidence.get('reference_dimensions')!=[data['analysis_width'],data['analysis_height']]:
        raise ValueError('different_reference_dimensions')
    index=evidence.get('source_note')
    if type(index)is not int or not 0<=index<len(data['notes']):raise ValueError('missing_source_note')
    if data['notes'][index]['lane']%5!=template['lane_kind']:raise ValueError('different_source_lane_kind')
    record=records.get(index,{})
    if (record.get('coordinate_method')!='native_cap_measurements'
            or record.get('coordinate_uncertainty_pixels')!=MEASUREMENT_FORMAT['coordinate_uncertainty_pixels']):
        raise ValueError('missing_independent_native_measurement')
    samples=[s for s in record['observations']if s['source_pts_seconds']==evidence.get('source_pts_seconds')
             and s['time']==evidence.get('playback_seconds')]
    if len(samples)!=1:raise ValueError('missing_unique_source_frame_measurement')
    sample=samples[0]
    if evidence.get('qualified_cap_measurement',sample)!=sample:
        raise ValueError('different_declared_native_measurement')
    raw=detection_points(data['notes'][index])
    points=[y for time,y in raw if abs(time-sample['time'])<=1e-6]
    if len(points)!=1 or abs(points[0]-sample['detected_y_pixels'])>1e-5:
        raise ValueError('measurement_differs_from_original_detection')
    crop=evidence.get('source_crop',template.get('source_crop'))
    native_geometry(bank,template,sample,crop)
    return sample,crop


def frame_ranges(times):
    groups=[]
    for time in sorted(times):
        if not groups or time-groups[-1][-1]>.25:groups.append([])
        groups[-1].append(time)
    return [(max(0,g[0]-.001),g[-1]+.02)for g in groups]


def register_anchors(bank_path,analysis_path,registration_path,output):
    """Write a new bank; qualification never invents a missing frame measurement."""
    bank_path,output=Path(bank_path).resolve(),Path(output)
    if output.exists():raise FileExistsError(output)
    bank=load_bank(bank_path);data=json.loads(Path(analysis_path).read_text())
    registration_path=Path(registration_path);registration_bytes=registration_path.read_bytes();registration=json.loads(registration_bytes)
    if registration.get('format')!=MEASUREMENT_FORMAT or registration!=data.get('head_registration'):
        raise ValueError('Native cap artifact is not the supplied analysis measurement record')
    spacing=median(np.diff([lane['x']*data['analysis_width']for lane in data['layout']['lanes']]))
    scale=spacing/bank['spacing_pixels']
    if any((round(t['mask'].shape[1]*scale),round(t['mask'].shape[0]*scale))!=t['mask'].shape[::-1]
           for t in bank['templates']if t['role']!='hold_body'):
        raise ValueError('Reference images would be resampled at their declared native source scale')
    before=Path(data['media']['path']).stat()
    if (before.st_size,before.st_mtime_ns)!=(data['media']['size_bytes'],data['media']['mtime_ns']):
        raise ValueError('Anchor registration source identity changed')
    records={r['note']:r for r in registration['notes']}
    if len(records)!=len(registration['notes']):raise ValueError('Duplicate native registration identity')
    todo=defaultdict(list);diagnostics=[]
    for template in bank['templates']:
        if template['role']=='hold_body':continue
        try:sample,crop=proposal(bank,template,data,records)
        except ValueError as error:
            diagnostics.append({'template':template['id'],'status':'unverified','reason':str(error)});continue
        todo[round(sample['time'],6)].append((template,sample,crop))
    if not todo:raise ValueError('No independently measured source anchors are available')
    source_hash=sha256(registration_bytes).hexdigest();certificates={};decoded_frames=0;matched_frames=set()
    for start,end in frame_ranges(todo):
        for pts,time,rgb in decode_frames(data['media'],start,end,data['game_roi'],data['analysis_width']):
            if rgb.shape!=(data['analysis_height'],data['analysis_width'],3)or rgb.dtype!=np.uint8:
                raise ValueError('Anchor registration decoded geometry differs from native measurements')
            key=round(time,6)
            if key not in todo:continue
            if key in matched_frames:raise ValueError('Duplicate native source frame during anchor registration')
            matched_frames.add(key);decoded_frames+=1;frame_hash=sha256(rgb.tobytes()).hexdigest()
            for template,sample,crop in todo[key]:
                if abs(pts-sample['source_pts_seconds'])>1e-6:
                    raise ValueError('Anchor registration frame differs from original source PTS')
                x0,y0,x1,y1=next(r['box']for r in template['regions']if r['name']=='cap')
                native=rgb[crop[1]+y0:crop[1]+y1,crop[0]+x0:crop[0]+x1]
                reference=template['rgb'][y0:y1,x0:x1];mask=template['mask'][y0:y1,x0:x1]
                if native.shape!=reference.shape or not np.array_equal(native[mask],reference[mask]):
                    diagnostics.append({'template':template['id'],'status':'unverified','reason':'source_cap_pixels_differ'});continue
                certificates[template['id']]=certificate(bank,template,sample,crop,source_hash,frame_hash)
                diagnostics.append({'template':template['id'],'status':'registered','source_pts_seconds':pts})
    for time in todo.keys()-matched_frames:
        diagnostics.extend({'template':t['id'],'status':'unverified','reason':'original_source_frame_missing'}for t,_,_ in todo[time])
    after=Path(data['media']['path']).stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError('Source changed during anchor registration')
    if not certificates:raise ValueError('No reference cap pixels matched their measured source frames')
    if load_bank(bank_path)['contract']!=bank['contract']:raise ValueError('Reference bank changed during anchor registration')
    document=json.loads(bank_path.read_text());output.mkdir(parents=True)
    for template in document['templates']:
        path=(bank_path.parent/template['image']).resolve();relative=path.relative_to(bank_path.parent)
        destination=output/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,destination);template['image']=str(relative)
        if template['id']in certificates:template['native_anchor_registration']=certificates[template['id']]
    destination=output/'bank.json';destination.write_text(json.dumps(document,indent=2)+'\n');load_bank(destination)
    (output/'anchor-registration-report.json').write_text(json.dumps({
        'source_media':data['media'],'source_artifact_sha256':source_hash,'decoded_reference_frames':decoded_frames,
        'counts':dict(Counter(r['status']for r in diagnostics)),'templates':diagnostics,
        'scope':'relative native cap centers only; absolute game registration remains unverified'},indent=2)+'\n')
    return destination
