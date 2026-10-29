"""Select compatible immutable native-observation backups."""
import json
import math
import re

from piu_timeline.storage import read_analysis_header as cache_header

NATIVE_FRAME_FORMAT = {'schema':1,'notes':'normalized_lane_centers','time':'source_pts_and_playback'}


def is_outline_trace(path):
    """A filename alone cannot turn image-template observations into outlines."""
    try:
        with path.open()as stream:frame=json.loads(stream.readline())
        return (isinstance(frame,dict)and isinstance(frame.get('notes'),list)
                and 'skin_observations'not in frame
                and all(n.get('method')!='skin_image'for n in frame['notes']))
    except (OSError,ValueError,AttributeError,TypeError):return False


def detector_replay_available(cached,directory,options):
    return (options.get('note_skin')is not None or not cached.get('skin_detector')
            or is_outline_trace(directory/'frames.outline.jsonl'))


def validate_native_frame(frame,lane_count,*,allow_images=True):
    try:
        if (not math.isfinite(frame['source_pts_seconds'])or not math.isfinite(frame['playback_seconds'])
                or not isinstance(frame['notes'],list)
                or frame['combo']is not None and(type(frame['combo'])is not int or frame['combo']<0)
                or any(type(n['lane'])is not int or not 0<=n['lane']<lane_count
                       or not all(isinstance(n[k],(int,float))and math.isfinite(n[k])and 0<=n[k]<=1 for k in ('x','y'))
                       for n in frame['notes'])):
            raise ValueError('Unsupported saved native observation format')
    except (KeyError,TypeError)as error:
        raise ValueError('Unsupported saved native observation format')from error
    if not allow_images and('skin_observations'in frame or any(n.get('method')=='skin_image'for n in frame['notes'])):
        raise ValueError('Image-template observations cannot be replayed as contour observations')


def observation_settings_match(cached, document, segment, start, end, options):
    chart=segment.get('chart') or ''
    lanes=10 if re.match(r'^(?:HD|D)\d',chart) else 5 if re.match(r'^(?:S\d|VERY HARD )',chart) else None
    return (cached.get('media')==document.get('media') and cached.get('start_seconds')==start
            and cached.get('end_seconds')==end and cached.get('game_roi')==document.get('game_roi')
            and cached.get('analysis_width')==options.get('width',650)
            and cached.get('player')==options.get('player')
            and cached.get('participant_slots',[])==sorted(segment.get('players',{}))
            and (lanes is None or len(cached.get('layout',{}).get('lanes',[]))==lanes)
            and (options.get('layout') is None or cached.get('layout')==options['layout']))


def find_saved_observations(root, final, document, segment, start, end, options):
    # Backups are immutable snapshots, so another segment can reuse them safely
    # while the numbered presentation directories are being updated.
    paths=[p for p in root.glob('segment-*.previous-*/analysis.json') if p.parent!=final]
    for path in sorted(paths,key=lambda p:p.stat().st_mtime_ns,reverse=True):
        try:
            cached=cache_header(path)
            if (observation_settings_match(cached,document,segment,start,end,options)
                    and (path.parent/'frames.jsonl').is_file()
                    and cached.get('native_frame_format',NATIVE_FRAME_FORMAT)==NATIVE_FRAME_FORMAT):
                cached=json.loads(path.read_text())
                if (observation_settings_match(cached,document,segment,start,end,options)
                        and cached.get('native_frame_format',NATIVE_FRAME_FORMAT)==NATIVE_FRAME_FORMAT
                        and all(key in cached for key in ('layout','analysis_height','frame_count'))
                        and detector_replay_available(cached,path.parent,options)):
                    return cached,path.parent
        except (OSError,ValueError):
            continue
    return None


