"""Bind source-observed boundary-frame roles to one recording and timeline."""
from pathlib import Path

from piu_timeline.play.frames import TIME_EPSILON

FORMAT={'schema':1,'revision':1}


def prepare(data,directory,effect,frames):
    """Validate exact source references before resolving temporal ambiguity."""
    roles=[];seen=set();source_id=Path(directory).parents[1].name
    for evidence in effect.get('evidence',[]):
        annotations=evidence.get('object_role_frames',[])
        if not annotations:continue
        if (evidence['source_id']!=source_id or evidence['segment_number']!=data['segment_number']
                or evidence['player']!=data.get('player')):continue
        if (evidence['media_size_bytes'],evidence['media_mtime_ns'])!=(data['media']['size_bytes'],data['media']['mtime_ns']):
            raise ValueError('Artwork boundary-frame media identity differs from the recording')
        error=effect['boundary_uncertainty_seconds']+effect.get('alignment_uncertainty_seconds',0)
        boundaries=effect['playback_start_seconds'],effect['playback_end_seconds']
        for annotation in annotations:
            matches=[(i,f)for i,f in enumerate(frames)
                     if abs(f['playback_seconds']-annotation['playback_seconds'])<=TIME_EPSILON
                     and abs(f['source_pts_seconds']-annotation['source_pts_seconds'])<=TIME_EPSILON]
            if len(matches)!=1:raise ValueError('Artwork boundary annotation has no unique original source frame')
            index,frame=matches[0]
            if min(abs(frame['playback_seconds']-boundary)for boundary in boundaries)>error+TIME_EPSILON:
                raise ValueError('Artwork frame annotation lies outside the uncertain boundary')
            if index in seen:raise ValueError('Duplicate artwork boundary-frame annotation')
            seen.add(index)
            roles.append({'role':annotation['role'],'playback_seconds':frame['playback_seconds'],
                          'source_pts_seconds':frame['source_pts_seconds'],'native_frame':index,
                          'basis':'recording_bound_frame_annotation'})
    return {**effect,'source_frame_roles':roles}
