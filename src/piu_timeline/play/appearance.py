"""Reusable native-resolution head neighborhoods from the complete approach."""
from hashlib import sha256
from itertools import zip_longest
import json
from pathlib import Path

import cv2
import numpy as np

from piu_timeline.play.frames import decode_frames

APPEARANCE_FORMAT = {'schema':1,'revision':1,'channels':['color','white','visible','relaxed_color','valid'],
                     'half_width_spacing':.85,'half_height_spacing':1.4}


def contract(data, frames):
    heads = [[f['playback_seconds'],f['source_pts_seconds'],
              [[n['lane'],n['x'],n['y']] for n in f.get('notes',[])]] for f in frames]
    return {'format':APPEARANCE_FORMAT,'source':{key:data[key] for key in
            ('media','layout','game_roi','analysis_width','start_seconds','end_seconds')},
            'native_heads':sha256(json.dumps(heads,separators=(',',':')).encode()).hexdigest()}


def patches(rgb, detections, layout, spacing):
    """Pad clipped neighborhoods explicitly; padding is never visible background."""
    height,width = rgb.shape[:2]
    hue,saturation,value = cv2.split(cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV))
    colors = {'blue':(hue>=85)&(hue<=130),'red':(hue<=15)|(hue>=150),'yellow':(hue>=15)&(hue<=45)}
    white = (rgb.min(axis=2)>175)&(rgb.max(axis=2)-rgb.min(axis=2)<80)
    half,radius = int(np.ceil(.85*spacing)),int(np.ceil(1.4*spacing))
    result = []
    for note in detections:
        x,y = round(note['x']*width),round(note['y']*height)
        left,top = x-half,y-radius
        masks = np.zeros((5,2*radius+1,2*half+1),dtype=bool)
        a,b,c,d = max(0,top),min(height,top+2*radius+1),max(0,left),min(width,left+2*half+1)
        color = colors[layout['lanes'][note['lane']]['color']][a:b,c:d]
        saturation_crop,value_crop = saturation[a:b,c:d],value[a:b,c:d]
        channels = (color&(saturation_crop>90)&(value_crop>140),white[a:b,c:d],value_crop>60,
                    color&(saturation_crop>60)&(value_crop>90),np.ones((b-a,d-c),dtype=bool))
        for i,channel in enumerate(channels):
            masks[i,a-top:b-top,c-left:d-left] = channel
        result.append(np.packbits(masks,axis=-1))
    return result


def acquire(data, directory, frames, *, allow_decode=True):
    """One no-OCR pass; refits and future type rules reuse the spatial masks."""
    if not data.get('media',{}).get('video_streams') or not any(f.get('notes') for f in frames):
        return None
    path = directory/'appearance-features.npz';expected = contract(data,frames)
    if path.is_file():
        with np.load(path,allow_pickle=False) as saved:
            if json.loads(str(saved['contract'])) == expected:
                return path
    if not allow_decode:
        raise ValueError('Native appearance features require the acquisition stage before measurement')
    print('  Retaining native head neighborhoods across the full approach; no OCR...',flush=True)
    before = Path(data['media']['path']).stat()
    width = data['analysis_width']
    spacing = float(np.median(np.diff([lane['x']*width for lane in data['layout']['lanes']])))
    masks,times,pts,lanes,ys = [],[],[],[],[]
    decoded = decode_frames(data['media'],data['start_seconds'],data['end_seconds'],data['game_roi'],width)
    for frame_index,(raw,frame) in enumerate(zip_longest(frames,decoded)):
        if raw is None or frame is None:
            raise ValueError('Appearance acquisition differs from the native frame count')
        source_pts,time,rgb = frame
        if abs(source_pts-raw['source_pts_seconds'])>1e-6 or abs(time-raw['playback_seconds'])>1e-6:
            raise ValueError('Appearance acquisition differs from native source timestamps')
        if (frame_index+1)%2400 == 0:
            print(f'    Head neighborhoods: {time-data["start_seconds"]:.0f}/{data["end_seconds"]-data["start_seconds"]:.0f}s',flush=True)
        if raw.get('notes'):
            masks.extend(patches(rgb,raw['notes'],data['layout'],spacing))
            for note in raw['notes']:
                times.append(time);pts.append(source_pts);lanes.append(note['lane']);ys.append(note['y']*rgb.shape[0])
    after = Path(data['media']['path']).stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError('Source changed during appearance acquisition')
    temporary = path.with_suffix('.build-npz')
    try:
        with temporary.open('wb') as stream:
            np.savez_compressed(stream,masks=np.asarray(masks),times=times,pts=pts,lanes=lanes,ys=ys,
                                spacing=spacing,columns=2*int(np.ceil(.85*spacing))+1,
                                contract=json.dumps(expected,sort_keys=True))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def retained(data, directory, frames):
    """Read only source-bound acquired neighborhoods; never open the video."""
    return acquire(data, directory, frames, allow_decode=False)
