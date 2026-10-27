"""Observed hold recognition and lane light transitions, never physical presses."""
from bisect import bisect_left, bisect_right

import numpy as np

from piu_timeline.play.holds.geometry import EDGE_POSITION_TOLERANCE


def recognition_window(data, hold, geometry):
    """Search for a visible response independently of chart endpoint uncertainty.

    A receptor response can remain visible as the trailing cap overlaps its row.
    This bounded association margin is not extra uncertainty on the cap's
    measured center crossing and cannot consume a separately detected next tap.
    """
    lower = hold['start_range'][1] if hold['start_censored'] else hold['start_range'][0]
    upper = hold['end_range'][1] if hold['end_range'] else hold['last_body_seconds']
    tail = hold['tail_note']
    if tail is not None:
        note = data['notes'][tail]
        speed = abs(note.get('velocity_pixels_per_second', 0))*geometry.note_scale
        if speed > 0:
            upper += EDGE_POSITION_TOLERANCE*geometry.spacing/speed
        following = [note['target_seconds']-note['prediction_uncertainty_seconds']
                     for index, note in enumerate(data['notes'])
                     if note['status'] == 'estimated' and note['lane'] == hold['lane']
                     and index not in hold['covered_notes']
                     and note['target_seconds'] > data['notes'][tail]['target_seconds']]
        if following:
            upper = min(upper, min(following))
    return [lower, max(lower, upper)]


def contextual_hold_support(data, frames, receptor, spacing, holds=(), *, require_hold_geometry=False):
    """Recover dim hold pulses using local change, body contact and a HUD update.

    Image acquisition requires established hold geometry; legacy color-body
    contact cannot corroborate its receptor evidence. These observations never
    become tap onsets or a physical press/release measurement.
    """
    times = [frame['playback_seconds'] for frame in frames]
    events = []
    for kind in ('combo_events', 'judgment_events'):
        for index, event in enumerate(data.get(kind, [])):
            lo, hi = event['lower_seconds'], event['upper_seconds']
            positive = (event.get('delta', 0) > 0 if kind == 'combo_events' else
                        event.get('label') in ('PERFECT', 'GREAT', 'GOOD', 'BAD'))
            if positive and 0 <= hi-lo <= .12:
                events.append((hi, {'kind': kind, 'index': index, 'range': [lo, hi]}))
    events.sort(key=lambda item: item[0])
    event_times = [item[0] for item in events]
    result = {}
    for fi, frame in enumerate(frames):
        values = frame.get('receptor_white_fraction')
        if values is None or frame.get('common_receptor_flash'):
            continue
        time = frame['playback_seconds']
        nearby = [item[1] for item in events[bisect_left(event_times, time-.04):bisect_right(event_times, time+.04)]]
        if not nearby:
            continue
        previous = frames[bisect_left(times, time-.15):bisect_right(times, time-.025)]
        if len(previous) < 3 or any('receptor_white_fraction' not in item for item in previous):
            continue
        for lane, value in enumerate(values):
            if value < .4:
                continue
            baseline = float(np.quantile([item['receptor_white_fraction'][lane] for item in previous], .25))
            others = [score for li, score in enumerate(values) if li != lane]
            if value-baseline < .16 or value-float(np.median(others)) < .2:
                continue
            body_contact = not require_hold_geometry and any(body['lane'] == lane and body['top'] <= receptor+.8*spacing
                               and body['bottom'] >= receptor+.6*spacing for body in frame['bodies'])
            # Geometry was resolved from neighboring source frames, independently
            # of this pulse. Require the certain interior, not an uncertain cap
            # envelope; a temporary hidden body need not be visible again here.
            established_hold = any(hold['lane'] == lane and hold['start_range'][1] <= time
                                   <= (hold['end_range'][0] if hold['end_range'] else hold['last_body_seconds'])
                                   for hold in holds)
            if not body_contact and not established_hold:
                continue
            result[(fi, lane)] = nearby
    return result


