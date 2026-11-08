"""Refute declared bright attachments at their own registered image positions."""
import math
from hashlib import sha256

import numpy as np

from piu_timeline.play.pixel_cache import FORMAT as PIXELS,measurements
from piu_timeline.play.screen_regions import occluders_at_bounds
from piu_timeline.play.skins.sampling import reference_scale


FORMAT={'schema':1,'method':'absence_inside_all_registered_bright_attachments',
        'registration_error_source_pixels':2,'raster_error_pixels':.5,
        'maximum_white_fraction':.05,'foreground':'other_compared_cap_pixels'}


class AttachmentGaps:
    def __init__(self,data,bank):
        self.data,self.bank=data,bank
        self.width=PIXELS['width']
        self.height=round(self.width*data['analysis_height']/data['analysis_width'])
        self.scale=reference_scale(bank,data['layout'],self.width,self.height)
        self.templates={t['id']:t for t in bank['templates']}
        self.caps={t['id']:self.cap_identity(t)for t in bank['templates']if t['role']!='hold_body'}
        self.attachments={}
        for kind in range(5):
            for role in ('hold_start','hold_end'):
                self.attachments[kind,role]=[self.prepare(t)for t in bank['templates']
                    if t['lane_kind']==kind and t['role']==role]

    @staticmethod
    def cap_identity(template):
        region=next(r for r in template['regions']if r['name']=='cap')
        a,b,c,d=region['box'];mask=template['mask'][b:d,a:c].astype(bool).copy()
        if 'comparison_boxes'in region:
            mask[:]=False
            for x,y,z,v in region['comparison_boxes']:mask[y-b:v-b,x-a:z-a]=template['mask'][y:v,x:z]
        rows,cols=np.nonzero(mask)
        x,y,z,v=int(cols.min()),int(rows.min()),int(cols.max())+1,int(rows.max())+1
        support=mask[y:v,x:z];rgb=np.where(support[:,:,None],template['rgb'][b+y:b+v,a+x:a+z],0)
        identity=sha256(str(support.shape).encode()+support.tobytes()+rgb.tobytes()).hexdigest()
        return identity,[a+x,b+y]

    def prepare(self,template):
        if template['id']not in self.bank['anchor_registrations']:return None
        color=measurements(template['rgb'])['relaxed_'+('blue','red','yellow','red','blue')[template['lane_kind']]]
        region=next(r for r in template['regions']if r['name']=='connection')
        a,b,c,d=region['box'];support=template['mask'][b:d,a:c].astype(bool).copy()
        if 'comparison_boxes'in region:
            support[:]=False
            for x,y,z,v in region['comparison_boxes']:support[y-b:v-b,x-a:z-a]=template['mask'][y:v,x:z]
        rows=np.flatnonzero((color[b:d,a:c]&support).any(axis=1));runs=[]
        for row in rows:
            row=int(row)+b
            if runs and runs[-1][1]==row:runs[-1][1]=row+1
            else:runs.append([row,row+1])
        if not runs:return None
        center=template.get('native_center_pixels',template['anchor_pixels'])
        return {'template':template['id'],'center':center,'horizontal':[a,c],'runs':runs}

    def foreground(self,frame,templates):
        from piu_timeline.play.skins.sampling import key
        from piu_timeline.play.skins.support import cap_support
        total=np.zeros((self.height,self.width),dtype='uint16');masks={}
        sx,sy=self.width/self.data['analysis_width'],self.height/self.data['analysis_height']
        for image in frame.get('skin_observations',[]):
            if image['role']=='hold_body':continue
            support=cap_support(templates[key(image)],image)
            a,b,_,_=image['bounds_pixels'];mask=np.zeros(total.shape,bool)
            for row in np.flatnonzero(support.any(axis=1)):
                edges=np.flatnonzero(np.diff(np.r_[False,support[row],False]))
                for lo,hi in zip(edges[::2],edges[1::2]):
                    mask[math.floor((b+row)*sy):math.ceil((b+row+1)*sy),
                         math.floor((a+lo)*sx):math.ceil((a+hi)*sx)]=True
            masks[id(image)]=mask;total+=mask
        return total,masks

    def measure(self,pattern,planes,obstacles):
        donor=self.templates[pattern['template']]
        if donor['id']not in self.bank['anchor_registrations']:return None
        reference=donor.get('native_center_pixels',donor['anchor_pixels'])
        center=[pattern['x']*self.width+(reference[0]-donor['anchor_pixels'][0])*self.scale,
                pattern['y']*self.height+(reference[1]-donor['anchor_pixels'][1])*self.scale]
        color=planes['relaxed_'+self.data['layout']['lanes'][pattern['lane']]['color']]
        results=[]
        for role,name in [('hold_end','clear_above'),('hold_start','clear_below')]:
            attachments=self.attachments[pattern['lane']%5,role]
            if not attachments or any(a is None for a in attachments):return None
            alternatives=[]
            for attachment in attachments:
                location=center;x,y=attachment['center'];basis='independent_native_centers'
                error=FORMAT['registration_error_source_pixels']*self.scale+FORMAT['raster_error_pixels']
                if self.caps[donor['id']][0]==self.caps[attachment['template']][0]:
                    # Identical source pixels establish a relative image offset
                    # without adding two independent engine-center conventions.
                    _,origin=self.caps[donor['id']];_,(x,y)=self.caps[attachment['template']]
                    location=[pattern['x']*self.width+(origin[0]-donor['anchor_pixels'][0])*self.scale,
                              pattern['y']*self.height+(origin[1]-donor['anchor_pixels'][1])*self.scale]
                    error=.5*self.width/self.data['analysis_width']+FORMAT['raster_error_pixels']
                    basis='identical_source_cap'
                lo,hi=attachment['horizontal']
                x0=math.floor(location[0]+(lo-x)*self.scale-error)
                x1=math.ceil(location[0]+(hi-x)*self.scale+error)
                if not 0<=x0<x1<=self.width:return None
                proof=None
                for lo,hi in attachment['runs']:
                    # A row must lie in the connector for every supported
                    # registration, rather than in a possible blank cap neck.
                    y0=math.ceil(location[1]+(lo-y)*self.scale+error)
                    y1=math.floor(location[1]+(hi-y)*self.scale-error)
                    for row in range(y0,y1):
                        bounds=[x0,row,x1,row+1]
                        if (row<self.data['layout']['receptor_y']*self.height
                                or row+1>self.data['layout'].get('note_y_max',.95)*self.height):continue
                        if occluders_at_bounds(self.data['layout'],bounds,self.width,self.height):continue
                        if obstacles[row,x0:x1].any():continue
                        white=float(planes['white'][row,x0:x1].mean())
                        if color[row,x0:x1].any()or white>=FORMAT['maximum_white_fraction']:continue
                        proof={'template':attachment['template'],'bounds_pixels':bounds,
                               'separating_rows_pixels':[row],'relaxed_foreground_pixels':0,
                               'white_fraction':white,'registration_error_pixels':error,'registration_basis':basis}
                        break
                    if proof is not None:break
                if proof is None:return None
                alternatives.append(proof)
            results.append({'region':name,'method':FORMAT['method'],'attachment_alternatives':alternatives})
        return results
