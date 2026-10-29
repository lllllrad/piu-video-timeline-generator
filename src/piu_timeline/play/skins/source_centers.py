"""Measure complete bright PIU cap references, independently of motion or beats."""
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import shutil

import cv2
import numpy as np

from piu_timeline.play.skins.anchors import certificate
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.calibration import frame_ranges
from piu_timeline.play.frames import decode_frames

FORMAT={'schema':1,'revision':2,'method':'bright_piu_complete_source_cap',
        'minimum_value':170,'minimum_saturation':65,'white_minimum':165,'white_chroma':110,
        'size_spacing_range':[.65,1.25],'maximum_height_difference_pixels':1,
        'maximum_center_shift_spacing':.25,'coordinate_uncertainty_pixels':1.}


def foreground(template):
    rgb=template['rgb'];h,s,v=cv2.split(cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV))
    kind=template['lane_kind']
    color=((h>=75)&(h<=140)if kind in(0,4)else
           ((h<=28)|(h>=150))if kind in(1,3)else(h>=15)&(h<=55))
    pixels=((rgb.min(axis=2)>FORMAT['white_minimum'])&
                (rgb.max(axis=2)-rgb.min(axis=2)<FORMAT['white_chroma']))|(
                color&(s>FORMAT['minimum_saturation'])&(v>FORMAT['minimum_value']))
    return cv2.morphologyEx(pixels.astype('uint8'),cv2.MORPH_CLOSE,np.ones((3,3),dtype='uint8'))


def isolated(template,spacing):
    """Only this explicit bright-cap family has the declared foreground model."""
    mask=foreground(template)
    boxes=[]
    for contour in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,w,h=cv2.boundingRect(contour)
        if (all(FORMAT['size_spacing_range'][0]*spacing<n<FORMAT['size_spacing_range'][1]*spacing for n in(w,h))
                and cv2.pointPolygonTest(contour,tuple(map(float,template['anchor_pixels'])),False)>=0
                and 0<x<x+w<mask.shape[1]and 0<y<y+h<mask.shape[0]
                and template['mask'][y:y+h,x:x+w].all()):boxes.append([x,y,w,h])
    return boxes[0]if len(boxes)==1 else None


def leading(template,references,spacing):
    """A stem cannot enlarge the glyph: use independently measured cap sizes."""
    identities={(t.get('source_evidence',{}).get('source_pts_seconds'),
                 tuple(t.get('source_evidence',{}).get('source_crop',[])))for t,_ in references}
    if len(identities)<2:return None
    widths=[box[2]for _,box in references];heights=[box[3]for _,box in references]
    error=FORMAT['coordinate_uncertainty_pixels']
    if max(widths)-min(widths)>2*error or max(heights)-min(heights)>2*error:return None
    height=float(np.median(heights));mask=foreground(template);candidates=[]
    stem=next(r['box']for r in template['regions']if r['name']=='connection')
    for contour in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,w,h=cv2.boundingRect(contour);bottom=round(y+height)
        if (cv2.pointPolygonTest(contour,tuple(map(float,template['anchor_pixels'])),False)<0
                or not min(widths)-error<=w<=max(widths)+error
                or not 0<x<x+w<mask.shape[1]or not 0<y<bottom<mask.shape[0]
                or h<height-error or abs(y+height/2-template['anchor_pixels'][1])>FORMAT['maximum_center_shift_spacing']*spacing
                or not template['mask'][y:bottom,x:x+w].all()):continue
        component=np.zeros_like(mask);cv2.drawContours(component,[contour],-1,1,cv2.FILLED);component&=mask
        shoulders=component[bottom-2:bottom,x:x+w].copy()
        shoulders[:,max(0,stem[0]-x):min(w,stem[2]-x)]=0
        if not shoulders.any():continue
        candidates.append({'center_pixels':[x+w/2,y+height/2],
            'basis':'leading_cap_with_independently_measured_dimensions',
            'source_cap_bounds':[x,y,x+w,bottom],'lower_shoulder_pixels':int(shoulders.sum()),
            'reference_templates':[t['id']for t,_ in references],'reference_sizes':[[box[2],box[3]]for _,box in references]})
    return candidates[0]if len(candidates)==1 else None


