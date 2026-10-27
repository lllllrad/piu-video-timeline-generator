"""Learn a head's persistence silhouette from its own clear native approach."""
from collections import defaultdict
import json

import numpy as np

from piu_timeline.play.pixel_cache import FORMAT as NATIVE_FORMAT,read_chunks,source_contract
from piu_timeline.play.screen_regions import occluders_at_bounds
from piu_timeline.play.processing.poses import FORMAT as POSE_FORMAT,references

FORMAT={'schema':1,'revision':3,'minimum_frames':3,'minimum_height_spacing':1.4,
        'radius_spacing':.45,'maximum_white_fraction':.45,'color_fraction_range':[.12,.85],
        'poses':POSE_FORMAT}


def hud_regions(layout,lane,y,radius,width,height):
    x=round(layout['lanes'][lane]['x']*width)
    return occluders_at_bounds(layout,[x-radius,round(y)-radius,x+radius+1,round(y)+radius+1],width,height)


def acceptable(color,white):
    return (FORMAT['color_fraction_range'][0]<color.mean()<FORMAT['color_fraction_range'][1]
            and white.mean()<FORMAT['maximum_white_fraction'])


def build(values,spacing,trace):
    if len(values)<FORMAT['minimum_frames']:return None
    poses=references(values,spacing)
    return {'mask':np.mean([mask for _,_,mask in values],axis=0)>=.5,'poses':poses,
            'evidence':{'trace':trace,'source_pts_seconds':[p for p,_,_ in values],
                        'frames':len(values),'poses':[p['evidence']for p in poses]}}


def learn(data,directory,times,pts):
    """Read retained masks once, without decoding or using accepted input times."""
    root=directory/'native-features';path=root/'manifest.json'
    if not path.is_file():return None
    manifest=json.loads(path.read_text())
    if manifest['contract']!={'format':NATIVE_FORMAT,'source':source_contract(data)}:
        raise ValueError('Processing template pixels do not belong to this source/geometry contract')
    layout=data['layout'];width=NATIVE_FORMAT['width']
    spacing=float(np.median(np.diff([lane['x']*width for lane in layout['lanes']])))
    note_height=data.get('analysis_height',round(data['analysis_width']*data['game_roi'][3]/data['game_roi'][2]))
    radius=max(2,round(FORMAT['radius_spacing']*spacing));lookup=defaultdict(list)
    for index,note in enumerate(data.get('notes',[])):
        if len(note.get('points',[]))<4:continue
        for time,y in note['points']:lookup[round(time,6)].append((index,note['lane'],y))
    examples=defaultdict(list);count=0
    for source_pts,time,planes,_ in read_chunks(root,manifest):
        if count>=len(times)or abs(time-times[count])>1e-6 or abs(source_pts-pts[count])>1e-6:
            raise ValueError('Processing template native timestamps differ from receptor pixels')
        count+=1;height=planes['white'].shape[0];scale=height/note_height
        receptor=layout['receptor_y']*height
        for index,lane,observed_y in lookup.get(round(time,6),[]):
            y=round(observed_y*scale);x=round(layout['lanes'][lane]['x']*width)
            left,top,right,bottom=x-radius,y-radius,x+radius+1,y+radius+1
            if (y<receptor+FORMAT['minimum_height_spacing']*spacing or left<0 or top<0
                    or right>width or bottom>layout.get('note_y_max',.95)*height
                    or hud_regions(layout,lane,y,radius,width,height)):continue
            color=planes['processing_'+layout['lanes'][lane]['color']][top:bottom,left:right]
            white=planes['white'][top:bottom,left:right]
            if acceptable(color,white):examples[index].append((source_pts,observed_y*scale,color.copy()))
    if count!=len(times):raise ValueError('Processing template native frame count differs from receptor pixels')
    result={}
    for index,values in examples.items():
        reference=build(values,spacing,'native-features/manifest.json')
        if reference is not None:result[index]=reference
    return result
