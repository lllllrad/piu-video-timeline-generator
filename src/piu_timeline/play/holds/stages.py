"""Independent hold geometry and sustained-state producers over retained frames."""
from piu_timeline.play.observations.artifacts import cached, files, producer


def image_geometry_contract():
    """Only measurement policies consumed by native image/endpoint geometry."""
    from piu_timeline.derived import CONTRACTS
    from piu_timeline.play.screen_regions import FORMAT
    return {'native_cap_registration':CONTRACTS['native_anchor'],
            'position_search':CONTRACTS['image_coordinates']['position_search'],'occlusion_regions':FORMAT}


def geometry(data, directory, frames, reconstruct):
    from piu_timeline.play.holds.features import feature_contract
    fields = ('notes', 'layout', 'analysis_width', 'analysis_height', 'game_roi', 'start_seconds',
              'scroll_motion', 'head_registration', 'object_interpretation', 'skin_detector', 'skin_role_evidence')
    native_path = directory/'frames.base.jsonl'
    if not native_path.is_file():
        native_path = directory/'frames.jsonl'
    image=bool(data.get('skin_detector'))
    values={k:data[k]for k in fields if k in data}
    if image:
        values['notes']=[{k:n[k]for k in ('lane','points','detected_points','duplicate_of')if k in n}for n in data['notes']]
        fields=('time','source_pts','phase','chunk','support','coordinate_status','native_displacement_interval')
        values['scroll_motion']={'samples':[{k:s[k]for k in fields if k in s}
                                           for s in data.get('scroll_motion',{}).get('samples',[])]}
    modules=['play/holds/stages.py','play/skins/holds.py','play/skins/temporal.py','play/skins/coverage.py','play/skins/occlusion.py',
             'play/skins/observations.py','play/skins/views.py','play/skins/extents.py','play/skins/detector.py','play/skins/bank.py',
             'derived/holds/extent.ts','derived/holds/image_motion.ts','derived/coordinates/measurements.ts','play/observations/coordinates.py','play/object_roles.py']if image else[
             'play/holds/stages.py','play/holds/reconstruction.py','play/holds/geometry.py','play/holds/continuity.py',
             'derived/holds/input.ts','play/object_roles.py']
    from piu_timeline.play.pixel_cache import source_contract
    inputs = {'source':source_contract(data)if image else feature_contract(data),'data':values,
              'frames':None if image else[{k:f[k]for k in ('playback_seconds','source_pts_seconds','bodies','color_connections')if k in f}for f in frames],
              'native': files(directory, (native_path.name,)) if data.get('skin_detector') else None,
              'producer': producer(*modules), 'derived':image_geometry_contract()if image else None}

    def build():
        from piu_timeline.play.object_roles import filter_frames
        unresolved = [];image_connections=[]
        if data.get('skin_detector'):
            from piu_timeline.play.skins.holds import measure_connections
            from piu_timeline.play.observations.trace import stream_frames
            with stream_frames(native_path, data.get('frame_count')) as native:
                interpreted=(filter_frames(data,[frame])[0]for frame in native)
                image_connections=measure_connections(data,interpreted,unresolved)
            return {'image_connections':image_connections,'unresolved_tracks':unresolved}
        else:
            holds = reconstruct(data, frames, unresolved, include_state=False)
        return {'holds':holds,'image_connections':image_connections,'unresolved_tracks':unresolved}

    measured=cached(directory,'hold-geometry',inputs,build)
    if not image:return measured
    from piu_timeline.derived import call
    return call('holdImages.projectCached',{'schema':1,'notes':data['notes'],'geometry':measured},str(directory))


def sustained(data, directory, frames, geometry):
    from piu_timeline.play.holds.state import prepare_input
    from piu_timeline.derived import call
    from piu_timeline.play.observations.artifacts import save_input
    request = prepare_input(data, frames, geometry['holds'])
    save_input(directory/'hold-state-input.json', request)
    return {**geometry, **call('holdState.sustainedCached', request, str(directory))}
