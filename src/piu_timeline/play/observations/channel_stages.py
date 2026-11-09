"""Cache native per-note measurements independently of popup/input association."""
from piu_timeline.play.observations.artifacts import cached, files, producer


def measurement_data(data):
    keys = ('media', 'start_seconds', 'end_seconds', 'layout', 'game_roi', 'analysis_width', 'analysis_height',
            'notes', 'scroll_motion', 'scroll_pause_model', 'scroll_speed_model', 'object_interpretation',
            'skin_detector', 'skin_role_evidence')
    geometry = data.get('hold_analysis', {})
    return {**{k: data[k] for k in keys if k in data},
            'hold_analysis': {'holds': [{k: v for k, v in h.items() if k != 'input'} for h in geometry.get('holds', [])],
                              'unresolved_tracks': geometry.get('unresolved_tracks', [])}}


def processing(data, directory, observe):
    source = measurement_data(data)
    inputs = {'data': source, 'files': files(directory, ('processing-features.npz', 'native-features/manifest.json')),
              'producer': producer('play/observations/channel_stages.py', 'play/processing/__init__.py', 'play/processing/motion.py',
                                   'play/processing/templates.py', 'play/processing/poses.py', 'play/processing/passage.py'),
              'derived': derived_motion_contract()}
    return serialized(directory,'processing',inputs,lambda:cached(directory,'processing',inputs,lambda:observe(source,directory/'processing-features.npz')))


def derived_motion_contract():
    from piu_timeline.derived import call
    return call('stageInputs.processingProducer')


def note_types(data, directory, native, frames, observe):
    source = {k: v for k, v in measurement_data(data).items() if k not in ('scroll_motion', 'scroll_pause_model', 'scroll_speed_model')}
    source['hold_analysis'].pop('holds')
    baseline = 'frames.base.jsonl' if (directory/'frames.base.jsonl').is_file() else 'frames.jsonl'
    inputs = {'data': source,
              'frames': [{k: f[k] for k in ('playback_seconds', 'source_pts_seconds', 'bodies', 'color_connections') if k in f} for f in frames],
              'native': files(directory, (baseline,)),
              'files': files(directory, ('processing-features.npz', 'appearance-features.npz')),
              'producer': producer('play/observations/channel_stages.py', 'play/note_types.py', 'play/holds/type_links.py', 'play/holds/geometry.py', 'play/skins/observations.py','play/skins/views.py')}
    if data.get('skin_detector'):
        from piu_timeline.play.skins.observations import producer_contract
        inputs['producer'].update(producer_contract())
    result=serialized(directory,'note-types',inputs,lambda:cached(directory,'note-types',inputs,lambda:observe(source)))
    # A first acquisition may have created the appearance cache. Bind the same
    # result to the finalized measurement inputs without performing it twice.
    finalized = {**inputs, 'files': files(directory, ('processing-features.npz', 'appearance-features.npz'))}
    if finalized != inputs:
        cached(directory, 'note-types', finalized, lambda: result)
    return result


def serialized(directory,name,inputs,compute):
    from piu_timeline.play.observations.serialized import reuse
    dependencies=('coordinates.json','physical-timing.json','beat-result.json','holds.json',
                  'hold-frames.jsonl','object-interpretation.json','skin-role-evidence.json')
    if not all((directory/file).is_file()for file in dependencies):return compute()
    for file in ('processing-features.npz','appearance-features.npz','native-features/manifest.json'):
        if(directory/file).is_file():dependencies+=file,
    source=inputs['data']
    parameters={'scroll_pause_model':source.get('scroll_pause_model'),'scroll_speed_model':source.get('scroll_speed_model'),
                'native':inputs.get('native'),'derived':inputs.get('derived')}
    return reuse(directory,name,dependencies,parameters,inputs['producer'],compute)