def proposals(bank):
    """Complete source caps define centers; attached starts require matching RGB."""
    taps=defaultdict(list);measured={};spacing=bank['spacing_pixels']
    for t in bank['templates']:
        if t['role']!='tap':continue
        box=isolated(t,spacing)
        if box:taps[t['lane_kind']].append((t,box))
    for kind,items in taps.items():
        height=max(box[3]for _,box in items)
        taps[kind]=[(t,box)for t,box in items if height-box[3]<=FORMAT['maximum_height_difference_pixels']]
        for t,(x,y,w,h)in taps[kind]:
            measured[t['id']]={'center_pixels':[x+w/2,y+h/2],'source_cap_bounds':[x,y,x+w,y+h],
                               'basis':'complete_bright_cap_envelope'}
    for t in bank['templates']:
        if t['role']!='hold_start':continue
        geometry=leading(t,taps[t['lane_kind']],spacing)
        target=t['rgb'].astype('float32')/255;matches=[]
        for ref,box in taps[t['lane_kind']]:
            cap=next(r for r in ref['regions']if r['name']=='cap');a,b,c,d=cap['box']
            mask=ref['mask'][b:d,a:c].astype('uint8').copy()
            if 'comparison_boxes'in cap:
                selected=np.zeros_like(mask)
                for x,y,z,w in cap['comparison_boxes']:selected[y-b:w-b,x-a:z-a]=1
                mask&=selected
            if not mask.any():continue
            patch=ref['rgb'][b:d,a:c].astype('float32')/255
            if min(target.shape[0]-patch.shape[0],target.shape[1]-patch.shape[1])<0:continue
            errors=cv2.matchTemplate(target,patch,cv2.TM_SQDIFF,mask=mask)/(3*int(mask.sum()))
            local=cv2.erode(errors,np.ones((3,3),dtype='uint8'))
            ys,xs=np.nonzero(np.isfinite(errors)&(errors<=cap.get('maximum_error',.015))&(errors<=local+1e-7))
            for y,x in zip(ys,xs):
                if not t['mask'][y:y+patch.shape[0],x:x+patch.shape[1]][mask.astype(bool)].all():continue
                center=[float(x+box[0]+box[2]/2-a),float(y+box[1]+box[3]/2-b)]
                if (abs(x+ref['anchor_pixels'][0]-a-t['anchor_pixels'][0])<=.1*spacing
                        and abs(center[1]-t['anchor_pixels'][1])<=FORMAT['maximum_center_shift_spacing']*spacing):
                    matches.append({'reference':ref['id'],'center_pixels':center,'cap_error':float(errors[y,x])})
        if not matches:
            if geometry:measured[t['id']]=geometry
            continue
        error=FORMAT['coordinate_uncertainty_pixels']
        lo=max(m['center_pixels'][1]-error for m in matches);hi=min(m['center_pixels'][1]+error for m in matches)
        if lo<=hi:
            if geometry:
                center=geometry['center_pixels'][1]
                if max(lo,center-error)>min(hi,center+error):continue
            measured[t['id']]={'center_pixels':[t['anchor_pixels'][0],(lo+hi)/2],
                                'basis':'complete_tap_cap_rgb_match','matches':matches,
                                **({'independent_geometry':geometry}if geometry else{})}
    return measured


