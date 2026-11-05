"""Prove tap clearance around matched cap images from native spatial masks."""
from collections import defaultdict
from piu_timeline.play.observations.coordinates import detection_points

import cv2
import numpy as np

from piu_timeline.play.pixel_cache import FORMAT as PIXEL_FORMAT, measurements
from piu_timeline.play.screen_regions import occluders_at_bounds
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.sampling import key,reference_scale

FORMAT={'schema':1,'revision':8,'model':'phoenix_chromatic_gap','pixels':PIXEL_FORMAT,
        'minimum_frames':4,
        'minimum_motion_spacing':.5,'maximum_anchor_delta_spacing':.1,
        'body_geometry':'declared_components_all_rows','minimum_clearance_halfwidth_spacing':.2,
        'maximum_white_fraction':.05}
COLORS=('blue','red','yellow','red','blue')


def validate_profile(data,bank,profile):
    if profile!={'model':FORMAT['model'],'skin':bank['skin']}:
        raise ValueError('Unsupported native clearance profile or skin identity')
    if any(lane.get('color')!=COLORS[i%5]for i,lane in enumerate(data['layout']['lanes'])):
        raise ValueError('Native clearance profile differs from lane colors')
    height=round(PIXEL_FORMAT['width']*data['analysis_height']/data['analysis_width'])
    scale=reference_scale(bank,data['layout'],PIXEL_FORMAT['width'],height);kinds=set();count=0;footprints={}
    for template in bank['templates']:
        if template['role']!='hold_body':continue
        h,w=template['mask'].shape;size=max(1,round(w*scale)),max(1,round(h*scale))
        rgb=cv2.resize(template['rgb'],size,interpolation=cv2.INTER_AREA)
        # Alpha includes interpolation context. Only declared positive body regions
        # establish the body's expected color; surrounding artwork is not body.
        measured=np.zeros(template['mask'].shape,dtype='uint8')
        for region in template['regions']:
            if region['name']!='body':continue
            for a,b,c,d in region.get('comparison_boxes',[region['box']]):
                measured[b:d,a:c]=template['mask'][b:d,a:c]
        support=cv2.resize(measured,size,interpolation=cv2.INTER_NEAREST).astype(bool)
        color=measurements(rgb)['relaxed_'+COLORS[template['lane_kind']]]
        if not support.any():raise ValueError('Body reference has no measured support')
        count_components,labels=cv2.connectedComponents(support.astype('uint8'),connectivity=8)
        for component in range(1,count_components):
            footprint=labels==component;rows=footprint.any(axis=1)
            if not(color&footprint).any(axis=1)[rows].all():
                raise ValueError('A body component can disappear from the clearance color plane')
        xs=np.nonzero(support)[1];center=template['anchor_pixels'][0]*size[0]/w
        lo,hi=float(xs.min()-center),float(xs.max()+1-center)
        kind=str(template['lane_kind']);before=footprints.get(kind,[lo,hi])
        footprints[kind]=[min(lo,before[0]),max(hi,before[1])]
        kinds.add(template['lane_kind']);count+=1
    if kinds!=set(range(5)):raise ValueError('Clearance needs body references for every lane kind')
    return {'validated_body_templates':count,'lane_kinds':sorted(kinds),'body_x_offsets_pixels':footprints}


def clear_regions(data,pattern,template,planes,body_footprints=None):
    width=PIXEL_FORMAT['width'];height=next(iter(planes.values())).shape[0]
    sx,sy=width/data['analysis_width'],height/data['analysis_height']
    regions=[r for r in template['regions']if r['name']in('clear_above','clear_below')]
    if len(regions)!=2:return None
    if any(not r['mask'].any()for r in regions):return None
    left,top=pattern['bounds_pixels'][:2];result=[]
    current=template.get('sampling_origin_pixels',[0,0]);observed=pattern.get('sampling_origin_pixels',[0,0])
    left+=current[0]-observed[0];top+=current[1]-observed[1]
    # The cap has a positive RGB match. Potential HUD overlap cannot refute it.
    # Blank bands remain unknown behind a HUD: it could conceal a connection.
    for region in regions:
        a,b,c,d=region['box']
        bounds=[int(np.floor((left+a)*sx)),int(np.floor((top+b)*sy)),
                int(np.ceil((left+c)*sx)),int(np.ceil((top+d)*sy))]
        # The RGB reference's background box is not a limit on measurable game
        # pixels. Inspect the measured body footprint, including off-center shoulders.
        spacing=float(np.median(np.diff([lane['x']*width for lane in data['layout']['lanes']])))
        half=FORMAT['minimum_clearance_halfwidth_spacing']*spacing
        center=pattern['x']*width
        lo,hi=(body_footprints or{}).get(str(pattern['lane']%5),[-half,half])
        bounds[0]=min(bounds[0],int(np.floor(center+min(-half,lo))))
        bounds[2]=max(bounds[2],int(np.ceil(center+max(half,hi))))
        x0,y0,x1,y1=bounds
        if not 0<=x0<x1<=width or not 0<=y0<y1<=height:return None
        if occluders_at_bounds(data['layout'],bounds,width,height):return None
        color=planes['relaxed_'+data['layout']['lanes'][pattern['lane']]['color']][y0:y1,x0:x1]
        white=float(planes['white'][y0:y1,x0:x1].mean())
        if color.any()or white>=FORMAT['maximum_white_fraction']:return None
        result.append({'region':region['name'],'bounds_pixels':bounds,'white_fraction':white,
                       'relaxed_foreground_pixels':0})
    return result


