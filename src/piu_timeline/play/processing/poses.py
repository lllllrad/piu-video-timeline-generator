"""Retain repeatedly supported native color shapes instead of averaging animation."""
import cv2
import numpy as np
from piu_timeline.derived import CONTRACTS
from piu_timeline.play.processing.registration import FORMAT as REGISTRATION_FORMAT,centers

FORMAT={'schema':1,'revision':2,'presence_selection':'best_clear_supported_shape',
        'minimum_support_frames':CONTRACTS['cap_coverage']['minimum_reference_frames'],'minimum_similarity':CONTRACTS['cap_coverage']['minimum_similarity'],
        'minimum_displacement_spacing':CONTRACTS['cap_coverage']['minimum_displacement_spacing'],'registration':REGISTRATION_FORMAT}


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


def compare(color,light,reference,y,radius,spacing,*,retain_support=False):
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
                             'white':white,'template':template,'offset':center-round(y),
                             'top':slices[0].start,'reference':evidence})
    result={'state':'unknown','score':None,'unknown_reason':'image_boundary'}
    if not measured:return result
    # Presence needs one supported, clear comparison. The highest color score
    # may use a different crop with a white flash along its edge; that crop
    # cannot veto another registered shape which meets both existing limits.
    positive=[p for p in measured if p['score']>=.65 and p['white'].mean()<.45]
    best=max(positive or measured,key=lambda p:p['score']);coverage=best['coverage']
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
    observed=[p for p in positive if isinstance(p['pose'],int)and p['coverage']['area_fraction']==1]
    if retain_support and result['state']=='present'and observed:
        cap=max(observed,key=lambda p:p['score'])
        runs=[]
        for row in np.flatnonzero(cap['template'].any(axis=1)):
            row=int(row)+cap['top']
            if runs and runs[-1][1]==row:runs[-1][1]=row+1
            else:runs.append([row,row+1])
        result['positive_cap_support']={'intervals_pixels':runs,'box_pixels':[cap['top'],cap['top']+cap['template'].shape[0]],
                                        'reference':cap['reference'],'score':cap['score'],'template_pose':cap['pose']}
    if coverage['area_fraction']<1:
        result.update(template_coverage=coverage,confirmation_only=True)
    return result
