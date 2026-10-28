"""Interpret concrete chart effects without changing native evidence or grades."""


FORMAT = {'schema':1, 'revision':6}


def active_effects(data, kind):
    return [effect for effect in data.get('chart_policy',{}).get('gimmick_candidates',[])
            if effect['kind'] == kind and effect['review_status'] != 'rejected']


def contains(effect, lo, hi):
    return effect['playback_start_seconds'] <= lo and hi < effect['playback_end_seconds']


def visibility_modifier(data):
    from piu_timeline.derived import call,evidence_input
    source=evidence_input(data)
    if 'processing'in data.get('visual_channels',{}):
        source['visual_channels']['processing']=data['visual_channels']['processing']
    result=call('effects.visibilityModifier',source)
    if 'visual_channels'not in data:return data
    processing=result['visual_channels'].get('processing')
    if processing is None:return data
    return {**data,'visual_channels':{**data['visual_channels'],
            'processing':{**data['visual_channels'].get('processing',{}),**processing}}}


def simultaneous_increment(data):
    from piu_timeline.derived import call,evidence_input
    result=call('effects.simultaneousIncrement',evidence_input(data))
    fields=('combo_events','matches','coverage','conflicted_matches','association_view_format')
    return {**data,**{k:result[k]for k in fields if k in result}}


from piu_timeline.play.scroll_pauses import apply as scroll_pauses
from piu_timeline.play.scroll_speeds import apply as scroll_speeds
from piu_timeline.play.object_roles import KIND as ART_KIND,verify as verify_art

HANDLERS = {'scroll_pause':scroll_pauses, 'scroll_speed_change':scroll_speeds, 'suspected_visibility_modifier':visibility_modifier,
            'suspected_multi_increment':simultaneous_increment,ART_KIND:verify_art}


def apply_gimmicks(data, directory=None):
    for kind,handler in HANDLERS.items():
        data = handler(data)
        if kind=='scroll_speed_change' and directory is not None:
            from piu_timeline.play.scroll_pauses import refresh_processing
            data=refresh_processing(data,directory)
    policy = data.get('chart_policy')
    if policy:
        unsupported = [e['id'] for e in policy.get('gimmick_candidates',[])
                       if e['review_status'] != 'rejected' and e['kind'] not in HANDLERS]
        data = {**data,'chart_policy':{**policy,'gimmick_format':FORMAT,'unsupported_gimmicks':unsupported}}
    return data
