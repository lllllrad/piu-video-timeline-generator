"""Explicit wire adapters for analysis-image trajectories (pixels, y downward).

Detection points belong to matched source images. Timing points belong to the
registered trajectory and require its registration proof for cross-track use.
These selectors never apply offsets, scaling, interpolation or timestamp edits.
"""


def detection_points(note):
    """Image ownership, masks, cap/body connectivity and pixel measurement."""
    registration=note.get('head_registration',{})
    if 'detected_points'not in note and(registration.get('coordinate_status')=='projected'
            or registration.get('coordinate_method')in('native_cap_measurements','native_image_anchors')):
        raise ValueError('Projected fit trajectory is missing original detected_points')
    return note['detected_points'] if 'detected_points' in note else note.get('points', [])


def fit_points(note):
    """Motion fitting and endpoint clocks; not a claim of registered cap centers."""
    return note.get('points', [])


def fit_trajectory(note):
    """Tagged input for relative motion; image ownership uses detection_points."""
    return {'purpose':'fit','frame':'analysis_image_pixels','vertical_axis':'down',
            'points':fit_points(note)}


def image_measurements(registration):
    """Read explicit measurement kinds through the common TypeScript adapter."""
    from piu_timeline.derived import call
    observed=[(r['note'],o)for r in registration.get('notes',[])for o in r['observations']]
    if len({(note,o['time'])for note,o in observed})!=len(observed):
        raise ValueError('Duplicate native image measurement identity')
    values=call('coordinateMeasurements.imagePositions',
                [{'sample':o,'trajectoryY':o.get('native_y_pixels')}for _,o in observed],registration.get('format',{}))
    return {(note,o['time']):value for (note,o),value in zip(observed,values,strict=True)}
