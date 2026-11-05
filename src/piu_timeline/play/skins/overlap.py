"""Recover obscured caps only behind positively measured neighboring artwork."""
import cv2
import numpy as np

from piu_timeline.play.skins.sampling import key
from piu_timeline.play.skins.visible_search import VisibleSearch

FORMAT={'schema':1,'method':'visible_cap_with_measured_foreground','proposal':'visible_mask_ssd_correlations',
        'required_cap_features':'fully_visible','foreground_basis':'visible_matching_cap_pixels',
        'minimum_visible_fraction':.25,'minimum_visible_width_fraction':.5,
        'minimum_visible_height_fraction':.2}


def proposals(searcher,template,bounds):
    """A position uses its actual 2-D visible footprint, not a fixed strip."""
    error,count=searcher.error(template,bounds)
    cap=next(r for r in template['regions']if r['name']=='cap');pixels=int(cap['mask'].sum())
    allowed=(count>=FORMAT['minimum_visible_fraction']*pixels)&(count<pixels)
    score=np.where(allowed,error/cap.get('maximum_error',.015),np.inf)
    minima=cv2.erode(score.astype('float32'),np.ones((3,3),dtype='uint8'))
    rows,cols=np.nonzero(np.isfinite(score)&(score<=1)&(score<=minima+1e-7))
    return list(zip(rows.tolist(),cols.tolist()))


def visible_support(image,template,known,left,top):
    support=template['cap_support'];h,w=support.shape
    hidden=known[top:top+h,left:left+w]&support
    visible=support&~hidden
    if not hidden.any()or visible.sum()<FORMAT['minimum_visible_fraction']*support.sum():return None
    ys,xs=np.nonzero(visible);full_y,full_x=np.nonzero(support)
    if ((xs.max()-xs.min()+1)<FORMAT['minimum_visible_width_fraction']*(full_x.max()-full_x.min()+1)
            or(ys.max()-ys.min()+1)<FORMAT['minimum_visible_height_fraction']*(full_y.max()-full_y.min()+1)):return None
    errors={}
    for region in template['regions']:
        if region['name']not in {'cap',*template.get('cap_features',[])}:continue
        a,b,c,d=region['box'];mask=region['mask'].astype(bool)&~known[top+b:top+d,left+a:left+c]
        if region['name']!='cap'and mask.sum()!=region['mask'].sum():return None
        if mask.sum()<FORMAT['minimum_visible_fraction']*region['mask'].sum():return None
        delta=image[top+b:top+d,left+a:left+c]-template['rgb'][b:d,a:c]
        error=float(np.square(delta[mask]).mean())
        if error>region.get('maximum_error',.015):return None
        errors[region['name']]=error
    return visible,hidden,errors


def positive_pixels(image,template,record):
    """Only pixels actually agreeing with a measured cap can hide another cap."""
    a,b,c,d=record['bounds_pixels']
    mask=template['cap_support'].copy()
    if 'visible_cap_runs'in record:
        mask[:]=False
        for y,x,z in record['visible_cap_runs']:mask[y,x:z]=True
    threshold=next(r.get('maximum_error',.015)for r in template['regions']if r['name']=='cap')
    return mask&(np.square(image[b:d,a:c]-template['rgb']).mean(axis=2)<=threshold)


def runs(mask):
    result=[]
    for row in np.flatnonzero(mask.any(axis=1)):
        edges=np.flatnonzero(np.diff(np.r_[False,mask[row],False]))
        result.extend([int(row),int(a),int(b)]for a,b in zip(edges[::2],edges[1::2]))
    return result


