"""Prepare source-bound endpoint errors for the independent rigid-length check."""
from math import isfinite
from piu_timeline.derived import call


class LengthChecks:
    def __init__(self, data):
        self.notes = data['notes']
        self.records = {r['note']: {o['time']: o for o in r['observations']}
                        for r in data.get('head_registration', {}).get('notes', [])
                        if r.get('coordinate_method') == 'native_image_anchors'}
        self.cache = {}

    def check(self, head, tail):
        key = head, tail
        if key in self.cache:
            return self.cache[key]
        before, after = (dict(self.notes[i]['points']) for i in key)
        samples, unbound = [], []
        for time in sorted(before.keys() & after.keys()):
            sample = {'time': time, 'head_y': before[time], 'tail_y': after[time]}
            pts = []
            for index, edge, y in ((head, 'head', before[time]), (tail, 'tail', after[time])):
                record = self.records.get(index, {}).get(time)
                if record is None:
                    continue
                pts.append(record['source_pts_seconds'])
                error = record.get('native_cap_coordinate_uncertainty_pixels')
                if (record.get('native_cap_reference_template') and error is not None and isfinite(error) and error > 0
                        and abs(record['native_y_pixels']-y) < 1e-5):
                    sample[edge+'_uncertainty'] = error
            if not pts:
                unbound.append(time)
                continue
            if max(pts)-min(pts) > 1e-6:
                raise ValueError('Hold endpoints belong to different source frames')
            sample['source_pts_seconds'] = pts[0]
            samples.append(sample)
        self.cache[key] = {**call('holdExtent.intersect', samples), 'unregistered_playback_seconds': unbound}
        return self.cache[key]
