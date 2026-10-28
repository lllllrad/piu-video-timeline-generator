"""Hold analysis orchestration and projection; pixels, geometry and state are separate."""
from hashlib import sha256
import json

from piu_timeline.play.holds.features import feature_contract
from piu_timeline.play.holds.reconstruction import reconstruct

ASSOCIATION_FORMAT = {'schema': 1, 'revision': 43}


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


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
    from piu_timeline.play.observations.acquisition import hold_observations
    frames = hold_observations(data, output)
    from piu_timeline.play.object_roles import filter_frames
    interpreted=filter_frames(data,frames,bodies=True)
    art=[{'source_pts_seconds':raw['source_pts_seconds'],'playback_seconds':raw['playback_seconds'],
          'observation':body,'role':'decorative_art'}for raw,view in zip(frames,interpreted,strict=True)
         for body in raw['bodies']if body not in view['bodies']]
    from piu_timeline.play.holds.stages import geometry as build_geometry, sustained
    geometry = build_geometry(data, output, frames, reconstruct)
    state = sustained(data, output, frames, geometry)
    result = {'feature_contract': contract, 'association_contract': association, **state,
              'decorative_body_observations':art,
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
            'recovered_lane_supported_notes','recovered_bounded_target_notes','hold_analysis','coverage','note_type_diagnostics',
            'conflicted_matches','association_view_format')
    return {**data,**{k:result[k]for k in fields if k in result}}
