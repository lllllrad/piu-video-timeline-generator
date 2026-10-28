"""Prepare native visibility observations for the TypeScript continuity audit."""
from piu_timeline.derived import CONTRACTS,call
from piu_timeline.play.screen_regions import note_occluders
FORMAT=CONTRACTS['visibility']


def inputs(data):
    fields=('notes','layout','analysis_width','analysis_height','scroll_motion','scroll_pause_model','scroll_speed_model')
    return {**{k:data[k]for k in fields if k in data},
            'visual_channels':{'processing':data.get('visual_channels',{}).get('processing',{})}}


def continuity_diagnostics(data,frames):
    from piu_timeline.play.object_roles import filter_frames
    return call('visibility.continuity',inputs(data),filter_frames(data,frames),note_occluders(data.get('layout',{})))
