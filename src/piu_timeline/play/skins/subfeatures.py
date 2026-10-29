"""A body-pattern match wholly inside positively compared cap artwork is a part."""
import numpy as np

from piu_timeline.play.skins.sampling import key


def account(images,templates,width,height):
    if not any(o['role']=='hold_body'for o in images):return images
    caps=[];unions={}
    for index,image in enumerate(images):
        if image['role']=='hold_body':continue
        parts=[]
        for pattern in [image,*image.get('alternatives',[])]:
            model=templates[key(pattern)];support=model['cap_support']
            if not support.any():continue
            a,b,c,d=pattern['bounds_pixels']
            if image['lane']not in unions:unions[image['lane']]=np.zeros((height,width),dtype=bool)
            union=unions[image['lane']]
            union[b:d,a:c]|=support;parts.append((a,b,c,d,support))
        caps.append((index,image['lane'],parts))
    for image in images:
        if image['role']!='hold_body':continue
        image.pop('cap_subfeature',None)
        union=unions.get(image['lane'])
        if union is None:continue
        proof=[]
        for comparison,pattern in enumerate([image,*image.get('alternatives',[])]):
            model=templates[key(pattern)];support=model['support'];a,b,c,d=pattern['bounds_pixels']
            if not support.any()or (support&~union[b:d,a:c]).any():break
            owners=[]
            for index,lane,parts in caps:
                if lane!=image['lane']:continue
                for x,y,z,w,mask in parts:
                    lo,top,hi,bottom=max(a,x),max(b,y),min(c,z),min(d,w)
                    if lo<hi and top<bottom and (support[top-b:bottom-b,lo-a:hi-a]&mask[top-y:bottom-y,lo-x:hi-x]).any():
                        owners.append(index);break
            proof.append({'comparison_index':comparison,'supported_pixels':int(support.sum()),'cap_observation_indices':owners})
        else:image['cap_subfeature']={'method':'compared_pixels_within_cap_artwork','comparisons':proof}
    return images