def qualify(proofs,spacing,movement=None):
    # These are positive per-frame classifications of one owned trajectory,
    # not a motion interpolation across missing observations. An unobservable
    # frame cannot invalidate clear pixels before or after it. Hold observations
    # anywhere on the trajectory still create a type conflict in the role join.
    if not proofs:return []
    moving=proofs if movement is None else movement
    ys=[p['image_anchor'][1]for p in moving]
    if (len(set(p['source_pts_seconds']for p in moving))>=FORMAT['minimum_frames']
            and len(set(ys))>=FORMAT['minimum_frames']
            and max(ys)-min(ys)>=FORMAT['minimum_motion_spacing']*spacing):return proofs
    return []


def derive(data,native,samples,bank,profile):
    validation=validate_profile(data,bank,profile)
    if bank['contract']!=data['skin_detector']['contract']['bank']:
        raise ValueError('Clearance bank differs from acquired cap images')
    width,height=data['analysis_width'],data['analysis_height']
    detector=SkinDetector(bank,data['layout'],width,height);templates={key(t):t for t in detector.templates}
    owners=defaultdict(list);proofs=defaultdict(list);held=defaultdict(list);movement=defaultdict(list)
    for i,note in enumerate(data['notes']):
        for time,y in detection_points(note):
            owners[time,note['lane'],round(y,5)].append(i)
    previous=None
    for frame,(pts,time,planes,_)in zip(native,samples,strict=True):
        shape=(round(PIXEL_FORMAT['width']*data['game_roi'][3]/data['game_roi'][2]),PIXEL_FORMAT['width'])
        if any(plane.shape!=shape for plane in planes.values()):raise ValueError('Native clearance mask geometry differs')
        if (not np.isfinite([pts,time]).all()or previous is not None and
                (pts<=previous[0]or time<=previous[1])):raise ValueError('Clearance needs increasing native PTS')
        previous=pts,time
        if frame['source_pts_seconds']!=pts or frame['playback_seconds']!=time:
            raise ValueError('Clearance masks differ from original frame timestamps')
        from piu_timeline.play.skins.connections import body_connections
        for image,pattern,connection in body_connections(data,frame,templates):
            indices=owners[time,image['lane'],round(image['y']*height,5)]
            if len(indices)!=1:continue
            held[indices[0],connection['role']].append({'kind':'hold','role':connection['role'],
                'reason':'image_cap_with_measured_body_connection','source_note':indices[0],
                'playback_seconds':time,'source_pts_seconds':pts,'trace':'frames.jsonl',
                'template':pattern['template'],'skin':bank['skin'],'region_errors':pattern['region_errors'],
                'bounds_pixels':pattern['bounds_pixels'],'image_anchor':[pattern['x']*width,image['y']*height],
                'classification_status':'cap_with_body_comparisons',**connection})
        for image in frame.get('skin_observations',[]):
            if image['role']=='hold_body':continue
            indices=owners[time,image['lane'],round(image['y']*height,5)]
            if len(indices)!=1:continue
            movement[indices[0]].append({'playback_seconds':time,'source_pts_seconds':pts,
                                       'image_anchor':[image['x']*width,image['y']*height]})
            for pattern in [image,*image.get('alternatives',[])]:
                template=templates[key(pattern)]
                if (pattern.get('template_role',pattern['role'])!='tap'
                        or pattern['classification_status']!='cap_only'
                        or pattern['template']not in bank['anchor_registrations']):continue
                if max(abs(pattern['x']-image['x'])*width,abs(pattern['y']-image['y'])*height)>FORMAT['maximum_anchor_delta_spacing']*detector.spacing:continue
                regions=clear_regions(data,{**pattern,'lane':image['lane']},template,planes,validation['body_x_offsets_pixels'])
                if regions is None:continue
                proofs[indices[0]].append({'kind':'tap','role':'tap','reason':'image_cap_with_native_clearance',
                    'source_note':indices[0],'playback_seconds':time,'source_pts_seconds':pts,
                    'trace':'native-features/manifest.json','template':pattern['template'],'skin':bank['skin'],
                    'region_errors':{'cap':pattern['region_errors']['cap']},'bounds_pixels':pattern['bounds_pixels'],
                    'image_anchor':[pattern['x']*width,image['y']*height],
                    'classification_status':'cap_with_native_clearance','clearance_regions':regions,
                    **{k:pattern[k]for k in ('sampling_phase_pixels','reference_scale_y','sampling_kernel','sampling_origin_pixels')if k in pattern},
                    'clearance_pixel_dimensions':[PIXEL_FORMAT['width'],next(iter(planes.values())).shape[0]]})
                break
    qualified={i:group for i,points in proofs.items()if(group:=qualify(points,detector.spacing,movement[i]))}
    # Raw tap candidates may later be invalidated by HUD clearance checks.
    # Keep every qualified independent proof; the role join owns conflicts.
    notes={str(i):group for i,group in qualified.items()}
    connected=0
    for (i,_),points in held.items():
        group=qualify(points,detector.spacing,movement[i])
        if group:notes.setdefault(str(i),[]).extend(group);connected+=1
    return {'status':'available','validation':validation,
            'counts':{'qualified_clearance_notes':len(qualified),'connected_hold_roles':connected},
            'notes':notes,'warnings':[]}
