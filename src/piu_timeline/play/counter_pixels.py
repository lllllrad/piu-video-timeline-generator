"""Exact native counter crops, reusable when digit templates improve."""
import json

import numpy as np

from piu_timeline.play.frames import decode_frames


def contract(data):
    return {'schema':1,'encoding':'rgb_uint8',
            'source':{**{key:data[key] for key in
                         ('media','start_seconds','end_seconds','analysis_width')},
                      'game_roi':list(data['game_roi'])},
            'region':list(data['layout']['combo_roi'])}


def crop_shape(data):
    width=data['analysis_width']
    height=max(1,round(width*data['game_roi'][3]/data['game_roi'][2]))
    x,y,w,h=data['layout']['combo_roi']
    return int((y+h)*height)-int(y*height),int((x+w)*width)-int(x*width),3


class CounterPixelWriter:
    def __init__(self, data, directory):
        self.contract=contract(data)
        self.shape=crop_shape(data)
        self.expected_frames=data.get('frame_count')
        self.path=directory/'counter-pixels.npz'
        self.images=[];self.times=[];self.pts=[]

    def append(self, pts, seconds, rgb):
        if (rgb.dtype!=np.uint8 or rgb.shape!=self.shape
                or not np.isfinite([pts,seconds]).all()
                or self.times and seconds<=self.times[-1]
                ):
            raise ValueError('Invalid native counter pixels or timestamps')
        self.images.append(rgb.copy());self.times.append(seconds);self.pts.append(pts)

    def save(self):
        if not self.images or self.expected_frames is not None and len(self.images)!=self.expected_frames:
            raise ValueError('Incomplete native counter pixels')
        temporary=self.path.with_suffix('.build-npz')
        try:
            with temporary.open('wb') as stream:
                np.savez_compressed(stream,contract=json.dumps(self.contract,sort_keys=True),
                                    images=np.asarray(self.images),times=self.times,pts=self.pts)
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)


def counter_crops(data, directory):
    """Legacy caches decode once; compatible caches preserve every pixel and PTS."""
    path=directory/'counter-pixels.npz'
    if path.is_file():
        with np.load(path,allow_pickle=False) as saved:
            if json.loads(str(saved['contract']))!=contract(data):
                raise ValueError('Saved counter pixels differ from the requested source or region')
            images,times,pts=(saved[key] for key in ('images','times','pts'))
        if (images.dtype!=np.uint8 or images.ndim!=4 or images.shape[1:]!=crop_shape(data)
                or times.ndim!=1 or pts.ndim!=1 or not len(times)
                or len(images)!=len(times) or len(times)!=len(pts)
                or len(times)!=data.get('frame_count',len(times))
                or not np.isfinite(times).all() or not np.isfinite(pts).all()
                or not (np.diff(times)>0).all()):
            raise ValueError('Invalid saved native counter pixels')
        yield from zip(pts,times,images)
        return
    writer=CounterPixelWriter(data,directory)
    for pts,seconds,rgb in decode_frames(data['media'],data['start_seconds'],data['end_seconds'],
                                         data['game_roi'],data['analysis_width'],region=data['layout']['combo_roi']):
        writer.append(pts,seconds,rgb)
        yield pts,seconds,rgb
    writer.save()