def recognition_segments(frames, frame_times, hold, contextual, window=None):
    """Bound lane-local sustained recognition by independently resolved geometry."""
    start, censored, lane = hold['start_range'], hold['start_censored'], hold['lane']
    last_time = hold['end_range'][1] if hold['end_range'] else hold['last_body_seconds']
    segments = []
    support_start = start[1] if censored else start[0]
    if window is not None:
        support_start, last_time = window
    # A flash can temporarily hide the body's colored pixels. Use the
    # independently recorded receptor state in neighboring native frames,
    # bounded by the reconstructed hold, not only frames with a body box.
    first_support = bisect_left(frame_times, support_start)
    support = frames[first_support:bisect_right(frame_times, last_time)]
    for fi, frame in enumerate(support, first_support):
        corroboration = contextual.get((fi, lane), [])
        if frame['receptor_lit'][lane] is not True and not corroboration:
            continue
        time, pts = frame['playback_seconds'], frame['source_pts_seconds']
        if segments and time - segments[-1]['upper_seconds'] <= .075:
            segments[-1].update(upper_seconds=time, last_source_pts_seconds=pts,
                                frames=segments[-1]['frames']+1)
        else:
            segments.append({'lower_seconds': time, 'upper_seconds': time,
                             'first_source_pts_seconds': pts, 'last_source_pts_seconds': pts, 'frames': 1})
        if corroboration:
            segment = segments[-1]
            segment['contextual_frames'] = segment.get('contextual_frames', 0)+1
            updates = segment.setdefault('corroborating_updates', [])
            for update in corroboration:
                if update not in updates:
                    updates.append(update)
    segments = [segment for segment in segments if segment['frames'] >= 2 or segment.get('contextual_frames')]
    return {'kind': 'sustained_recognition', 'segments': segments,
            'association_window': [support_start, last_time],
            'press_range': None, 'release_range': None,
            'recognition_envelope': [segments[0]['lower_seconds'], segments[-1]['upper_seconds']] if segments else None,
            'note': 'Filled receptor with a long body is hold-state evidence, not repeated presses or a measured switch release.'}


def receptor_runs(frames):
    runs, current, known, bridge, hidden_light = [], {}, {}, {}, {}
    previous_time = None
    for frame in frames:
        time = frame['playback_seconds']
        continuous = previous_time is None or 0 < time-previous_time <= .075
        for lane, lit in enumerate(frame['receptor_lit']):
            if not continuous:
                bridge[lane] = False
                hidden_light[lane] = False
            previous = current.get(lane)
            if previous is not None and previous['lit'] == lit and continuous:
                previous.update(end_seconds=frame['playback_seconds'], last_source_pts_seconds=frame['source_pts_seconds'], frames=previous['frames']+1)
            else:
                run = {'lane': lane, 'lit': lit, 'start_seconds': frame['playback_seconds'],
                       'end_seconds': frame['playback_seconds'], 'frames': 1,
                       'first_source_pts_seconds': frame['source_pts_seconds'], 'last_source_pts_seconds': frame['source_pts_seconds'],
                       'previous_seconds': previous['end_seconds'] if previous else None,
                       'previous_lit': previous['lit'] if previous else None}
                runs.append(run); current[lane] = run
                if lit is True:
                    before = known.get(lane)
                    run['onset_range'] = None
                    if (bridge.get(lane) and before is not None and before['lit'] is False
                            and time-before['end_seconds'] <= .15):
                        run['onset_range'] = [before['end_seconds'], time]
                        run['onset_source_pts_seconds'] = [before['last_source_pts_seconds'], frame['source_pts_seconds']]
                    if (hidden_light.get(lane) and before is not None and before['lit'] is True
                            and 0 < time-before['end_seconds'] <= .15):
                        # Corroborate the earlier observed onset, without filling
                        # unknown frames or inventing a second onset after flash.
                        before['corroborating_lit_frames_after_flash'] = 1
                        before['corroborating_source_pts_seconds'] = frame['source_pts_seconds']
                        before['corroborating_playback_seconds'] = time
            if lit is None:
                bridge[lane] = bridge.get(lane, False) and frame.get('common_receptor_flash', False)
                hidden_light[lane] = (continuous and frame.get('common_receptor_flash', False)
                                      and (hidden_light.get(lane, False) or previous is not None and previous['lit'] is True))
            else:
                known[lane] = current[lane]
                bridge[lane] = lit is False
                hidden_light[lane] = False
        previous_time = time
    return runs
