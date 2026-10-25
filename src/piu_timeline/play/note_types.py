"""Per-frame shape evidence; failing to prove a hold never proves a tap."""
from bisect import bisect_left
from collections import Counter

import cv2
import numpy as np

TYPE_FORMAT = {'schema': 1, 'revision': 2}


def shape(color, white, visibility, center, spacing):
    """Require a complete cap plus either a connected stripe or clear margins."""
    contours, _ = cv2.findContours(white.astype('uint8'), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    caps = []
    for contour in contours:
        x,y,w,h = cv2.boundingRect(contour)
        if (.65*spacing < w < 1.25*spacing and .65*spacing < h < 1.25*spacing
                and abs(y+h/2-center) < .2*spacing
                and color[y:y+h,x:x+w].mean() >= .12):
            caps.append((x,y,w,h))
    if not caps:
        return 'unknown', 'no_complete_cap_outline'
    _, labels, stats, _ = cv2.connectedComponentsWithStats(color.astype('uint8'), 8)
    for component, (x,y,w,h,_) in enumerate(stats[1:],1):
        if h <= 1.6*spacing or w < .16*spacing:
            continue
        stripe = (labels[y:y+h,x:x+w] == component).mean(axis=0).max()
        if stripe >= .8 and any(np.any(labels[cy:cy+ch,cx:cx+cw] == component) for cx,cy,cw,ch in caps):
            return 'hold', 'complete_cap_with_connected_color_stripe'
    # Beyond both ends of a complete outline, require visible background, not
    # an absence of colored pixels under a white/desaturated effect.
    for _,y,_,h in caps:
        pad = max(2, round(.15*spacing))
        if y-pad < 0 or y+h+pad > color.shape[0]:
            continue
        bands = [slice(y-pad,y), slice(y+h,y+h+pad)]
        if all(visibility[band].mean() >= .8 and not color[band].any()
               and white[band].mean() < .05 for band in bands):
            return 'tap', 'complete_cap_with_visible_separation_on_both_sides'
    return 'unknown', 'cap_margins_obscured_or_connected_shape_unresolved'


def body_type_observations(data, frames):
    """A single visible cap attached to an extended stripe is retained as proof."""
    from piu_timeline.play.holds.features import ui_regions
    from piu_timeline.play.holds.geometry import HoldGeometry, register_caps
    geometry = HoldGeometry.from_analysis(data,325)
    records = {}
    frames = [{**frame,'bodies':frame.get('bodies',[])} for frame in frames]
    for frame in register_caps(data,frames,geometry):
        for body in frame['bodies']:
            if not body['long'] or body.get('stripe_support',0) < .8:
                continue
            x = data['layout']['lanes'][body['lane']]['x']
            for edge in ('top','bottom'):
                index, y = body.get(edge+'_cap_note'), body.get(edge+'_cap_y')
                if index is None or abs(y-body[edge]) > .55*geometry.spacing:
                    continue
                if not geometry.receptor+1.3*geometry.spacing < y < data['layout'].get('note_y_max',.95)*geometry.height-.7*geometry.spacing:
                    continue
                if any(rx <= x <= rx+rw and ry*geometry.height-geometry.spacing <= y <= (ry+rh)*geometry.height+geometry.spacing
                       for rx,ry,rw,rh in ui_regions(data['layout'])):
                    continue
                records.setdefault(index,[]).append({'kind':'hold', 'reason':'observed_cap_attached_to_extended_body',
                    'source_note':index,'playback_seconds':frame['playback_seconds'],
                    'source_pts_seconds':frame['source_pts_seconds'],'y':y,'body_edge':edge,'trace':'hold-frames.jsonl',
                    'body_bounds':[body['top'],body['bottom']],'stripe_support':body['stripe_support']})
    return records


def observe_types(data, path, frames=()):
    """Measure only actual tracked positions away from processing and HUD cuts."""
    from piu_timeline.play.holds.features import ui_regions
    result = []
    body_evidence = body_type_observations(data,frames) if frames else {}
    if not path.is_file():
        return {'format': TYPE_FORMAT, 'available': False, 'notes': []}
    with np.load(path, allow_pickle=False) as saved:
        masks, times, pts = saved['masks'], saved['times'], saved['pts']
        top, half, height = int(saved['top']), int(saved['half']), int(saved['height'])
    width = 325
    scale = height/data.get('analysis_height',round(data['analysis_width']*data['game_roi'][3]/data['game_roi'][2]))
    spacing = float(np.median(np.diff([lane['x']*width for lane in data['layout']['lanes']])))
    receptor = data['layout']['receptor_y']*height
    for index, note in enumerate(data.get('notes', [])):
        observations = []
        x = data['layout']['lanes'][note['lane']]['x']
        for time,y in note.get('points', []):
            y *= scale
            if not receptor+1.3*spacing < y < receptor+2.5*spacing:
                continue
            if any(rx <= x <= rx+rw and ry*height-spacing <= y <= (ry+rh)*height+spacing
                   for rx,ry,rw,rh in ui_regions(data['layout'])):
                continue
            fi = bisect_left(times,time-1e-6)
            if fi == len(times) or abs(times[fi]-time) > 1e-6:
                continue
            color, white, visible = np.unpackbits(masks[fi,note['lane']],axis=-1)[...,:2*half+1].astype(bool)
            # Inspect a bounded neighborhood; remote notes cannot supply a stripe.
            a,b = max(0,round(y-top-1.1*spacing)), min(color.shape[0],round(y-top+1.1*spacing))
            kind, reason = shape(color[a:b],white[a:b],visible[a:b],y-top-a,spacing)
            observations.append({'kind':kind,'reason':reason,'playback_seconds':float(times[fi]),
                                 'source_pts_seconds':float(pts[fi]), 'y':y, 'source_note':index,'trace':'processing-features.npz'})
        observations.extend(body_evidence.get(index,[]))
        observations.sort(key=lambda o:(o['playback_seconds'],o['kind']))
        kinds = {o['kind'] for o in observations}-{'unknown'}
        status = 'conflict' if len(kinds)>1 else next(iter(kinds)) if kinds else 'unknown'
        result.append({'note':index,'status':status,'observations':observations})
    return {'format':TYPE_FORMAT,'available':True,'notes':result,
            'counts':dict(Counter(r['status'] for r in result)),
            'traces':['processing-features.npz','hold-frames.jsonl'],
            'pixel_coordinates':{'width':width,'height':height,'origin':'game_crop_top_left'}}


def project_types(data, notes, holds):
    """Combine identities without voting away a single contradictory observation."""
    records = data.get('visual_channels', {}).get('note_types', {}).get('notes')
    if records is None:
        return []
    by_note = {r['note']:r for r in records}
    groups = {h['display_note']: set(h['covered_notes']) | ({h['head_note']} if h['head_note'] is not None else set())
              for h in holds}
    hold_by_note = {h['display_note']:h for h in holds}
    timeline = {pts:time for time,pts in data.get('visual_channels', {}).get('timeline', {}).get('frames', [])}
    diagnostics = []
    for index, note in enumerate(notes):
        if note['status'] != 'estimated':
            continue
        members = groups.get(index,{index})
        observations = [o for n in sorted(members) for o in by_note.get(n,{}).get('observations',[])]
        hold = hold_by_note.get(index)
        if hold and hold.get('start_range'):
            contact = hold['start_range'][0]
            observations = [{**o,'kind':'unknown','observed_kind':'tap','reason':'hold_processing_remnant'}
                            if o['kind']=='tap' and o['playback_seconds'] >= contact else o for o in observations]
        kinds = {o['kind'] for o in observations}-{'unknown'}
        # A supported reconstructed hold also contradicts an isolated cap,
        # even if the cap was seen in another frame of the same identity.
        if index in groups:
            kinds.add('hold')
            hold = hold_by_note[index]
            pts_range = hold.get('source_pts_range')
            if pts_range and all(pts in timeline for pts in pts_range):
                observations.append({'kind':'hold', 'reason':'reconstructed_connected_body',
                                     'source_note':hold['head_note'], 'hold':hold['id'],
                                     'playback_seconds':timeline[pts_range[0]],
                                     'playback_end_seconds':timeline[pts_range[1]],
                                     'source_pts_seconds':pts_range[0], 'source_pts_range':pts_range})
        status = 'conflict' if len(kinds)>1 else next(iter(kinds)) if kinds else 'unknown'
        note['type_status'] = status
        note['type_evidence'] = observations
        note['type_unknown_reasons'] = dict(Counter(o['reason'] for o in observations if o['kind']=='unknown'))
        if status in ('unknown','conflict') or status == 'hold' and note.get('note_type') != 'hold':
            proof = [o for o in observations if o['kind'] != 'unknown']
            times = [t for o in proof for t in (o['playback_seconds'],o.get('playback_end_seconds',o['playback_seconds']))] or [t for t,_ in note.get('points',[])] or [note['target_seconds']]
            diagnostics.append({'note':index,'lane':note['lane'],
                                'reason':'note_type_conflict' if status == 'conflict' else 'note_type_unresolved',
                                'visible_start_seconds':min(times),'visible_end_seconds':max(times),
                                'observed_points':len(observations),'type_evidence':proof,
                                'type_unknown_reasons':note['type_unknown_reasons'],
                                'hold':note.get('hold_id')})
    return diagnostics