def recovery_record(detector,image,template,lane,left,top,known,owners):
    measured=visible_support(image,template,known,left,top)
    if measured is None:return None
    visible,hidden,errors=measured;h,w=template['mask'].shape
    unavailable=[name for name,value in errors.items()if value is None]
    for region in template['regions']:
        name=region['name']
        if name in errors:continue
        a,b,c,d=region['box']
        if (region['mask'].astype(bool)&known[top+b:top+d,left+a:left+c]).any():
            errors[name]=None;unavailable.append(name);continue
        # Positive connection/body checks retain their spatial cell thresholds.
        parts=region.get('_cells')or[region];values=[]
        for part in parts:
            a,b,c,d=part['box'];mask=part['mask'].astype(bool)
            values.append(float(np.square((image[top+b:top+d,left+a:left+c]-template['rgb'][b:d,a:c])[mask]).mean())if mask.any()else float('inf'))
        if all(np.isfinite(values)):errors[name]=max(values)
        else:errors[name]=None;unavailable.append(name)
    full=all(errors[r['name']]is not None and errors[r['name']]<=r.get('maximum_error',.015)for r in template['regions'])
    full=full and(template['role']!='tap'or template['tap_clearance'])
    ax,ay=template['anchor'];bounds=[left,top,left+w,top+h]
    sources=[]
    for record,mask in owners:
        a,b,c,d=record['bounds_pixels'];x,y,z,v=max(left,a),max(top,b),min(left+w,c),min(top+h,d)
        if x<z and y<v and(hidden[y-top:v-top,x-left:z-left]&mask[y-b:v-b,x-a:z-a]).any():
            sources.append({k:record[k]for k in('lane','template','bounds_pixels','x','y','sampling_phase_pixels','sampling_kernel','sampling_origin_pixels')if k in record})
    cap=next(r for r in template['regions']if r['name']=='cap')
    from piu_timeline.play.skins.detector import occluded_support
    hidden_hud=occluded_support(detector.layout,visible,left,top,detector.width,detector.height)
    return {'lane':lane,'x':(left+ax)/detector.width,'y':(top+ay)/detector.height,
        'role':template['role']if full else'unknown','template_role':template['role'],'template':template['id'],
        'classification_status':'full_pattern'if full else'cap_only','reason':'skin_image_overlap'if full else'skin_overlap_role_unresolved',
        'quality':float(1-errors['cap']/cap.get('maximum_error',.015)),'region_errors':errors,
        'bounds_pixels':bounds,'method':'skin_image','skin':detector.bank['skin'],
        'hud_region_overlap':hidden_hud,'visible_cap_runs':runs(visible),
        'occlusion_evidence':{'method':FORMAT['method'],'visible_cap_pixels':int(visible.sum()),
            'hidden_cap_pixels':int(hidden.sum()),'foreground_caps':sources},
        **({'unavailable_regions':unavailable}if unavailable else{}),
        **{k:template[k]for k in('sampling_phase_pixels','reference_scale_y','sampling_kernel','sampling_origin_pixels')if k in template}}


def recover(detector,image,seeds):
    """Monotone proof: each accepted cap adds new positively measured pixels.

    No lane, popup, timing estimate or expected chart count invents an anchor.
    Fully hidden caps have no visible proof and cannot be recovered here.
    """
    roots=detector.resolve([r for r in seeds if r['role']!='hold_body'])
    if not roots:return []
    known=np.zeros((detector.height,detector.width),dtype=bool);owners=[]
    for root in roots:
        template=detector.by_sampling[key(root)];mask=positive_pixels(image,template,root)
        a,b,c,d=root['bounds_pixels'];known[b:d,a:c]|=mask;owners.append((root,mask))
    recovered=[]
    while True:
        accepted=[];searcher=VisibleSearch(image,known)
        for lane,column in enumerate(detector.layout['lanes']):
            lane_roots=[r for r in roots if r['lane']==lane]
            for template in detector.templates:
                if template['lane_kind']!=lane%5 or template['role']=='hold_body':continue
                search=detector.search_bounds(column,template)
                if search is None:continue
                left,top,right,_=search;ay=template['anchor'][1]
                if not known[:,left:right].any():continue
                for row,col in proposals(searcher,template,search):
                    y=top+row+ay
                    if y>detector.layout.get('note_y_max',.95)*detector.height:continue
                    if any(abs(root['y']*detector.height-y)<detector.same_anchor_pixels for root in lane_roots):continue
                    record=recovery_record(detector,image,template,lane,left+col,top+row,known,owners)
                    if record is not None:accepted.append(record)
        if not accepted:break
        # Competing roles/phases see the same foreground. Only after their
        # independent comparisons do unique anchors become another layer.
        recovered.extend(accepted)
        additions=detector.resolve(accepted)
        for record in additions:
            template=detector.by_sampling[key(record)];mask=positive_pixels(image,template,record)
            a,b,c,d=record['bounds_pixels'];known[b:d,a:c]|=mask;owners.append((record,mask))
        roots.extend(additions)
    return recovered
