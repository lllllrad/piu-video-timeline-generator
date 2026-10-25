"""Keep repeated spatial visibility losses separate from note consumption."""


def pre_receptor_losses(records, receptor, spacing):
    """Find a stable visibility boundary using independent lanes and source times.

    This identifies a limitation of the observation, not its game/capture cause.
    It never creates chart exceptions or changes the receptor calibration.
    """
    candidates = []
    for record in records:
        if record['status'] != 'disappeared_near_receptor':
            continue
        last = next(s for s in reversed(record['samples']) if s['state'] == 'present')
        height = (last['y']-receptor)/spacing
        if height >= .65:
            candidates.append((record['range'][0], height, record))
    candidates.sort(key=lambda entry: entry[0])
    groups = []
    for entry in candidates:
        if (not groups or entry[0]-groups[-1][-1][0] > 3
                or max(e[1] for e in groups[-1]+[entry])-min(e[1] for e in groups[-1]+[entry]) > .25):
            groups.append([])
        groups[-1].append(entry)
    boundaries = []
    for group in groups:
        if len(group) < 8 or len({e[2]['lane'] for e in group}) < 3 or group[-1][0]-group[0][0] < 1:
            continue
        boundary = {'notes': [e[2]['note'] for e in group],
                    'last_visible_height_spacing': [min(e[1] for e in group), max(e[1] for e in group)],
                    'playback_range': [group[0][0], group[-1][2]['range'][1]]}
        for _, _, record in group:
            record['visibility_loss'] = {key: record.pop(key) for key in
                                         ('range', 'source_pts_seconds', 'confirmation_source_pts_seconds')}
            record.update(status='unresolved', reason='pre_receptor_visibility_boundary',
                          visibility_boundary=len(boundaries))
        boundaries.append(boundary)
    return boundaries
