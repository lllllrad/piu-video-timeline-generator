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

FORMAT = {'schema': 1, 'revision': 2, 'chunk_frames': 64,
          'coordinates': 'normalized_full_game_top_left', 'input_extent_spacing': 2.0,
          'storage': 'timeline_and_spatial_masks'}


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


def digest(path):
    value = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): value.update(block)
    return {'size_bytes': path.stat().st_size, 'sha256': value.hexdigest()}


def read_manifest(directory, expected=None, verify=False):
    path = directory/'manifest.json'
    if not path.is_file(): return None
    saved = json.loads(path.read_text())
    if saved.get('schema') != 1 or saved.get('contract', {}).get('format') != FORMAT:
        raise ValueError('Unsupported independent observation manifest')
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


class Writer:
    """Bounded chunks share one original timeline across independent channels."""
    def __init__(self, directory, binding):
        self.directory, self.binding = directory, binding
        self.geometry = rectangles(binding['source'])
        self.frames, self.masks = [], []
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
                    'masks.bin.gz': np.asarray(self.masks).tobytes()}
        files = {}
        for suffix, value in payloads.items():
            name = prefix+'.'+suffix;path = self.directory/name
            path.write_bytes(gzip.compress(value,compresslevel=1,mtime=0));files[name] = digest(path)
        self.chunks.append({'first_frame': self.count, 'frames': len(self.frames), 'files': files,
                            'first_source_pts_seconds': self.frames[0]['source_pts_seconds'],
                            'last_source_pts_seconds': self.frames[-1]['source_pts_seconds']})
        self.count += len(self.frames)
        self.frames.clear();self.masks.clear()

    def finish(self):
        self.flush()
        if not self.count: raise ValueError('No original frames acquired')
        source_current(self.binding['source'])
        result = {'schema': 1, 'contract': self.binding, 'geometry': self.geometry, 'frame_count': self.count,
                  'capture_state': 'complete',
                  'recognition_state': 'not_evaluated',
                  'channels': {'notes': {'status': 'not_measured', 'artifact': 'notes/manifest.json',
                                         'representation': 'independent_detector_stage'},
                               'input_effects': {'status': 'not_measured', 'representation': 'original_source_recording',
                                                'physical_switch_calibration': None},
                               'popup': {'status': 'not_measured', 'representation': 'original_source_recording'},
                               'note_processing': {'status': 'available', 'representation': 'full_field_spatial_masks'}},
                  'masks': {'width': MASK_FORMAT['width'], 'height': round(MASK_FORMAT['width']*self.binding['source']['height']/self.binding['source']['width']),
                            'fields': FIELDS, 'encoding': 'packbits_big'}, 'chunks': self.chunks}
        save_input(self.directory/'manifest.json',result)
        return result


def acquire_pixels(data, directory, width=650):
    """Stream original video into compact masks; retain no decoded RGB frames."""
    binding = contract(data,width);source_current(binding['source'])
    saved = read_manifest(directory,binding)
    if saved is not None: return saved
    pending = directory.with_name('.'+directory.name+'.'+uuid4().hex+'.build')
    writer = Writer(pending,binding)
    try:
        decoded=decode_frames(data['media'],data['start_seconds'],data['end_seconds'],data['game_roi'],width)
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
    """Publish timeline/masks first, then independent detections from source media."""
    pixels=acquire_pixels(data,directory,width)
    if bank is not None or detector is not None:
        from piu_timeline.play.observations.notes import detect_notes
        notes=detect_notes(directory,bank,jobs=jobs,detector=detector)
        return {**pixels,'channels':{**pixels['channels'],'notes':{'status':'available','artifact':'notes/manifest.json',
                                                               'detector':notes['contract']['detector']}}}
    return pixels


def for_play(data):
    """Locate only a source/window/geometry-identical observation store."""
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
