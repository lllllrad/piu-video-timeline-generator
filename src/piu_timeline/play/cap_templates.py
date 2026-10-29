"""Register connected caps against independently observed isolated silhouettes."""
from collections import defaultdict
from piu_timeline.play.observations.coordinates import detection_points

import cv2
import numpy as np

FORMAT={'schema':1,'revision':5,'minimum_independent_heads':2,'cluster_similarity':.94,
        'maximum_clusters_per_lane':128,'maximum_templates_per_lane':12,
        'minimum_similarity':.90,'different_offset_margin':.04,'distinct_offset_pixels':.75,
        'vertical_search_pixels':4,'horizontal_search_pixels':1,'minimum_truncated_rows':3,
        'numeric_epsilon_pixels':1e-9}


def dice(first,second):
    return 2*np.count_nonzero(first&second)/max(1,int(first.sum()+second.sum()))


def learn(records,pixels,lookup):
    """A reference needs independent heads at the same canonical alignment."""
    masks,columns=pixels['masks'],int(pixels['columns']);exact=defaultdict(dict);groups=defaultdict(list)
    for record in records:
        if record['status']!='registered':continue
        for sample in record['observations']:
            if abs(sample['offset_pixels']-record['offset_pixels'])>1+FORMAT['numeric_epsilon_pixels']:continue
            indices=lookup.get((round(sample['time'],6),record['lane']),[])
            indices=[i for i in indices if abs(float(pixels['pts'][i])-sample['source_pts_seconds'])<1e-6
                     and abs(float(pixels['ys'][i])-sample['detected_y_pixels'])<1e-5]
            if len(indices)!=1:continue
            i=indices[0];white=np.unpackbits(masks[i,1],axis=-1)[...,:columns].astype(bool)
            x,y,w,h=sample['outer_bounds_in_patch'];image=white[y:y+h,x:x+w].copy()
            support={'note':record['note'],'source_pts_seconds':sample['source_pts_seconds'],
                     'time':sample['time'],'outer_bounds_in_patch':[x,y,w,h]}
            key=(w,h,np.packbits(image).tobytes());lane=record['lane']
            if key not in exact[lane]:
                exact[lane][key]={'image':image,'bounds':[x,y,w,h],
                    'reference':support,'support':{},'count':0}
            exact[lane][key]['support'].setdefault(record['note'],support)
            exact[lane][key]['count']+=1
    # Prioritize repeatedly observed pixels before bounding cluster storage;
    # chronological truncation would privilege only the opening silhouettes.
    for lane,candidates in exact.items():
        for candidate in sorted(candidates.values(),key=lambda c:c['count'],reverse=True):
            image=candidate['image']
            cluster=next((g for g in groups[lane] if image.shape==g['image'].shape
                          and dice(image,g['image'])>=FORMAT['cluster_similarity']),None)
            if cluster is not None:
                cluster['count']+=candidate['count'];cluster['support'].update(candidate['support'])
            elif len(groups[lane])<FORMAT['maximum_clusters_per_lane']:
                groups[lane].append(candidate)
    banks={lane:sorted((g for g in gs if len(g['support'])>=FORMAT['minimum_independent_heads']),
                       key=lambda g:g['count'],reverse=True)[:FORMAT['maximum_templates_per_lane']]
           for lane,gs in groups.items()}
    return banks


def sums(image,h,w):
    integral=cv2.integral(image.astype('uint8'))
    return integral[h:,w:]-integral[:-h,w:]-integral[h:,:-w]+integral[:-h,:-w]


def match(packed,columns,spacing,patch_shift,templates,note):
    """Compare all candidate offsets; reject distinct competing alignments."""
    color,white,_,_,valid=np.unpackbits(packed,axis=-1)[...,:columns].astype(bool)
    candidates=[];center=(white.shape[0]-1)/2
    sy,sx=FORMAT['vertical_search_pixels'],FORMAT['horizontal_search_pixels']
    for index,template in enumerate(templates):
        # Both the image and two supporting identities must be external.
        if (len(set(template['support'])-{note})<FORMAT['minimum_independent_heads']
                or template.get('reference',{}).get('note')in(None,note)):continue
        x,y,w,h=template['bounds'];left,right=max(0,x-sx),min(white.shape[1],x+w+sx)
        top,bottom=max(0,y-sy),min(white.shape[0],y+h+sy)
        if right-left<w or bottom-top<h:continue
        window=white[top:bottom,left:right]
        total=sums(window,h,w)+template['image'].sum()
        errors=cv2.matchTemplate(window.astype('float32'),template['image'].astype('float32'),cv2.TM_SQDIFF)
        scores=1-errors/np.maximum(total,1)
        allowed=(sums(valid[top:bottom,left:right],h,w)==h*w)&(sums(color[top:bottom,left:right],h,w)>=.12*h*w)
        offsets=top+np.arange(scores.shape[0])+h/2-center+patch_shift
        allowed&=(abs(offsets)<=.1*spacing)[:,None]
        for row in range(scores.shape[0]):
            cols=np.flatnonzero(allowed[row])
            if not len(cols):continue
            col=int(cols[np.argmax(scores[row,cols])]);score=float(scores[row,col])
            candidates.append((score,float(offsets[row]),index,[left+col,top+row,w,h]))
    if not candidates:return None
    candidates.sort(key=lambda c:c[0],reverse=True);best=candidates[0]
    if best[0]<FORMAT['minimum_similarity']:return None
    rival=max((c[0]for c in candidates if abs(c[1]-best[1])>FORMAT['distinct_offset_pixels']),default=0)
    if rival>best[0]-FORMAT['different_offset_margin']:return None
    return {'offset_pixels':best[1],'similarity':best[0],'alternative_similarity':rival,
            'template':best[2],'outer_bounds_in_patch':best[3]}


