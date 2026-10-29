"""Prove tap clearance around matched cap images from native spatial masks."""
from collections import defaultdict

import cv2
import numpy as np

from piu_timeline.play.pixel_cache import FORMAT as PIXEL_FORMAT, measurements
from piu_timeline.play.screen_regions import occluders_at_bounds
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.sampling import key

FORMAT={'schema':1,'revision':1,'model':'phoenix_chromatic_gap','pixels':PIXEL_FORMAT,
        'minimum_frames':4,'minimum_span_seconds':.065,'maximum_gap_seconds':.05,
        'minimum_motion_spacing':.5,'maximum_anchor_delta_spacing':.1,
        'body_core_halfwidth_spacing':.1,'minimum_clearance_halfwidth_spacing':.2,
        'maximum_white_fraction':.05}
COLORS=('blue','red','yellow','red','blue')


def validate_profile(data,bank,profile):
    if profile!={'model':FORMAT['model'],'skin':bank['skin']}:
        raise ValueError('Unsupported native clearance profile or skin identity')
    if any(lane.get('color')!=COLORS[i%5]for i,lane in enumerate(data['layout']['lanes'])):
        raise ValueError('Native clearance profile differs from lane colors')
    spacing=np.median(np.diff([lane['x']*PIXEL_FORMAT['width']for lane in data['layout']['lanes']]))
    scale=spacing/bank['spacing_pixels'];kinds=set();count=0
    for template in bank['templates']:
        if template['role']=='tap'and template['id']in bank['anchor_registrations']:
            half=FORMAT['minimum_clearance_halfwidth_spacing']*bank['spacing_pixels']
            for region in template['regions']:
                if region['name']in('clear_above','clear_below')and not(
                        region['box'][0]<=template['anchor_pixels'][0]-half
                        and region['box'][2]>=template['anchor_pixels'][0]+half):
                    raise ValueError('Clearance probe cannot cover the registered body core')
        if template['role']!='hold_body':continue
        h,w=template['mask'].shape;size=max(1,round(w*scale)),max(1,round(h*scale))
        rgb=cv2.resize(template['rgb'],size,interpolation=cv2.INTER_AREA)
        support=cv2.resize(template['mask'].astype('uint8'),size,interpolation=cv2.INTER_NEAREST).astype(bool)
        color=measurements(rgb)['relaxed_'+COLORS[template['lane_kind']]]
        center=template['anchor_pixels'][0]*size[0]/w
        core=abs(np.arange(size[0])+.5-center)<=FORMAT['body_core_halfwidth_spacing']*spacing
        if not support.any()or not core.any()or not (color&support)[:,core].any(axis=1)[support.any(axis=1)].all():
            raise ValueError('A body reference can disappear from the clearance color plane')
        kinds.add(template['lane_kind']);count+=1
    if kinds!=set(range(5)):raise ValueError('Clearance needs body references for every lane kind')
    return {'validated_body_templates':count,'lane_kinds':sorted(kinds)}


def clear_regions(data,pattern,template,planes):
    width=PIXEL_FORMAT['width'];height=next(iter(planes.values())).shape[0]
    sx,sy=width/data['analysis_width'],height/data['analysis_height']
    regions=[r for r in template['regions']if r['name']in('clear_above','clear_below')]
    if len(regions)!=2:return None
    if any(not r['mask'].any()for r in regions):return None
    left,top=pattern['bounds_pixels'][:2];result=[]
    # The positive cap must also be outside documented foreground footprints.
    cap=next(r['box']for r in template['regions']if r['name']=='cap')
    if occluders_at_bounds(data['layout'],[(left+cap[0])*sx,(top+cap[1])*sy,
                                         (left+cap[2])*sx,(top+cap[3])*sy],width,height):return None
    for region in regions:
        a,b,c,d=region['box']
        bounds=[int(np.floor((left+a)*sx)),int(np.floor((top+b)*sy)),
                int(np.ceil((left+c)*sx)),int(np.ceil((top+d)*sy))]
        x0,y0,x1,y1=bounds
        if not 0<=x0<x1<=width or not 0<=y0<y1<=height:return None
        if occluders_at_bounds(data['layout'],bounds,width,height):return None
        color=planes['relaxed_'+data['layout']['lanes'][pattern['lane']]['color']][y0:y1,x0:x1]
        white=float(planes['white'][y0:y1,x0:x1].mean())
        if color.any()or white>=FORMAT['maximum_white_fraction']:return None
        result.append({'region':region['name'],'bounds_pixels':bounds,'white_fraction':white,
                       'relaxed_foreground_pixels':0})
    return result


