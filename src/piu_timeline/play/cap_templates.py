"""Register connected caps against independently observed isolated silhouettes."""
from collections import defaultdict

import cv2
import numpy as np

FORMAT={'schema':1,'revision':1,'minimum_independent_heads':2,'cluster_similarity':.94,
        'maximum_clusters_per_lane':128,'maximum_templates_per_lane':12,
        'minimum_similarity':.90,'different_offset_margin':.04,'distinct_offset_pixels':.75,
        'vertical_search_pixels':4,'horizontal_search_pixels':1}


def dice(first,second):
    return 2*np.count_nonzero(first&second)/max(1,int(first.sum()+second.sum()))


def learn(records,pixels,lookup):
    """A reference needs independent heads at the same canonical alignment."""
    masks,columns=pixels['masks'],int(pixels['columns']);exact=defaultdict(dict);groups=defaultdict(list)
    for record in records:
        if record['status']!='registered':continue
        for sample in record['observations']:
            if abs(sample['offset_pixels']-record['offset_pixels'])>1:continue
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
        # One identity cannot calibrate its own continuation through a template.
        if note in template['support']:continue
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
    from piu_timeline.play.holds.features import ui_regions
    with np.load(path,allow_pickle=False)as saved:
        pixels={key:saved[key]for key in ('masks','times','pts','lanes','ys','spacing','columns')}
        lookup=defaultdict(list)
        for i,(time,lane)in enumerate(zip(pixels['times'],pixels['lanes'],strict=True)):
            lookup[round(float(time),6),int(lane)].append(i)
        banks=learn(records,pixels,lookup);known={r['note']for r in records};added=[]
        spacing,columns=float(pixels['spacing']),int(pixels['columns']);height=data['analysis_height']
        for ni,note in enumerate(data['notes']):
            if ni in known or not banks.get(note['lane']):continue
            samples=[];x=data['layout']['lanes'][note['lane']]['x']
            for time,y in note.get('detected_points',note.get('points',[])):
                if not data['layout']['receptor_y']*height+1.3*spacing<y<data['layout'].get('note_y_max',.95)*height-.8*spacing:continue
                if any(rx<=x<=rx+rw and ry*height-.8*spacing<=y<=(ry+rh)*height+.8*spacing
                       for rx,ry,rw,rh in ui_regions(data['layout'])):continue
                options=[i for i in lookup.get((round(time,6),note['lane']),[])if abs(float(pixels['ys'][i])-y)<1e-5]
                if len(options)!=1:continue
                i=options[0];shift=round(float(pixels['ys'][i]))-float(pixels['ys'][i])
                result=match(pixels['masks'][i],columns,spacing,shift,banks[note['lane']],ni)
                if result:samples.append({'time':time,'source_pts_seconds':float(pixels['pts'][i]),
                                          'patch_center_shift_pixels':shift,**result})
            fitted=fit_offset(samples)
            if fitted:added.append({'note':ni,'lane':note['lane'],'method':'independent_cap_templates',**fitted})
        metadata=[{'lane':lane,'templates':[{'template':i,'reference':t['reference'],
                    'support':list(t['support'].values()),'observations':t['count']}
                   for i,t in enumerate(ts)]}for lane,ts in banks.items()]
    return records+added,{'format':FORMAT,'lanes':metadata}
