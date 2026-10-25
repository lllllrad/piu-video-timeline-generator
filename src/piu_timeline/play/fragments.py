"""Join uniquely corroborated fragments of one interrupted visible trajectory."""
from bisect import bisect_right
from collections import defaultdict

import numpy as np


def stitch_tracks(tracks, receptor, spacing, motion=None, layout=None):
    from piu_timeline.play.tracking import Track, fit_track
    by_lane = defaultdict(list)
    for index, track in enumerate(tracks):
        by_lane[track.lane].append(index)
    candidates, incoming = defaultdict(list), defaultdict(list)
    for indices in by_lane.values():
        ordered = sorted(indices, key=lambda i: tracks[i].points[0][0])
        starts = [tracks[i].points[0][0] for i in ordered]
        for index in indices:
            track = tracks[index]
            if len(track.points) < 3 or fit_track(track, receptor, spacing, motion=motion, layout=layout)['status'] == 'estimated':
                continue
            usable = track.points
            if layout and layout.get('combo_roi'):
                # The bounding-box center can shift while a glyph intersects
                # the HUD. Use the intact approach below it to predict a unique
                # reappearance; retain all source points in the joined trace.
                x, y, w, h = layout['combo_roi']
                height = receptor/layout['receptor_y']
                lane_x = layout['lanes'][track.lane]['x']
                if x-.12 <= lane_x <= x+w+.12 and track.points[-1][1] <= (y+h)*height+spacing:
                    usable = [p for p in track.points if (y+h)*height+spacing < p[1]
                              < layout.get('note_y_max', .95)*height-.55*spacing]
            if len(usable) < 4:
                continue
            points = np.asarray(usable[-12:])
            times = points[:, 0] - points[-1, 0]
            if times[0] > -.06:
                continue
            velocity, intercept = np.polyfit(times, points[:, 1], 1)
            residual = np.sqrt(np.mean((points[:, 1] - velocity*times - intercept)**2))
            if velocity >= -spacing or residual > .1*spacing:
                continue
            first = bisect_right(starts, track.points[-1][0])
            last = bisect_right(starts, track.points[-1][0]+.35)
            for successor in ordered[first:last]:
                other = tracks[successor]
                if len(other.points) < 2 or other.points[0][0]-points[-1, 0] > .65:
                    continue
                # Every initial reappearance must land on the same extrapolated
                # path. A different arrow in the same lane is not a continuation.
                def prediction(time):
                    displacement = motion.distance(float(points[-1, 0]), time) if motion else None
                    return points[-1, 1]-displacement if displacement is not None else intercept+velocity*(time-points[-1, 0])
                if any(abs(y-prediction(time)) > .12*spacing
                       for time, y in other.points[:3]):
                    continue
                joined = Track(track.lane, track.points+other.points)
                if fit_track(joined, receptor, spacing, motion=motion, layout=layout)['status'] != 'estimated':
                    continue
                candidates[index].append((successor, joined))
                incoming[successor].append(index)
    used, result = set(), []
    for index, track in enumerate(tracks):
        if index in used:
            continue
        links = candidates.get(index, [])
        if len(links) == 1:
            successor, joined = links[0]
            if len(incoming[successor]) == 1 and successor not in used and successor > index:
                used.add(successor)
                result.append((joined, [index, successor]))
                continue
        result.append((track, [index]))
    return result
