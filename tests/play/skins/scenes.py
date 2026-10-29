"""Render independent chart objects and run native image/connection consumers.

The caller supplies object truth. Acquisition creates tracks without receiving
those identities or target times. This helper makes no recognition assertions.
"""
import json
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
import os
from pathlib import Path
import sys
import tempfile

import cv2
import numpy as np

from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.holds import measure_connections
from piu_timeline.play.skins.observations import observe
from piu_timeline.play.skins.coordinates import measure
from piu_timeline.play.tracking import NoteTracker


BACKGROUND=np.array([12,14,18],dtype='uint8')
COLORS=([30,140,230],[230,50,65],[240,190,35],[220,65,85],[45,150,240])


def cap(kind):
    """A lane-colored, outlined glyph shared by tap and both hold caps."""
    image=np.full((20,20,3),245,dtype='uint8')
    image[2:18,2:18]=COLORS[kind]
    # Direction/center details localize the anchor without relying on contours.
    for row in range(4,16):
        col=4+(row+3*kind)%12
        image[row,col]=[55,65,75]
    return image


def bank_at(root,clearance_rows=4,connection_rows=6,margin=4,cap_only=False):
    entries=[]
    for kind in range(5):
        glyph=cap(kind);color=COLORS[kind]
        for role in ('tap','hold_start','hold_end','hold_body'):
            if role=='hold_body':
                rgb=np.full((12,8,3),color,dtype='uint8');anchor=[4,6]
                regions=[('body',[0,0,8,12])]
            else:
                h,offset=(20+2*(clearance_rows+margin),clearance_rows+margin)if role=='tap'else(20+margin+connection_rows,margin)if role=='hold_start'else(20+margin+connection_rows,connection_rows)
                rgb=np.full((h,20,3),BACKGROUND,dtype='uint8')
                rgb[offset:offset+20]=glyph;anchor=[10,offset+10]
                regions=[('cap',[0,offset,20,offset+20])]
                if role=='tap':regions += [('clear_above',[6,margin,14,offset]),('clear_below',[6,offset+20,14,offset+20+clearance_rows])]
                else:
                    a,b=(offset+20,h)if role=='hold_start'else(0,connection_rows)
                    rgb[a:b,6:14]=color;regions.append(('connection',[6,a,14,b]))
            # The reference scene supplies this surrounding RGB too. It is
            # interpolation context, not extra cap/body comparison coverage.
            alpha=np.full(rgb.shape[:2],255,dtype='uint8')
            name=f'{kind}-{role}'
            cv2.imwrite(str(root/(name+'.png')),np.dstack([rgb[:,:,::-1],alpha]))
            entries.append({'id':name,'role':role,'lane_kind':kind,'image':name+'.png',
                            'anchor_pixels':anchor,'sampling_context':[[0,0,rgb.shape[1],rgb.shape[0]]],
                            'regions':[{'name':n,'box':b,'maximum_error':.002}for n,b in regions]})
    path=root/'bank.json'
    if cap_only:
        entries=[t for t in entries if t['role']in('tap','hold_body')]
        for t in entries:
            if t['role']=='tap':
                # Only the shared glyph interior is role-independent after
                # interpolation; its edge can include a stem or background.
                region=t['regions'][0];a,b,c,d=region['box']
                t['regions']=[{**region,'box':[a+4,b+4,c-4,d-4]}]
    path.write_text(json.dumps({'schema':1,'skin':'generated-colored-caps','spacing_pixels':20,'templates':entries}))
    return load_bank(path)


def render(objects,time,width,height,seed,mode,frame):
    rng=np.random.default_rng(seed)
    image=np.full((height,width,3),BACKGROUND,dtype='uint8')
    image+=rng.integers(0,3,image.shape,dtype='uint8')
    for obj in objects:
        lane=obj['lane'];x=40+lane*20;head=round(obj['y']-80*time)
        tail=round(obj.get('end_y',obj['y'])-80*time)
        if obj['kind']=='hold' and not(mode=='contradictory_roles'and frame==3):
            image[head:tail+1,x-4:x+4]=COLORS[lane%5]
        if mode=='opaque_connection':image[head+10:tail-10,x-5:x+5]=255
        if mode=='body_only':continue
        for y in ([head,tail]if obj['kind']=='hold'else[head]):
            image[y-10:y+10,x-10:x+10]=cap(lane%5)
    return image


