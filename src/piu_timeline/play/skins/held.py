"""A remote body tile cannot establish a hold-tick risk at the receptors."""
from collections import defaultdict

import numpy as np

from piu_timeline.play.skins.coverage import image_spans
from piu_timeline.play.skins.sampling import key

FORMAT={'schema':1,'revision':2,'method':'positive_hold_regions_at_receptors',
        'minimum_body_height_spacing':1.25,'maximum_body_top_spacing':.75,
        'connection_receptor_band_spacing':.25}
CAUSE_FORMAT={'schema':1,'revision':1,'detector':FORMAT}


def row_runs(support,origin=0):
    runs=[]
    for row in np.flatnonzero(support.any(axis=1)):
        row=int(row)+origin
        if runs and runs[-1][1]==row:runs[-1][1]=row+1
        else:runs.append([row,row+1])
    return runs


class BodyAtReceptor:
    def __init__(self,detector):
        self.spacing=detector.spacing;self.receptor=detector.layout['receptor_y']*detector.height
        self.rows={key(t):row_runs(t['support'],t.get('sampling_origin_pixels',[0,0])[1])for t in detector.templates}
        self.connections={}
        for t in detector.templates:
            support=np.zeros(t['mask'].shape,dtype=bool)
            for region in t['regions']:
                if region['name']=='connection':
                    a,b,c,d=region['box'];support[b:d,a:c]|=region['mask'].astype(bool)
            self.connections[key(t)]=row_runs(support,t.get('sampling_origin_pixels',[0,0])[1])

    def __call__(self,observations):
        return bool(self.explain(observations))

    def explain(self,observations):
        """Retain every positive cause; a first known owner cannot hide another."""
        lanes=defaultdict(list);s=self.spacing;r=self.receptor
        band=FORMAT['connection_receptor_band_spacing']*s;causes=[]
        for index,image in enumerate(observations):
            if image.get('cap_subfeature'):continue
            if image['role']in('hold_start','hold_body','hold_end'):
                lanes[image['lane']].extend((a,b,index)for a,b in image_spans(image,self.rows))
            for pattern in [image,*image.get('alternatives',[])]:
                if (pattern.get('template_role',pattern['role'])in('hold_start','hold_end')
                        and pattern.get('classification_status')in('full_pattern','conflict')):
                    top=pattern['bounds_pixels'][1]-pattern.get('sampling_origin_pixels',[0,0])[1]
                    spans=[(top+a,top+b)for a,b in self.connections[key(pattern)]
                           if top+a<=r+band and top+b>=r-band]
                    if spans:causes.append({'kind':'cap_connection','lane':image['lane'],'image_indices':[index],
                        'template':pattern['template'],'vertical_range_pixels':[min(a for a,b in spans),max(b for a,b in spans)]})
        for lane,spans in lanes.items():
            runs=[]
            for a,b,index in sorted(spans):
                if runs and a<=runs[-1][1]+1:
                    runs[-1][1]=max(runs[-1][1],b);runs[-1][2].add(index)
                else:runs.append([a,b,{index}])
            for a,b,indices in runs:
                if a<=r+FORMAT['maximum_body_top_spacing']*s and b-a>=FORMAT['minimum_body_height_spacing']*s:
                    causes.append({'kind':'body_run','lane':lane,'image_indices':sorted(indices),'vertical_range_pixels':[a,b]})
        return causes
