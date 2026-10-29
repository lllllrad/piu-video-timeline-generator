"""Prepare source-bound endpoint errors for the independent rigid-length check."""
from piu_timeline.play.observations.coordinates import image_measurements,fit_points
from piu_timeline.derived import call


class LengthChecks:
    def __init__(self, data):
        self.notes = data['notes']
        self.records = {r['note']: {o['time']: o for o in r['observations']}
                        for r in data.get('head_registration', {}).get('notes', [])
                        if r.get('coordinate_method') == 'native_image_anchors'}
        self.measurements=image_measurements(data.get('head_registration',{}))
        self.cache = {}

    def check(self, head, tail):
        key = head, tail
        if key in self.cache:
            return self.cache[key]
        before, after = (dict(fit_points(self.notes[i])) for i in key)
        samples, unbound = [], []
        for time in sorted(before.keys() & after.keys()):
            sample = {'time': time, 'head_y': before[time], 'tail_y': after[time]}
            pts = []
            for index, edge, y in ((head, 'head', before[time]), (tail, 'tail', after[time])):
                record = self.records.get(index, {}).get(time)
                if record is None:
                    continue
                pts.append(record['source_pts_seconds'])
                position=self.measurements.get((index,time),{})
                if position.get('kind')=='native_cap_center'and abs(position['yPixels']-y)<1e-8:
                    sample[edge+'_uncertainty']=position['uncertaintyPixels']
            if not pts:
                unbound.append(time)
                continue
            if max(pts)-min(pts) > 1e-6:
                raise ValueError('Hold endpoints belong to different source frames')
            sample['source_pts_seconds'] = pts[0]
            samples.append(sample)
        self.cache[key] = {**call('holdExtent.intersect', samples), 'unregistered_playback_seconds': unbound}
        return self.cache[key]
