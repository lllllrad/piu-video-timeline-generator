"""Render independent chart objects and run native image/connection consumers.

The caller supplies object truth. Acquisition creates tracks without receiving
those identities or target times. This helper makes no recognition assertions.
"""
import json
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


def bank_at(root):
    entries=[]
    for kind in range(5):
        glyph=cap(kind);color=COLORS[kind]
        for role in ('tap','hold_start','hold_end','hold_body'):
            if role=='hold_body':
                rgb=np.full((12,8,3),color,dtype='uint8');anchor=[4,6]
                regions=[('body',[0,0,8,12])]
            else:
                h,offset=(28,4)if role=='tap'else(24,0)if role=='hold_start'else(24,4)
                rgb=np.full((h,20,3),BACKGROUND,dtype='uint8')
                rgb[offset:offset+20]=glyph;anchor=[10,offset+10]
                regions=[('cap',[0,offset,20,offset+20])]
                if role=='tap':regions += [('clear_above',[6,0,14,3]),('clear_below',[6,25,14,28])]
                else:
                    a,b=(20,24)if role=='hold_start'else(0,4)
                    rgb[a:b,6:14]=color;regions.append(('connection',[6,a,14,b]))
            alpha=np.zeros(rgb.shape[:2],dtype='uint8')
            for _,(x0,y0,x1,y1)in regions:alpha[y0:y1,x0:x1]=255
            name=f'{kind}-{role}'
            cv2.imwrite(str(root/(name+'.png')),np.dstack([rgb[:,:,::-1],alpha]))
            entries.append({'id':name,'role':role,'lane_kind':kind,'image':name+'.png',
                            'anchor_pixels':anchor,'regions':[{'name':n,'box':b,'maximum_error':.002}for n,b in regions]})
    path=root/'bank.json'
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
    for i in range(round(.2*fps)+1):
        time=i/fps;pts=42.125+time
        image=render(spec['objects'],time,base_width,base_height,i+spec['seed'],spec.get('mode'),i)
        image=cv2.resize(image,(width,height),interpolation=cv2.INTER_AREA)
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
            'cap_subfeature_frames':sum(any(o.get('cap_subfeature')for o in f['skin_observations'])for f in native),
            'frames':[{'time':f['playback_seconds'],'pts':f['source_pts_seconds'],
                       'caps':[{k:o[k]for k in ('lane','y','role','classification_status')}for o in f['skin_observations']if o['role']!='hold_body']}
                      for f in native]}


def main():
    specs=json.load(sys.stdin)
    with tempfile.TemporaryDirectory()as tmp:
        root=Path(tmp);bank=bank_at(root)
        json.dump([acquire(spec,root,bank)for spec in specs],sys.stdout)


if __name__=='__main__':main()
