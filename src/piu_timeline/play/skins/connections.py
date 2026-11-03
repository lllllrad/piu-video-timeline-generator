"""Prove an endpoint connector using independently matched body-image pixels."""
import numpy as np

from piu_timeline.play.skins.sampling import key


def body_connections(data,frame,templates):
    """Only the full declared connector support can establish a hold role.

    A nearby body tile, a vertical bounding box or an unmeasured gap is not
    connectivity. Every connector pixel must have a positive body comparison.
    """
    height,width=data['analysis_height'],data['analysis_width']
    bodies={};sources={}
    for index,image in enumerate(frame.get('skin_observations',[])):
        if image['role']!='hold_body'or image.get('cap_subfeature'):continue
        lane=image['lane']
        if lane not in bodies:bodies[lane]=np.zeros((height,width),dtype=bool);sources[lane]=[]
        for comparison,pattern in enumerate([image,*image.get('alternatives',[])]):
            if pattern['role']!='hold_body'or pattern['classification_status']!='full_pattern':continue
            template=templates[key(pattern)];a,b,c,d=pattern['bounds_pixels']
            support=np.zeros(template['support'].shape,dtype=bool)
            for region in template['regions']:
                error=pattern.get('region_errors',{}).get(region['name'])
                if region['name']!='body'or error is None or not 0<=error<=region.get('maximum_error',.015):continue
                x0,y0,x1,y1=region['box'];support[y0:y1,x0:x1]|=region['mask'].astype(bool)
            if not support.any():continue
            bodies[lane][b:d,a:c]|=support
            sources[lane].append((index,comparison,(a,b,c,d),support))
    result=[]
    for image in frame.get('skin_observations',[]):
        if image['role']=='hold_body'or image['lane']not in bodies:continue
        observed=set()
        for pattern in [image,*image.get('alternatives',[])]:
            role=pattern.get('template_role',pattern['role'])
            if role in observed or role not in('hold_start','hold_end')or pattern['classification_status']!='cap_only':continue
            template=templates[key(pattern)]
            regions=[r for r in template['regions']if r['name']=='connection']
            if len(regions)!=1:continue
            region=regions[0];x0,y0,x1,y1=region['box'];mask=region['mask'].astype(bool)
            if not mask.any():continue
            left,top=pattern['bounds_pixels'][:2];a,b,c,d=left+x0,top+y0,left+x1,top+y1
            if not 0<=a<c<=width or not 0<=b<d<=height:continue
            if (mask&~bodies[image['lane']][b:d,a:c]).any():continue
            used=[];remaining=mask.copy()
            for index,comparison,(x,y,z,w),support in sources[image['lane']]:
                lo,hi=max(a,x),min(c,z);start,end=max(b,y),min(d,w)
                if lo<hi and start<end and (remaining[start-b:end-b,lo-a:hi-a]&support[start-y:end-y,lo-x:hi-x]).any():
                    used.append({'observation':index,'comparison':comparison})
                    remaining[start-b:end-b,lo-a:hi-a]&=~support[start-y:end-y,lo-x:hi-x]
                    if not remaining.any():break
            observed.add(role)
            result.append((image,pattern,{'role':role,'connector_bounds_pixels':[a,b,c,d],
                                        'connector_supported_pixels':int(mask.sum()),'body_comparisons':used}))
    return result
