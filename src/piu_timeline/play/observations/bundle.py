"""Independent channel acquisition; no chart, track, OCR or association prerequisite."""
from contextlib import closing, nullcontext
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
import shutil
from uuid import uuid4

import cv2
import numpy as np

from piu_timeline.play.frames import decode_frames
from piu_timeline.play.judgments import judgment_region
from piu_timeline.play.pixel_cache import measurements, FIELDS, FORMAT as MASK_FORMAT
from piu_timeline.play.observations.artifacts import save_input

FORMAT = {'schema': 1, 'revision': 1, 'chunk_frames': 64,
          'coordinates': 'normalized_full_game_top_left', 'pixels': 'rgb24',
          'input': 'uninterpreted_receptor_rgb', 'input_extent_spacing': 2.0,
          'rgb_encoding': 'planar_green_difference_temporal_delta_v1'}


def source(data, width):
    return {**{k: data[k] for k in ('media', 'game_roi', 'layout', 'start_seconds', 'end_seconds')},
            'width': width, 'height': round(width*data['game_roi'][3]/data['game_roi'][2])}


def source_current(bound):
    stat = Path(bound['media']['path']).stat()
    if (stat.st_size, stat.st_mtime_ns) != (bound['media']['size_bytes'], bound['media']['mtime_ns']):
        raise ValueError('Original source identity changed; observations cannot be reused')


def contract(data, width):
    return {'format': FORMAT, 'source': source(data, width),
            'masks': MASK_FORMAT}


def rectangles(bound):
    width, height, layout = bound['width'], bound['height'], bound['layout']
    spacing = float(np.median(np.diff([lane['x']*width for lane in layout['lanes']])))
    extent = FORMAT['input_extent_spacing']*spacing
    receptor = layout['receptor_y']*height
    inputs = [0, max(0, math.floor(receptor-extent)), width, min(height, math.ceil(receptor+extent))]
    regions = [layout['combo_roi'], judgment_region(layout)]
    popup = [max(0, math.floor(min(r[0] for r in regions)*width)),
             max(0, math.floor(min(r[1] for r in regions)*height)),
             min(width, math.ceil(max(r[0]+r[2] for r in regions)*width)),
             min(height, math.ceil(max(r[1]+r[3] for r in regions)*height))]
    return {'input': inputs, 'popup': popup, 'spacing_pixels': spacing,
            'popup_regions': {'combo': layout['combo_roi'], 'judgment': judgment_region(layout)}}


def crop(rgb, bounds):
    a,b,c,d = bounds
    return rgb[b:d,a:c].copy()


def digest(path):
    value = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): value.update(block)
    return {'size_bytes': path.stat().st_size, 'sha256': value.hexdigest()}


def read_manifest(directory, expected=None, verify=False):
    path = directory/'manifest.json'
    if not path.is_file(): return None
    saved = json.loads(path.read_text())
    if saved.get('schema') != 1: raise ValueError('Invalid independent observation manifest')
    source_current(saved['contract']['source'])
    if expected is not None and saved['contract'] != expected: return None
    count = 0
    for chunk in saved['chunks']:
        if chunk['first_frame'] != count or chunk['frames'] < 1:
            raise ValueError('Observation chunks have a gap or invalid count')
        count += chunk['frames']
        for name, identity in chunk['files'].items():
            path = directory/name
            if Path(name).is_absolute() or '..' in Path(name).parts or not path.is_file():
                raise ValueError('Missing or invalid observation chunk path')
            if path.stat().st_size != identity['size_bytes'] or verify and digest(path) != identity:
                raise ValueError('Corrupt independent observation chunk')
    if not count or count != saved['frame_count']: raise ValueError('Incomplete independent observations')
    return saved


def encode_rgb(images):
    """Reversible byte predictors only; no quantization or frame removal."""
    color=np.asarray(images).copy()
    color[:,:,:,0]-=color[:,:,:,1];color[:,:,:,2]-=color[:,:,:,1]
    delta=np.concatenate((color[:1],color[1:]-color[:-1]))
    return delta.transpose(0,3,1,2).tobytes()


def decode_rgb(raw, count, width, height):
    if len(raw)!=count*width*height*3: raise ValueError('Cached RGB shape differs')
    values=np.frombuffer(raw,dtype='uint8').reshape(count,3,height,width)
    values=np.add.accumulate(values,axis=0,dtype='uint8').transpose(0,2,3,1).copy()
    values[:,:,:,0]+=values[:,:,:,1];values[:,:,:,2]+=values[:,:,:,1]
    return values


