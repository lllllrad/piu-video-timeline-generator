"""Select compatible immutable native-observation backups."""
import json
import math
import re
import shutil
from pathlib import Path

from piu_timeline.storage import read_analysis_header as cache_header

NATIVE_FRAME_FORMAT = {'schema':1,'notes':'normalized_lane_centers','time':'source_pts_and_playback'}


def validate_native_frame(frame,lane_count):
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
    if (not isinstance(frame.get('skin_observations'),list)
            or any(n.get('method')!='skin_image'for n in frame['notes'])
            or any(not isinstance(n,dict)or n.get('method')!='skin_image'for n in frame['skin_observations'])):
        raise ValueError('Native note observations require image-template evidence')


def tracking_notes(frame):
    """Resolve explicit compact-row bindings without discarding image alternatives."""
    rows=[]
    for note in frame['notes']:
        if 'skin_observation' not in note:
            rows.append(note)
            continue
        index=note['skin_observation'];observed=frame['skin_observations']
        if type(index)is not int or not 0<=index<len(observed):
            raise ValueError('Compact note has an invalid image-observation binding')
        image=observed[index]
        if image.get('role')=='hold_body' or any(k!='skin_observation'and(k not in image or image[k]!=value)
                                              for k,value in note.items()):
            raise ValueError('Compact note differs from its bound image observation')
        rows.append(image)
    return rows


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
    if options.get('note_skin')is None:return None
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
                        and all(key in cached for key in ('layout','analysis_height','frame_count'))):
                    return cached,path.parent
        except (OSError,ValueError):
            continue
    return None


def stage_saved_observations(root,final,pending,document,segment,start,end,options):
    """Pin immutable history through selection and copying, before native refitting."""
    from piu_timeline.storage import history_guard
    with history_guard(root,shared=True):
        saved=find_saved_observations(root,final,document,segment,start,end,options)
        if saved is None:return None
        cached,donor=saved
        stat=Path(document['media']['path']).stat()
        if (stat.st_size,stat.st_mtime_ns)!=(cached['media']['size_bytes'],cached['media']['mtime_ns']):return None
        shutil.copytree(donor,pending)
        return saved


