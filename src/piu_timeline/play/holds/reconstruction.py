"""Native long-body geometry without judgment or sustained-state decisions."""
from piu_timeline.play.holds.features import FEATURE_FORMAT
from piu_timeline.play.holds.geometry import HoldGeometry, body_tracks, register_caps, resolve_geometry, retain_hold
from piu_timeline.play.holds.continuity import CapContinuity


def reconstruct(data, frames, diagnostics=None, *, include_state=True):
    """Resolve chart geometry first, then attach independent recognition spans."""
    from piu_timeline.play.object_roles import filter_frames
    frames=filter_frames(data,frames,bodies=True)
    geometry = HoldGeometry.from_analysis(data, FEATURE_FORMAT['width'])
    frames = register_caps(data, frames, geometry)
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
    if include_state:
        from piu_timeline.play.holds.state import attach_state
        holds = attach_state(data, frames, holds)
    return holds
