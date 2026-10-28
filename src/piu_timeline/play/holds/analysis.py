"""Hold analysis orchestration and projection; pixels, geometry and state are separate."""
from hashlib import sha256
import json

from piu_timeline.play.holds.features import FEATURE_FORMAT, acquire_features, feature_contract
from piu_timeline.play.holds.geometry import HoldGeometry, body_tracks, hold_start, register_caps, resolve_geometry, retain_hold
from piu_timeline.play.holds.state import contextual_hold_support, recognition_segments, recognition_window, receptor_runs
from piu_timeline.play.holds.continuity import CapContinuity

ASSOCIATION_FORMAT = {'schema': 1, 'revision': 43}


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def reconstruct(data, frames, diagnostics=None):
    """Resolve chart geometry first, then attach independent recognition spans."""
    from piu_timeline.play.object_roles import filter_frames
    frames=filter_frames(data,frames,bodies=True)
    geometry = HoldGeometry.from_analysis(data, FEATURE_FORMAT['width'])
    frames = register_caps(data, frames, geometry)
    frame_times = [frame['playback_seconds'] for frame in frames]
    continuity = CapContinuity(data, frames, geometry)
    holds = []
    for track in body_tracks(frames, geometry.spacing):
        native_components=[{'source_pts_seconds':p['pts'],'playback_seconds':p['time'],
                            'components':p.get('source_components',[]),'bounds':p.get('foreground_bounds')}
                           for p in track]
        hold = resolve_geometry(data, track, geometry)
        connection = continuity.check(track)
        if connection and connection['decision'] == 'disconnected_caps':
            hold = None
        if hold is None:
            extended = [p for p in track if p['long'] and p.get('stripe_support', 1) >= .72]
            if diagnostics is not None and len(extended) >= 4:
                cap_evidence = []
                for edge in ('top', 'bottom'):
                    for index in {p[edge+'_observed_cap_note'] for p in track if edge+'_observed_cap_note' in p}:
                        pts = [p['pts'] for p in track if p.get(edge+'_observed_cap_note') == index]
                        if len(set(pts)) >= 4:
                            cap_evidence.append({'edge': edge, 'note': index, 'source_pts_seconds': pts,
                                                 'timing_accepted':data['notes'][index]['status']=='estimated'})
                diagnostics.append({'lane': track[0]['lane'], 'reason': 'unresolved_hold_geometry',
                                    'visible_start_seconds': track[0]['time'], 'visible_end_seconds': track[-1]['time'],
                                    'source_pts_range': [track[0]['pts'], track[-1]['pts']],
                                    'native_component_evidence':native_components,
                                    'cap_continuity': connection,
                                    'cap_evidence': cap_evidence, 'observed_points': len(track)})
            continue
        hold['id'] = len(holds)
        hold['native_component_evidence']=native_components
        retain_hold(holds, hold)
    contextual = contextual_hold_support(data, frames, geometry.receptor, geometry.spacing, holds)
    for hold in holds:
        window = recognition_window(data, hold, geometry)
        hold['input'] = recognition_segments(frames, frame_times, hold, contextual, window)
    return holds


def augment_holds(data, output):
    from piu_timeline.play.channels import augment_channels,annotate_matches
    # Synthetic/legacy metadata without source stream geometry cannot reacquire
    # pixels; keep it explicit rather than invoking a decoder with invented data.
    if not data.get('media', {}).get('video_streams') or any('color' not in lane for lane in data.get('layout', {}).get('lanes', [])):
        return annotate_matches(data)
    from piu_timeline.play.holds.risk_cache import prepare as prepare_risk
    if data.get('skin_detector'):
        from piu_timeline.play.skins.clearance_cache import prepare
        data=prepare(data,output)
    contract = feature_contract(data)
    association = {'format': ASSOCIATION_FORMAT, 'notes': fingerprint(data['notes']),
                   'object_roles':fingerprint(data.get('object_interpretation',{}).get('effects',[])),
                   'hud_events': fingerprint({key: data.get(key, []) for key in ('combo_events', 'judgment_events')})}
    if data.get('skin_detector'):
        from piu_timeline.play.skins.holds import FORMAT as IMAGE_HOLD_FORMAT
        association['skin_images'] = data['skin_detector']['contract']
        association['image_hold_format'] = IMAGE_HOLD_FORMAT
        association['skin_role_clearance']=data.get('skin_role_evidence',{}).get('contract')
    path = output / 'holds.json'
    if path.is_file():
        saved = json.loads(path.read_text())
        if (saved.get('feature_contract') == contract and saved.get('association_contract') == association
                and all((output/name).is_file() for name in
                        ('hold-features.json','hold-frames.jsonl','processing-features.npz'))):
            return augment_channels(prepare_risk({**data, 'hold_analysis': saved},output), output)
    acquire_features(data, output)
    with (output / 'hold-frames.jsonl').open() as stream:
        frames = [json.loads(line) for line in stream]
    from piu_timeline.play.object_roles import filter_frames
    interpreted=filter_frames(data,frames,bodies=True)
    art=[{'source_pts_seconds':raw['source_pts_seconds'],'playback_seconds':raw['playback_seconds'],
          'observation':body,'role':'decorative_art'}for raw,view in zip(frames,interpreted,strict=True)
         for body in raw['bodies']if body not in view['bodies']]
    from piu_timeline.play.receptors import observations, reject_common_flashes
    frames = reject_common_flashes(frames, observations(data, output, frames))
    unresolved = []
    if data.get('skin_detector'):
        from piu_timeline.play.skins.holds import reconstruct_images
        native = filter_frames(data,[json.loads(line) for line in (output/'frames.jsonl').open()])
        holds = reconstruct_images(data, frames, native, unresolved)
    else:
        holds = reconstruct(data, frames, unresolved)
    result = {'feature_contract': contract, 'association_contract': association, 'holds': holds,
              'decorative_body_observations':art,
              'unresolved_tracks': unresolved, 'receptor_runs': receptor_runs(frames),
              'semantics': 'Long notes are sustained states. Hold ticks are not independent presses; release is not measured.'}
    pending = path.with_suffix('.build-json')
    pending.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    pending.replace(path)
    return augment_channels(prepare_risk({**data, 'hold_analysis': result},output), output, frames)


def chart_projection(data):
    from piu_timeline.derived import call,projection_input
    result=call('holdProjection.chartProjection',projection_input(data))
    fields=('notes','hold_analysis','note_type_diagnostics')
    return {**data,**{k:result[k]for k in fields if k in result}}


def presentation(data):
    """Consume retained geometry/channels in TypeScript; image proof preparation stays native."""
    from piu_timeline.derived import call,evidence_input,projection_input,recovery_input
    from piu_timeline.play.deferred_words import prepare_risk_proofs
    evidence=evidence_input(data);projection=projection_input(data)
    source={**recovery_input(data),**projection,
            **{k:data[k]for k in ('limitations','counter_judgment_labels','deferred_matches')if k in data},
            'visual_channels':{**evidence['visual_channels'],**projection['visual_channels']}}
    result=call('holdPresentation.present',source,prepare_risk_proofs(data))
    fields=('notes','matches','limitations','excluded_notes','miss_candidates','combo_events','judgment_events',
            'hold_tick_ambiguous_notes','recovered_pre_hold_notes','recovered_dense_notes',
            'recovered_lane_supported_notes','hold_analysis','coverage','note_type_diagnostics',
            'conflicted_matches','association_view_format')
    return {**data,**{k:result[k]for k in fields if k in result}}
