"""Independent hold geometry and sustained-state producers over retained frames."""
from piu_timeline.play.observations.artifacts import cached, files, producer


def geometry(data, directory, frames, reconstruct):
    from piu_timeline.play.holds.features import feature_contract
    fields = ('notes', 'layout', 'analysis_width', 'analysis_height', 'game_roi', 'start_seconds',
              'scroll_motion', 'object_interpretation', 'skin_detector', 'skin_role_evidence')
    native_path = directory/'frames.base.jsonl'
    if not native_path.is_file():
        native_path = directory/'frames.jsonl'
    inputs = {'source': feature_contract(data), 'data': {k: data[k] for k in fields if k in data},
              'frames': [{k: f[k] for k in ('playback_seconds','source_pts_seconds','bodies','color_connections') if k in f} for f in frames],
              'native': files(directory, (native_path.name,)) if data.get('skin_detector') else None,
              'producer': producer('play/holds/stages.py', 'play/holds/reconstruction.py', 'play/holds/geometry.py', 'play/holds/continuity.py',
                                   'play/skins/holds.py', 'play/skins/temporal.py', 'play/skins/coverage.py',
                                   'play/skins/observations.py', 'play/object_roles.py')}

    def build():
        from piu_timeline.play.object_roles import filter_frames
        unresolved = []
        if data.get('skin_detector'):
            from piu_timeline.play.skins.holds import reconstruct_images
            import json
            with native_path.open() as stream:
                native = filter_frames(data, [json.loads(line) for line in stream])
            holds = reconstruct_images(data, frames, native, unresolved, include_state=False)
        else:
            holds = reconstruct(data, frames, unresolved, include_state=False)
        return {'holds': holds, 'unresolved_tracks': unresolved}

    return cached(directory, 'hold-geometry', inputs, build)


def sustained(data, directory, frames, geometry):
    from piu_timeline.play.holds.state import prepare_input
    from piu_timeline.derived import call
    from piu_timeline.play.observations.artifacts import save_input
    request = prepare_input(data, frames, geometry['holds'])
    save_input(directory/'hold-state-input.json', request)
    return {**geometry, **call('holdState.sustainedCached', request, str(directory))}
