"""Reuse source-bound registered observations when only physical timing rules change."""
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
            and {k:v for k,v in stored.items()if k not in ('native_clock','shared_motion','counter_reader','counter_revision')}
                =={k:v for k,v in expected.items()if k not in ('native_clock','shared_motion','counter_reader','counter_revision')})


def refresh(cached,final,segment_number,display_delay_ms,source_media):
    from piu_timeline.play.stages import load_coordinates
    source=load_coordinates(cached,final)
    if source is None:return None
    pending=final.with_name(final.name+'.build-'+uuid4().hex[:8])
    shutil.copytree(final,pending)
    from piu_timeline.storage import relocate_evidence
    relocate_evidence(pending,pending,source=final)
    copied=json.loads((pending/'analysis.json').read_text())
    source=load_coordinates(copied,pending)
    if source is None:raise ValueError('Registered coordinate identity changed during replay staging')
    from piu_timeline.play.analysis import refresh_counter_observations,TIMING_FORMAT
    if any(cached.get('timing_format',{}).get(k)!=TIMING_FORMAT.get(k)for k in ('counter_reader','counter_revision')):
        from piu_timeline.play.stages import execute
        source={**source,**execute(pending,'counter-observations',lambda:refresh_counter_observations(copied,pending,replace_font=True),('counter-events.json',))}
    print('Reusing saved registered coordinates for downstream stages.',flush=True)
    from piu_timeline.play.stages import coordinate_context
    result={**coordinate_context(source),'timing_format':TIMING_FORMAT}
    from piu_timeline.play.analysis import finish_play
    return finish_play(result,pending,final,segment_number,display_delay_ms,source_media,registered_coordinates=True)