def prepare(bank_path,output):
    """Certify only proposals verified against unchanged original source RGB/PTS."""
    bank_path=Path(bank_path).resolve();output=Path(output)
    if output.exists():raise FileExistsError(output)
    bank=load_bank(bank_path);measured=proposals(bank);todo=defaultdict(lambda:defaultdict(list));states={}
    for t in bank['templates']:
        if t['id']not in measured:continue
        e=t.get('source_evidence',{});media=e.get('media',{});crop=e.get('source_crop')
        if not all(k in e for k in ('media','roi','reference_dimensions','playback_seconds','source_pts_seconds','source_crop')):continue
        source=Path(media['path']);stat=source.stat()
        if (stat.st_size,stat.st_mtime_ns)!=(media['size_bytes'],media['mtime_ns']):raise ValueError('Source identity changed')
        states[str(source)]=(stat.st_size,stat.st_mtime_ns)
        key=json.dumps({k:e[k]for k in ('media','roi','reference_dimensions')},sort_keys=True)
        todo[key][round(e['playback_seconds'],6)].append((t,crop))
    artifacts={'format':FORMAT,'bank_contract':bank['contract'],'measurements':measured}
    content=json.dumps(artifacts,sort_keys=True,allow_nan=False).encode();artifact_hash=sha256(content).hexdigest()
    proofs={};diagnostics=[]
    for key,times in todo.items():
        source=json.loads(key);width,height=source['reference_dimensions'];seen=set()
        for start,end in frame_ranges(times):
            for pts,time,rgb in decode_frames(source['media'],start,end,source['roi'],width):
                row=round(time,6)
                if row not in times:continue
                if row in seen:raise ValueError('Duplicate source frame')
                seen.add(row)
                if rgb.shape!=(height,width,3):raise ValueError('Source reference dimensions changed')
                for t,crop in times[row]:
                    if abs(time-t['source_evidence']['playback_seconds'])>1e-6 or abs(pts-t['source_evidence']['source_pts_seconds'])>1e-6:
                        raise ValueError('Source cap PTS changed')
                    x,y,z,w=crop;pixels=rgb[y:w,x:z];mask=t['mask']
                    if pixels.shape!=t['rgb'].shape or not np.array_equal(pixels[mask],t['rgb'][mask]):
                        diagnostics.append({'template':t['id'],'reason':'source_pixels_differ'});continue
                    center=measured[t['id']]['center_pixels'];template={**t,'native_center_pixels':center}
                    sample={'time':time,'source_pts_seconds':pts,'detected_y_pixels':y+center[1],
                            'offset_pixels':0,'measurement_basis':FORMAT['method']}
                    proofs[t['id']]=certificate(bank,template,sample,crop,artifact_hash,sha256(rgb.tobytes()).hexdigest())
        diagnostics.extend({'template':t['id'],'reason':'source_frame_missing'}for row in times.keys()-seen for t,_ in times[row])
    for path,identity in states.items():
        stat=Path(path).stat()
        if (stat.st_size,stat.st_mtime_ns)!=identity:raise ValueError('Source changed during verification')
    verified=set(proofs)
    for name in list(proofs):
        measurement=measured[name]
        dependencies={m['reference']for m in measurement.get('matches',[])}|set(measurement.get('reference_templates',[]))
        dependencies.update(measurement.get('independent_geometry',{}).get('reference_templates',[]))
        if not dependencies<=verified:
            proofs.pop(name);diagnostics.append({'template':name,'reason':'source_center_reference_unverified',
                                                'references':sorted(dependencies-verified)})
    if not proofs:raise ValueError('No complete source cap centers verified')
    if load_bank(bank_path)['contract']!=bank['contract']:raise ValueError('Source bank changed')
    output.mkdir(parents=True);document=json.loads(bank_path.read_text())
    for t in document['templates']:
        source=bank_path.parent/t['image'];destination=output/t['image'];destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
        if t['id']in proofs:t.update(native_center_pixels=measured[t['id']]['center_pixels'],native_anchor_registration=proofs[t['id']])
        elif t['id']in measured:
            t.pop('native_center_pixels',None);t.pop('native_anchor_registration',None)
    (output/'source-center-measurements.json').write_bytes(content)
    (output/'source-center-verification.json').write_text(json.dumps({'registered':sorted(proofs),'unverified':diagnostics,
        'unmeasured':[t['id']for t in document['templates']if t['role']!='hold_body'and t['id']not in proofs]},indent=2)+'\n')
    path=output/'bank.json';path.write_text(json.dumps(document,indent=2)+'\n');load_bank(path)
    return path
