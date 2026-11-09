"""Reuse source-bound unassigned channel rows independently of track interpretation."""
import json

from piu_timeline.play.observations.artifacts import files
from piu_timeline.storage import read_analysis_header


def retained(data,directory):
    path=directory/'visual-channels.json';analysis=directory/'analysis.json'
    if not path.is_file()or not analysis.is_file():return None
    saved=json.loads(path.read_text());binding=saved.get('contract',{})
    from piu_timeline.play.channels import CHANNEL_FORMAT
    if binding.get('format')!=CHANNEL_FORMAT:return None
    names=('frames.jsonl','frames.base.jsonl')
    if any(binding.get('traces',{}).get(name)!=signature for name,signature in files(directory,names).items()):return None
    previous=read_analysis_header(analysis)
    fields=('media','layout','analysis_width','analysis_height','game_roi','frame_count')
    if any(previous.get(key)!=data.get(key)for key in fields):return None
    channel=saved['channels'];timeline=channel['timeline']['frames'];popup=channel['popup'];motion=channel['motion']['observations']
    fields=popup['observation_fields'];rows=popup['observations'];expected=data.get('frame_timeline')
    if len(timeline)!=data['frame_count']or len(rows)!=len(timeline)or len(motion)!=len(timeline):
        raise ValueError('Saved channel projection has inconsistent frame counts')
    if expected is not None and timeline!=[[r['time'],r['source_pts']]for r in expected]:
        raise ValueError('Saved channel projection differs from original frame timeline')
    result=[]
    for (time,pts),hud,notes in zip(timeline,rows,motion,strict=True):
        if len(hud)!=len(fields):raise ValueError('Saved popup projection has inconsistent fields')
        values=dict(zip(fields,hud,strict=True))
        result.append({'playback_seconds':time,'source_pts_seconds':pts,
            **{key:values[key]for key in ('combo','combo_confidence','combo_read_mode','combo_recovered',
                                         'baseline_combo','baseline_combo_confidence')if key in values},
            'notes':[dict(zip(('lane','x','y','quality'),n,strict=True))for n in notes]})
    return result