def acquire(spec,root,bank):
    scale,fps,lanes=spec['scale'],spec['fps'],spec['lanes']
    base_width,base_height=(lanes+4)*20,300
    width,height=round(base_width*scale),round(base_height*scale)
    layout={'receptor_y':.08,'note_y_max':.95,
            'judgment_roi':[0,0,0,0],'combo_roi':[0,0,0,0],
            'lanes':[{'x':(40+i*20)/base_width,'color':('blue','red','yellow','red','blue')[i%5]}for i in range(lanes)]}
    tracker=NoteTracker(layout,width,height,skin_bank=bank);native=[]
    images=[render(spec['objects'],i/fps,base_width,base_height,i+spec['seed'],spec.get('mode'),i)for i in range(round(.2*fps)+1)]
    if spec.get('capture')=='encoded':
        from tests.play.skins.capture import encoded
        captures,expected_pts,preserved=encoded(images,fps,root,width)
    else:
        captures=[(42.125+i/fps,i/fps,cv2.resize(image,(width,height),interpolation=cv2.INTER_AREA))for i,image in enumerate(images)]
        expected_pts=[42.125+i/fps for i in range(len(images))];preserved=True
    for pts,time,image in captures:
        detections=tracker.detect(image);tracker.update(time,detections,pts)
        native.append({'playback_seconds':time,'source_pts_seconds':pts,'skin_observations':tracker.skin_observations})
    # Raw acquired tracks, not scene-supplied endpoints or fitted truth.
    notes=[{'lane':t.lane,'points':t.points}for t in tracker.finished+tracker.active]
    data={'analysis_width':width,'analysis_height':height,'layout':layout,'notes':notes,
          'start_seconds':0,'end_seconds':.2,'skin_detector':{'bank_path':str(root/'bank.json'),'contract':{'bank':bank['contract']}}}
    warnings=[];connections=measure_connections(data,native,warnings)
    roles=observe(data,native)
    coordinates=measure(data,native)
    return {'id':spec['id'],'notes':notes,'roles':roles['notes'],'connections':connections,'warnings':warnings,'coordinates':coordinates,
            'expected_source_pts':expected_pts,'source_preserved':preserved,
            'cap_subfeature_frames':sum(any(o.get('cap_subfeature')for o in f['skin_observations'])for f in native),
            'frames':[{'time':f['playback_seconds'],'pts':f['source_pts_seconds'],
                       'caps':[{k:o[k]for k in ('lane','y','role','classification_status')}for o in f['skin_observations']if o['role']!='hold_body']}
                      for f in native]}


def acquire_task(task):
    spec,directory,bank=task
    return acquire(spec,directory,bank)


def main():
    specs=json.load(sys.stdin)
    with tempfile.TemporaryDirectory()as tmp:
        root=Path(tmp);banks={(4,False):(root,bank_at(root))};tasks=[]
        for spec in specs:
            margin=spec.get('reference_margin',4);cap_only=spec.get('reference_profile')=='cap_only';profile=margin,cap_only
            if profile not in banks:
                directory=root/f'context-{margin}-{cap_only}';directory.mkdir()
                banks[profile]=directory,bank_at(directory,margin=margin,cap_only=cap_only)
            directory,bank=banks[profile];tasks.append((spec,directory,bank))
        available=len(os.sched_getaffinity(0))if hasattr(os,'sched_getaffinity')else(os.cpu_count()or 1)
        workers=min(4,max(1,available))
        # Independent RGB scenes share immutable references and retain input
        # order. Encoded scenes stay serial to bound FFmpeg thread pools.
        if workers>1 and len(tasks)>1 and all(s.get('capture')!='encoded'for s in specs):
            with ProcessPoolExecutor(max_workers=workers,mp_context=get_context('spawn'),
                    initializer=cv2.setNumThreads,initargs=(1,))as pool:
                results=list(pool.map(acquire_task,tasks))
        else:results=[acquire_task(task)for task in tasks]
        json.dump(results,sys.stdout,allow_nan=False)


if __name__=='__main__':main()
