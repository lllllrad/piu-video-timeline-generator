"""Translate video observations with the already bounded common song phase."""
from hashlib import sha256
import math


def transcription_alignment(template,data,alignment):
    """Keep audio alignment immutable; use only matching phase calibration."""
    result=dict(alignment)
    proof={'method':'audio_alignment','song_start_seconds':alignment['song_start_seconds'],
           'uncertainty_seconds':alignment['uncertainty_seconds']}
    beat=data.get('beat_timing',{});phase=beat.get('song_phase_correction_seconds')
    if phase is None:return result,proof
    reference=beat.get('contract',{}).get('reference',{})
    expected=sha256(template.text().encode()).hexdigest()
    if (reference.get('status')!='available' or reference.get('sha256')!=expected
            or reference.get('song_start_seconds')!=alignment['song_start_seconds']
            or reference.get('alignment_uncertainty_seconds')!=alignment['uncertainty_seconds']
            or alignment.get('rate',1)!=1):
        return result,{**proof,'unused_phase_reason':'phase_reference_does_not_match_transcription_alignment'}
    bounds=beat.get('song_phase_range')
    if (type(phase)not in (int,float)or not math.isfinite(phase)
            or not isinstance(bounds,list)or len(bounds)!=2
            or any(type(t)not in (int,float)or not math.isfinite(t)for t in bounds)
            or not -alignment['uncertainty_seconds']<=bounds[0]<=phase<=bounds[1]<=alignment['uncertainty_seconds']
            or not any(g.get('status')=='restored'for g in beat.get('groups',[]))):
        raise ValueError('Invalid bounded common song phase for UCS transcription')
    origin=alignment['song_start_seconds']+phase
    uncertainty=max(phase-bounds[0],bounds[1]-phase)
    result.update(song_start_seconds=origin,uncertainty_seconds=uncertainty)
    return result,{'method':'bounded_common_song_phase','audio_song_start_seconds':alignment['song_start_seconds'],
                   'audio_uncertainty_seconds':alignment['uncertainty_seconds'],
                   'phase_correction_seconds':phase,'phase_range':list(bounds),
                   'song_start_seconds':origin,'uncertainty_seconds':uncertainty,
                   'timing_sha256':expected}