def game_frames(directory, saved=None, start=None, end=None):
    """Replay exact acquired game pixels; decoder and other channels are unnecessary."""
    saved = saved or read_manifest(directory)
    if saved is None: raise ValueError('No reusable game pixels')
    bound = saved['contract']['source'];size = bound['width']*bound['height']*3
    for chunk in saved['chunks']:
        origin=bound['media']['container_start_seconds']
        if start is not None and chunk['last_source_pts_seconds']-origin<start: continue
        if end is not None and chunk['first_source_pts_seconds']-origin>=end: continue
        def read(suffix):
            names=[name for name in chunk['files'] if name.endswith('.'+suffix)]
            if len(names)!=1: raise ValueError('Missing independent channel file')
            path=directory/names[0]
            if digest(path)!=chunk['files'][names[0]]: raise ValueError('Corrupt independent observation channel')
            return gzip.decompress(path.read_bytes())
        rows=[json.loads(line)for line in read('frames.jsonl.gz').decode().splitlines()]
        raw=read('game.rgb.gz')
        if len(rows)!=chunk['frames'] or len(raw)!=size*chunk['frames']: raise ValueError('Game pixel timeline differs')
        values=decode_rgb(raw,chunk['frames'],bound['width'],bound['height'])
        for row,image in zip(rows,values,strict=True):
            if start is not None and row['playback_seconds']<start: continue
            if end is not None and row['playback_seconds']>=end: continue
            yield row['source_pts_seconds'],row['playback_seconds'],image


class Writer:
    """Bounded chunks share one original timeline across independent channels."""
    def __init__(self, directory, binding):
        self.directory, self.binding = directory, binding
        self.geometry = rectangles(binding['source'])
        self.frames, self.inputs, self.popups, self.masks, self.games = [], [], [], [], []
        self.chunks, self.count, self.previous = [], 0, None
        directory.mkdir(parents=True)

    def append(self, pts, time, rgb):
        bound = self.binding['source']
        if rgb.dtype != np.uint8 or rgb.shape != (bound['height'],bound['width'],3):
            raise ValueError('Observation pixels differ from declared geometry')
        if not np.isfinite([pts,time]).all() or self.previous is not None and (pts<=self.previous[0] or time<=self.previous[1]):
            raise ValueError('Independent observations require increasing original PTS and playback time')
        if abs((pts-bound['media']['container_start_seconds'])-time)>1e-6:
            raise ValueError('Observation playback time differs from original source PTS')
        if not bound['start_seconds']-1e-6<=time<bound['end_seconds']:
            raise ValueError('Observation falls outside the original segment')
        self.previous = pts,time
        index = self.count+len(self.frames)
        self.frames.append({'frame': index, 'source_pts_seconds': pts, 'playback_seconds': time})
        self.inputs.append(crop(rgb,self.geometry['input']));self.popups.append(crop(rgb,self.geometry['popup']))
        self.games.append(rgb.copy())
        # Full-field spatial masks are independent of selected notes and accepted roles.
        small = cv2.resize(rgb,(MASK_FORMAT['width'],round(MASK_FORMAT['width']*bound['height']/bound['width'])),interpolation=cv2.INTER_AREA)
        planes = measurements(small)
        self.masks.append(np.packbits(np.stack([planes[k] for k in FIELDS]),axis=-1))
        if len(self.frames)>=FORMAT['chunk_frames']: self.flush()

    def flush(self):
        if not self.frames: return
        if shutil.disk_usage(self.directory).free < 32*1024**3:
            raise OSError('Independent acquisition stopped: less than 32 GiB free; published evidence is preserved')
        prefix = f'{len(self.chunks):05}'
        def lines(records):
            return ''.join(json.dumps(f,separators=(',',':'),allow_nan=False)+'\n' for f in records).encode()
        timeline = [{k:f[k] for k in ('frame','source_pts_seconds','playback_seconds')} for f in self.frames]
        payloads = {'frames.jsonl.gz': lines(timeline),
                    'game.rgb.gz': encode_rgb(self.games),
                    'input.rgb.gz': encode_rgb(self.inputs),
                    'popup.rgb.gz': encode_rgb(self.popups),
                    'masks.bin.gz': np.asarray(self.masks).tobytes()}
        files = {}
        for suffix, value in payloads.items():
            name = prefix+'.'+suffix;path = self.directory/name
            path.write_bytes(gzip.compress(value,compresslevel=6 if suffix.endswith('.rgb.gz')else 1,mtime=0));files[name] = digest(path)
        self.chunks.append({'first_frame': self.count, 'frames': len(self.frames), 'files': files,
                            'first_source_pts_seconds': self.frames[0]['source_pts_seconds'],
                            'last_source_pts_seconds': self.frames[-1]['source_pts_seconds']})
        self.count += len(self.frames)
        self.frames.clear();self.inputs.clear();self.popups.clear();self.masks.clear();self.games.clear()

    def finish(self):
        self.flush()
        if not self.count: raise ValueError('No original frames acquired')
        source_current(self.binding['source'])
        result = {'schema': 1, 'contract': self.binding, 'geometry': self.geometry, 'frame_count': self.count,
                  'capture_state': 'complete',
                  'recognition_state': 'not_evaluated',
                  'channels': {'notes': {'status': 'not_measured', 'artifact': 'notes/manifest.json',
                                         'representation': 'independent_detector_stage'},
                               'input_effects': {'status': 'available', 'representation': 'receptor_rgb_before_interpretation',
                                                'interpretation_status': 'not_measured',
                                                'physical_switch_calibration': None},
                               'popup': {'status': 'available', 'representation': 'rgb_before_ocr'},
                               'note_processing': {'status': 'available', 'representation': 'full_field_rgb_and_spatial_masks'}},
                  'masks': {'width': MASK_FORMAT['width'], 'height': round(MASK_FORMAT['width']*self.binding['source']['height']/self.binding['source']['width']),
                            'fields': FIELDS, 'encoding': 'packbits_big'}, 'chunks': self.chunks}
        save_input(self.directory/'manifest.json',result)
        return result


