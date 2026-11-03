"""Reuse source-bound registered observations when only the native clock changes."""
import json
import shutil
from uuid import uuid4


def metadata_matches(cached,segment,result,display_delay_ms):
    return (all(cached.get(k)==segment.get(k)for k in ('song','chart','chart_identity'))
            and cached.get('display_delay_correction_ms',0)==display_delay_ms
            and cached.get('result_reference')==result)


def applicable(actual,expected):
    stored=actual.get('timing_format',{})
    return (stored!=expected and 'native_clock'in stored and 'native_clock'in expected
            and {k:v for k,v in stored.items()if k!='native_clock'}
                =={k:v for k,v in expected.items()if k!='native_clock'})


def refresh(cached,final,segment_number,display_delay_ms,source_media):
    from piu_timeline.play.stages import load_coordinates
    source=load_coordinates(cached,final)
    if source is None:return None
    registration=source.get('head_registration',{})
    if not any('native_cap_projection_uncertainty_pixels'in o
               for r in registration.get('notes',[])for o in r['observations']):return None
    pending=final.with_name(final.name+'.build-'+uuid4().hex[:8])
    shutil.copytree(final,pending)
    from piu_timeline.storage import relocate_evidence
    relocate_evidence(pending,pending,source=final)
    copied=json.loads((pending/'analysis.json').read_text())
    source=load_coordinates(copied,pending)
    if source is None:raise ValueError('Registered coordinate identity changed during replay staging')
    source.pop('_coordinate_source',None)
    print('Refitting saved registered coordinates; no frame replay, decoding or OCR.',flush=True)
    from piu_timeline.play.head_registration import refit_registered
    result=refit_registered(source,display_delay_ms)
    from piu_timeline.play.analysis import finish_play,TIMING_FORMAT
    if result.get('timing_format')!=TIMING_FORMAT:raise ValueError('Registered clock replay did not produce its declared contract')
    return finish_play(result,pending,final,segment_number,display_delay_ms,source_media,registered_coordinates=True)
