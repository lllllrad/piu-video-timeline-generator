"""Select declared geometry from independently moving, colored head outlines."""
from collections import defaultdict

import cv2
import numpy as np


def outline_centers(rgb, layout):
    """Geometry support uses colored outlines, not a particular note skin hue."""
    height,width = rgb.shape[:2]
    spacing=float(np.median(np.diff([lane['x']*width for lane in layout['lanes']])))
    white=((rgb.min(axis=2)>175)&(rgb.max(axis=2)-rgb.min(axis=2)<80)).astype('uint8')
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    colored=(hsv[:,:,1]>60)&(hsv[:,:,2]>90)
    contours,_=cv2.findContours(white,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour)
        if not (.65*spacing<w<1.25*spacing and .65*spacing<h<1.25*spacing):continue
        cy,cx=y+h/2,x+w/2
        if not layout['receptor_y']*height+.55*spacing<cy<layout.get('note_y_max',.95)*height:continue
        lane=min(range(len(layout['lanes'])),key=lambda i:abs(layout['lanes'][i]['x']*width-cx))
        if abs(layout['lanes'][lane]['x']*width-cx)>.2*spacing or colored[y:y+h,x:x+w].mean()<.12:continue
        yield lane,cy


class MovingHeadProfiles:
    def __init__(self, segment, player=None):
        from piu_timeline.play.layout import fixed_layout
        chart = segment.get('chart') or ''
        modes = ['D1'] if chart.startswith(('D', 'HD')) else ['S1'] if chart.startswith(('S', 'HS', 'VERY HARD')) else ['S1', 'D1']
        sides = [player] if player else [side for side in ('p1', 'p2') if side in segment.get('players', {})]
        if not sides:
            sides = ['p1', 'p2']
        self.profiles = {}
        for mode in modes:
            for side in sides:
                layout = fixed_layout({'chart':mode}, side)
                if layout is not None:
                    self.profiles[layout['profile']] = layout
        self.points = defaultdict(lambda: defaultdict(dict))

    def latest_support(self):
        return max((pts for lanes in self.points.values() for samples in lanes.values() for pts in samples),default=None)

    def observe(self, rgb, observation):
        pts = observation.get('source_pts_seconds')
        if pts is None:
            return None
        height, width = rgb.shape[:2]
        choices = []
        for profile, layout in self.profiles.items():
            spacing=float(np.median(np.diff([lane['x']*width for lane in layout['lanes']])))
            for lane,y in outline_centers(rgb, layout):
                self.points[profile][lane].setdefault(pts, []).append(y)
            lanes = self.points[profile]
            moving = [lane for lane, samples in lanes.items() if len(samples)>=3
                      and len({tuple(round(y,1) for y in sorted(values)) for values in samples.values()})>=3
                      and max(max(v) for v in samples.values())-min(min(v) for v in samples.values()) >= .5*spacing]
            # Multiple caps in one image, repeated copies of one PTS and a
            # stationary background cannot establish an independently moving field.
            if len(moving)>=2 and len(lanes)>=3 and max(moving)-min(moving)>=2:
                choices.append(layout)
        if len(choices) != 1:
            return None
        result = {**choices[0], 'method':'declared_geometry_with_moving_head_support'}
        result['geometry_support'] = {'kind':'colored_head_outlines',
            'lanes':{str(lane):sorted(samples) for lane,samples in self.points[result['profile']].items()}}
        return result
