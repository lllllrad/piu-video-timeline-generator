"""A remote body tile cannot establish a hold-tick risk at the receptors."""
from collections import defaultdict

import numpy as np

from piu_timeline.play.skins.coverage import image_spans

FORMAT={'schema':1,'revision':1,'method':'positive_hold_regions_at_receptors',
        'minimum_body_height_spacing':1.25,'maximum_body_top_spacing':.75,
        'connection_receptor_band_spacing':.25}


def row_runs(support):
    runs=[]
    for row in np.flatnonzero(support.any(axis=1)):
        row=int(row)
        if runs and runs[-1][1]==row:runs[-1][1]=row+1
        else:runs.append([row,row+1])
    return runs


class BodyAtReceptor:
    def __init__(self,detector):
        self.spacing=detector.spacing;self.receptor=detector.layout['receptor_y']*detector.height
        self.rows={t['id']:row_runs(t['support'])for t in detector.templates}
        self.connections={}
        for t in detector.templates:
            support=np.zeros(t['mask'].shape,dtype=bool)
            for region in t['regions']:
                if region['name']=='connection':
                    a,b,c,d=region['box'];support[b:d,a:c]|=t['mask'][b:d,a:c].astype(bool)
            self.connections[t['id']]=row_runs(support)

    def __call__(self,observations):
        lanes=defaultdict(list);s=self.spacing;r=self.receptor
        band=FORMAT['connection_receptor_band_spacing']*s
        for image in observations:
            if image['role']in('hold_start','hold_body','hold_end'):
                lanes[image['lane']].extend(image_spans(image,self.rows))
            for pattern in [image,*image.get('alternatives',[])]:
                if (pattern.get('template_role',pattern['role'])in('hold_start','hold_end')
                        and pattern.get('classification_status')in('full_pattern','conflict')):
                    top=pattern['bounds_pixels'][1]
                    if any(top+a<=r+band and top+b>=r-band for a,b in self.connections[pattern['template']]):
                        return True
        for spans in lanes.values():
            runs=[]
            for a,b in sorted(spans):
                if runs and a<=runs[-1][1]+1:runs[-1][1]=max(runs[-1][1],b)
                else:runs.append([a,b])
            if any(a<=r+FORMAT['maximum_body_top_spacing']*s and b-a>=FORMAT['minimum_body_height_spacing']*s for a,b in runs):return True
        return False