def qualify(proofs,spacing):
    groups=[]
    for point in proofs:
        if not groups or point['playback_seconds']-groups[-1][-1]['playback_seconds']>FORMAT['maximum_gap_seconds']:
            groups.append([])
        groups[-1].append(point)
    for group in groups:
        times=[p['playback_seconds']for p in group];ys=[p['image_anchor'][1]for p in group]
        if (len(set(p['source_pts_seconds']for p in group))>=FORMAT['minimum_frames']
                and times[-1]-times[0]>=FORMAT['minimum_span_seconds']
                and len(set(ys))>=FORMAT['minimum_frames']
                and max(ys)-min(ys)>=FORMAT['minimum_motion_spacing']*spacing):return group
    return []


def derive(data,native,samples,bank,profile):
    validation=validate_profile(data,bank,profile)
    if bank['contract']!=data['skin_detector']['contract']['bank']:
        raise ValueError('Clearance bank differs from acquired cap images')
    width,height=data['analysis_width'],data['analysis_height']
    detector=SkinDetector(bank,data['layout'],width,height);templates={key(t):t for t in detector.templates}
    owners=defaultdict(list);proofs=defaultdict(list);already_taps=set()
    for i,note in enumerate(data['notes']):
        for time,y in note.get('detected_points',note.get('points',[])):
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
        for image in frame.get('skin_observations',[]):
            if image['role']=='hold_body':continue
            indices=owners[time,image['lane'],round(image['y']*height,5)]
            if len(indices)!=1:continue
            if 'tap'in image.get('conflicting_roles',[image['role']]):already_taps.add(indices[0])
            for pattern in [image,*image.get('alternatives',[])]:
                template=templates[key(pattern)]
                if (pattern.get('template_role',pattern['role'])!='tap'
                        or pattern['classification_status']!='cap_only'
                        or pattern['template']not in bank['anchor_registrations']):continue
                if max(abs(pattern['x']-image['x'])*width,abs(pattern['y']-image['y'])*height)>FORMAT['maximum_anchor_delta_spacing']*detector.spacing:continue
                regions=clear_regions(data,{**pattern,'lane':image['lane']},template,planes)
                if regions is None:continue
                proofs[indices[0]].append({'kind':'tap','role':'tap','reason':'image_cap_with_native_clearance',
                    'source_note':indices[0],'playback_seconds':time,'source_pts_seconds':pts,
                    'trace':'native-features/manifest.json','template':pattern['template'],'skin':bank['skin'],
                    'region_errors':{'cap':pattern['region_errors']['cap']},'bounds_pixels':pattern['bounds_pixels'],
                    'image_anchor':[pattern['x']*width,image['y']*height],
                    'classification_status':'cap_with_native_clearance','clearance_regions':regions,
                    **{k:pattern[k]for k in ('sampling_phase_pixels','reference_scale_y','sampling_kernel')if k in pattern},
                    'clearance_pixel_dimensions':[PIXEL_FORMAT['width'],next(iter(planes.values())).shape[0]]})
                break
    qualified={i:group for i,points in proofs.items()if(group:=qualify(points,detector.spacing))}
    return {'status':'available','validation':validation,
            'counts':{'qualified_clearance_notes':len(qualified),'already_observed_taps':len(qualified.keys()&already_taps),
                      'additional_tap_roles':len(qualified.keys()-already_taps)},
            'notes':{str(i):group for i,group in qualified.items()if i not in already_taps},'warnings':[]}
