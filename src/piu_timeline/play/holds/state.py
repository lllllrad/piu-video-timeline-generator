"""Adapters for saved-observation sustained-state and receptor calculations."""
from piu_timeline.derived import call


def geometry_input(geometry):
    from piu_timeline.play.holds.geometry import EDGE_POSITION_TOLERANCE
    return {'receptor': geometry.receptor, 'spacing': geometry.spacing,
            'note_scale': geometry.note_scale, 'edge_tolerance': EDGE_POSITION_TOLERANCE}


def prepare_input(data, frames, holds):
    from piu_timeline.play.holds.geometry import HoldGeometry
    keys = ('notes', 'combo_events', 'judgment_events')
    source = {k: data[k] for k in keys if k in data}
    for key in ('combo_events', 'judgment_events'):
        source[key] = [{k: e[k] for k in ('lower_seconds', 'upper_seconds', 'delta', 'label') if k in e}
                       for e in source.get(key, [])]
    observed = [{k: f[k] for k in ('playback_seconds', 'source_pts_seconds', 'bodies', 'receptor_lit',
                                  'receptor_white_fraction', 'common_receptor_flash') if k in f} for f in frames]
    return {'data': source, 'frames': observed, 'holds': holds, 'geometry': geometry_input(HoldGeometry.from_analysis(data, 325)),
            'require_hold_geometry': bool(data.get('skin_detector'))}


def attach_state(data, frames, holds, *, require_hold_geometry=False):
    from piu_timeline.play.holds.geometry import HoldGeometry
    geometry = HoldGeometry.from_analysis(data, 325)
    source = {key: data[key] for key in ('notes', 'combo_events', 'judgment_events') if key in data}
    return call('holdState.attach', source, frames, holds, geometry_input(geometry), require_hold_geometry)


def recognition_window(data, hold, geometry):
    return call('holdState.recognitionWindow', {'notes': data['notes']}, hold, geometry_input(geometry))


def contextual_hold_support(data, frames, receptor, spacing, holds=(), *, require_hold_geometry=False):
    source = {key: data[key] for key in ('combo_events', 'judgment_events') if key in data}
    result = call('holdState.contextualSupport', source, frames, receptor, spacing, holds, require_hold_geometry)
    return {tuple(map(int, key.split(','))): value for key, value in result.items()}


def recognition_segments(frames, frame_times, hold, contextual, window=None):
    context = {','.join(map(str, key)): value for key, value in contextual.items()}
    return call('holdState.recognitionSegments', frames, frame_times, hold, context, window)


def receptor_runs(frames):
    return call('holdState.receptorRuns', frames)