def acquire_pixels(data, directory, width=650):
    """One decode for independent pixels; a note detector cannot abort acquisition."""
    binding = contract(data,width);source_current(binding['source'])
    saved = read_manifest(directory,binding)
    if saved is not None: return saved
    pending = directory.with_name('.'+directory.name+'.'+uuid4().hex+'.build')
    writer = Writer(pending,binding)
    try:
        prior=read_manifest(directory)
        rgb_keys=('media','game_roi','start_seconds','end_seconds','width','height')
        reusable=prior and prior['contract']['format'].get('rgb_encoding')==FORMAT['rgb_encoding'] and all(
            prior['contract']['source'][k]==binding['source'][k]for k in rgb_keys)
        decoded=game_frames(directory,prior)if reusable else decode_frames(
            data['media'],data['start_seconds'],data['end_seconds'],data['game_roi'],width)
        with closing(decoded) if hasattr(decoded,'close') else nullcontext(decoded):
            for pts,time,rgb in decoded: writer.append(pts,time,rgb)
        result = writer.finish()
        old = directory.with_name('.'+directory.name+'.previous')
        if old.exists(): shutil.rmtree(old)
        if directory.exists(): directory.rename(old)
        try: pending.rename(directory)
        except BaseException:
            if old.exists(): old.rename(directory)
            raise
        if old.exists(): shutil.rmtree(old)
        return result
    finally:
        shutil.rmtree(pending,ignore_errors=True)


def acquire(data, directory, bank=None, width=650, jobs=None, *, detector=None):
    """Explicit orchestration: publish pixels first, then independent detections."""
    pixels=acquire_pixels(data,directory,width)
    if bank is not None or detector is not None:
        from piu_timeline.play.observations.notes import detect_notes
        notes=detect_notes(directory,bank,jobs=jobs,detector=detector)
        return {**pixels,'channels':{**pixels['channels'],'notes':{'status':'available','artifact':'notes/manifest.json',
                                                               'detector':notes['contract']['detector']}}}
    return pixels


def for_play(data):
    """Locate only a source/window/geometry-identical independent pixel store."""
    explicit=data.get('observations_directory');media=Path(data['media']['path'])
    if explicit:directory=Path(explicit)
    elif media.parent.name=='raw' and data.get('segment_number'):
        directory=media.parent.parent/'observations'/f'segment-{data["segment_number"]:03}'
    else:return None
    pixels=read_manifest(directory)
    if pixels is None:return None
    bound=pixels['contract']['source']
    if any(bound[k]!=data.get(k)for k in ('media','game_roi','layout','start_seconds','end_seconds')):return None
    if bound['width']!=data.get('analysis_width')or bound['height']!=data.get('analysis_height'):return None
    return directory