def augment(data,path,records,fit_offset):
    """Templates add coordinate evidence, never note type or chart timing."""
    from piu_timeline.play.screen_regions import visible_cap_bounds
    with np.load(path,allow_pickle=False)as saved:
        pixels={key:saved[key]for key in ('masks','times','pts','lanes','ys','spacing','columns')}
        lookup=defaultdict(list)
        for i,(time,lane)in enumerate(zip(pixels['times'],pixels['lanes'],strict=True)):
            lookup[round(float(time),6),int(lane)].append(i)
        banks=learn(records,pixels,lookup)
        records=refine_outlines(data,pixels,lookup,banks,records,fit_offset)
        known={r['note']:r for r in records};added=[]
        spacing,columns=float(pixels['spacing']),int(pixels['columns'])
        for ni,note in enumerate(data['notes']):
            if not banks.get(note['lane']):continue
            samples=list(known.get(ni,{}).get('observations',[]))
            measured={s['time']for s in samples}
            for time,y in detection_points(note):
                if time in measured:continue
                options=[i for i in lookup.get((round(time,6),note['lane']),[])if abs(float(pixels['ys'][i])-y)<1e-5]
                if len(options)!=1:continue
                i=options[0];shift=round(float(pixels['ys'][i]))-float(pixels['ys'][i])
                result=match(pixels['masks'][i],columns,spacing,shift,banks[note['lane']],ni)
                if result:
                    bounds=visible_cap_bounds(data,note['lane'],y,result['outer_bounds_in_patch'],
                                              (pixels['masks'].shape[2],columns),spacing)
                    if bounds is not None:
                        samples.append({'time':time,'source_pts_seconds':float(pixels['pts'][i]),
                                        'detected_y_pixels':float(pixels['ys'][i]),
                                        'patch_center_shift_pixels':shift,'support_bounds_pixels':bounds,**result})
            samples.sort(key=lambda s:s['time'])
            fitted=fit_offset(samples)
            if fitted:
                if ni in known:known[ni]={**known[ni],**fitted}
                else:added.append({'note':ni,'lane':note['lane'],'method':'independent_cap_templates',**fitted})
        metadata=[{'lane':lane,'templates':[{'template':i,'reference':t['reference'],
                    'support':list(t['support'].values()),'observations':t['count']}
                   for i,t in enumerate(ts)]}for lane,ts in banks.items()]
    return list(known.values())+added,{'format':FORMAT,'lanes':metadata}


def refine_outlines(data,pixels,lookup,banks,records,fit_offset):
    """A truncated inner contour need not bound the complete canonical cap."""
    from piu_timeline.play.screen_regions import visible_cap_bounds
    spacing,columns=float(pixels['spacing']),int(pixels['columns']);result=[]
    for record in records:
        samples=[];changed=False
        for sample in record['observations']:
            options=[i for i in lookup.get((round(sample['time'],6),record['lane']),[])
                     if abs(float(pixels['pts'][i])-sample['source_pts_seconds'])<1e-6
                     and abs(float(pixels['ys'][i])-sample['detected_y_pixels'])<1e-5]
            proof=None
            if len(options)==1:
                i=options[0]
                proof=match(pixels['masks'][i],columns,spacing,sample['patch_center_shift_pixels'],
                            banks.get(record['lane'],[]),record['note'])
            if proof and truncated_outline(sample['outer_bounds_in_patch'],proof['outer_bounds_in_patch']):
                bounds=visible_cap_bounds(data,record['lane'],sample['detected_y_pixels'],
                    proof['outer_bounds_in_patch'],(pixels['masks'].shape[2],columns),spacing)
                if bounds is not None:
                    sample={**sample,**proof,'support_bounds_pixels':bounds,
                            'outline_observation':dict(sample),'method':'independent_cap_template'}
                    changed=True
            samples.append(sample)
        if changed:
            fitted=fit_offset(samples)
            record={**record,**fitted,'coordinate_method':'isolated_caps_with_independent_templates'}
        result.append(record)
    return result


def truncated_outline(outline,canonical):
    """The observed small box must be contained, not merely shifted elsewhere."""
    x,y,w,h=outline;cx,cy,cw,ch=canonical
    return (ch-h>=FORMAT['minimum_truncated_rows'] and cx<=x and cy<=y
            and x+w<=cx+cw and y+h<=cy+ch)
