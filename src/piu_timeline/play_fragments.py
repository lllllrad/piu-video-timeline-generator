"""Join uniquely corroborated fragments of one interrupted visible trajectory."""
from bisect import bisect_right
from collections import defaultdict

import numpy as np


def stitch_tracks(tracks, receptor, spacing, motion=None, layout=None):
    from .play_tracking import Track, fit_track
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
            points = np.asarray(track.points[-12:])
            times = points[:, 0] - points[-1, 0]
            if times[0] > -.06:
                continue
            velocity, intercept = np.polyfit(times, points[:, 1], 1)
            residual = np.sqrt(np.mean((points[:, 1] - velocity*times - intercept)**2))
            if velocity >= -spacing or residual > .1*spacing:
                continue
            first = bisect_right(starts, points[-1, 0])
            last = bisect_right(starts, points[-1, 0]+.35)
            for successor in ordered[first:last]:
                other = tracks[successor]
                if len(other.points) < 2:
                    continue
                # Every initial reappearance must land on the same extrapolated
                # path. A different arrow in the same lane is not a continuation.
                def prediction(time):
                    displacement = motion.distance(track.points[-1][0], time) if motion else None
                    return track.points[-1][1]-displacement if displacement is not None else intercept+velocity*(time-points[-1, 0])
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
