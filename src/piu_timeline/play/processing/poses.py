"""Retain repeatedly supported native color shapes instead of averaging animation."""
import cv2
import numpy as np
from piu_timeline.play.processing.registration import FORMAT as REGISTRATION_FORMAT,centers

FORMAT={'schema':1,'minimum_support_frames':3,'minimum_similarity':.65,
        'minimum_displacement_spacing':.5,'registration':REGISTRATION_FORMAT}


def overlap(template,image):
    total=int(template.sum())+int(image.sum())
    return 2*int((template&image).sum())/total if total else 0.


def references(values,spacing):
    """Every added shape needs repeated, moving, same-head approach support."""
    poses=[];seen=set()
    for pts,y,mask in values:
        key=mask.tobytes()
        if key in seen:continue
        seen.add(key)
        support=[(p,h)for p,h,m in values if overlap(mask,m)>=FORMAT['minimum_similarity']]
        if len({p for p,_ in support})<FORMAT['minimum_support_frames']:continue
        lower,upper=min(h for _,h in support),max(h for _,h in support)
        if upper-lower<FORMAT['minimum_displacement_spacing']*spacing:continue
        poses.append({'mask':mask,'evidence':{'source_pts_seconds':pts,
            'anchor_y_pixels':y,'crop_center_y_pixels':round(y),
            'supporting_source_pts_seconds':[p for p,_ in support],'observed_y_range_pixels':[lower,upper]}})
    return poses


def compare(color,light,reference,y,radius,spacing):
    """Presence needs one verified shape; clear absence must reject every shape."""
    from piu_timeline.play.processing import visible_template
    models=[('median',reference['mask'],{}),*[(i,p['mask'],p.get('evidence',{}))for i,p in enumerate(reference.get('poses',[]))]]
    models=[(name,mask,evidence)for name,mask,evidence in models if mask.any()]
    measured=[];expected=0
    for name,mask,evidence in models:
        locations=centers(y,evidence);expected+=len(locations)
        for center in locations:
            cropped=visible_template(color,mask,center,radius)
            if cropped is None:continue
            slices,template,coverage=cropped
            image,white=color[slices],light[slices]
            measured.append({'pose':name,'score':overlap(template,image),'coverage':coverage,
                             'white':white,'template':template,'offset':center-round(y)})
    result={'state':'unknown','score':None,'unknown_reason':'image_boundary'}
    if not measured:return result
    best=max(measured,key=lambda p:p['score']);coverage=best['coverage']
    if best['white'].mean()>=.45:
        result.update(unknown_reason='white_effect')
    else:
        score=best['score'];state='unknown';reason='partial_shape'
        if score>=.65:state,reason='present',None
        elif len(measured)==expected and score<=.18:
            state,reason='absent',None
            coverage={k:min(p['coverage'][k]for p in measured)for k in coverage}
            halo_radius=max(1,round(.1*spacing))
            for part in measured:
                halo=cv2.dilate(part['white'].astype('uint8'),np.ones((2*halo_radius+1,2*halo_radius+1),dtype='uint8'))
                if part['white'].mean()>=.45 or halo[part['template']].mean()>=.3:state,reason='unknown','white_effect'
        elif len(measured)!=expected:reason='image_boundary'
        if coverage['area_fraction']<1 and state=='present':state,reason='unknown','partial_head_present'
        result.update(state=state,score=score,unknown_reason=reason,template_pose=best['pose'],
                      template_vertical_offset_pixels=best['offset'])
    if coverage['area_fraction']<1:
        result.update(template_coverage=coverage,confirmation_only=True)
    return result
