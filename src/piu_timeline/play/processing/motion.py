"""A bounded visual path for persistence, independent of chart-time acceptance."""
from bisect import bisect_left


def observed_path(note, data, receptor, spacing, scale):
    """Do not treat a rejected chart estimate as an accepted motion clock.

    Use a locally verified trajectory when chart/shared reconstruction failed.
    It can support pixel inspection, never restore chart timing or input matches.
    """
    from piu_timeline.play.scroll_pauses import observed_path as paused_path
    paused=paused_path(note,data,receptor,spacing,scale)
    if paused is not None:
        return paused
    from piu_timeline.play.scroll_speeds import observed_path as speed_path
    measured=speed_path(note,data,receptor,spacing,scale)
    if measured is not None:
        return measured
    from piu_timeline.play.tracking import Track, fit_track
    points = note.get('points', [])
    path = {'supported': False, 'basis': 'unsupported_native_trajectory', 'velocity': 0, 'target': None}
    if len(points) < 4:
        return path
    # Shared displacement remains a visual measurement when beat assignment
    # fails. Interpolate its receptor crossing rather than reading chart timing.
    bridge=note.get('coordinate_bridge',{})
    phase=note.get('clock_target_phase',note.get('motion_target_phase'))
    chunk=bridge.get('to_chunk',note.get('motion_chunk'))
    samples = [s for s in data.get('scroll_motion', {}).get('samples', []) if s['chunk'] == chunk]
    if phase is not None and samples and note.get('timing_reconstruction', {}).get('status') != 'failed':
        crossing = next(((a,b) for a,b in zip(samples,samples[1:])
                         if a['phase'] <= phase < b['phase'] and 0 < b['time']-a['time'] <= .05), None)
        velocity = (-note['motion_clock']['velocity'] if bridge else note.get('velocity_pixels_per_second',0))*scale
        if crossing is not None and velocity < -spacing:
            a,b = crossing
            target = a['time']+(phase-a['phase'])/(b['phase']-a['phase'])*(b['time']-a['time'])
            times = [s['time'] for s in samples]
            original={s['time']:s for s in data.get('scroll_motion',{}).get('samples',[])
                      if bridge and s['chunk']==bridge['from_chunk']}
            def position(time):
                if time in original:return receptor+(note['motion_target_phase']-original[time]['phase'])*scale
                i = bisect_left(times, time-1e-6)
                if i == len(samples) or abs(times[i]-time) > 1e-6:
                    return None
                return receptor+(phase-samples[i]['phase'])*scale
            return {'supported':True, 'basis':'registered_native_displacement',
                    'velocity':velocity, 'target':target, 'position':position}
    fitted = fit_track(Track(note['lane'], [(t, y*scale) for t, y in points]), receptor, spacing)
    if fitted['status'] != 'estimated' or fitted['prediction_uncertainty_seconds'] > .05:
        return path
    velocity, target = fitted['velocity_pixels_per_second'], fitted['target_seconds']
    if velocity >= -spacing:
        return path
    return {'supported':True, 'basis':'bounded_native_trajectory', 'velocity':velocity, 'target':target,
            'position':lambda time: receptor+velocity*(time-target)}
