"""Retain native reference anchors without claiming absolute game calibration."""
from collections import defaultdict

import numpy as np

from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.anchors import cap_reference, FORMAT as ANCHOR_FORMAT
from piu_timeline.play.skins.sampling import phases,FORMAT as SAMPLING_FORMAT

from piu_timeline.derived import CONTRACTS

FORMAT=CONTRACTS['image_coordinates']


def validate_origin(candidate,template,width,height,scale):
    """Bind a trimmed comparison canvas to its original reference anchor."""
    if 'sampling_origin_pixels'not in candidate:return
    origin=candidate['sampling_origin_pixels'];bounds=candidate.get('bounds_pixels',[])
    phase=candidate.get('sampling_phase_pixels',[0,0]);sy=candidate.get('reference_scale_y')
    if (not isinstance(origin,list)or len(origin)!=2 or any(type(v)is not int or v<0 for v in origin)
            or len(bounds)!=4 or any(type(v)is not int for v in bounds)
            or not 0<=bounds[0]<bounds[2]<=width or not 0<=bounds[1]<bounds[3]<=height
            or type(sy)not in(int,float)or not np.isfinite(sy)or abs(sy-scale)>1e-8
            or len(phase)!=2 or any(not any(abs(v-p)<1e-8 for p in phases(scale))for v in phase)
            or not np.isfinite([candidate['x'],candidate['y']]).all()
            or candidate.get('sampling_kernel','area')not in SAMPLING_FORMAT['kernels']):
        raise ValueError('Image comparison has incompatible sampling origin')
    expected=[bounds[i]+phase[i]+sy*template['anchor_pixels'][i]-origin[i]for i in (0,1)]
    if max(abs(expected[0]-candidate['x']*width),abs(expected[1]-candidate['y']*height))>1e-5:
        raise ValueError('Image anchor disagrees with its comparison canvas origin')



def registered_comparison(image,bank,templates,lane,y,height,scale):
    """Project a positive comparison from its matching anchor to its native center."""
    choices=[]
    for index,candidate in enumerate([image,*image.get('alternatives',[])]):
        name=candidate['template']
        if name not in bank['anchor_registrations']:continue
        template=templates[name]
        if template['lane_kind']!=lane%5 or candidate.get('lane',lane)!=lane:
            raise ValueError('Registered image comparison belongs to another lane')
        cap=next(r for r in template['regions']if r['name']=='cap')
        error=candidate.get('region_errors',{}).get('cap',float('nan'))
        if (type(error)not in(int,float)or not np.isfinite(error)or error<0
                or np.float32(error)/cap.get('maximum_error',.015)>1):continue
        row=candidate['y']*height
        if not np.isfinite(row):raise ValueError('Nonfinite registered comparison coordinate')
        original_height=template['mask'].shape[0];sy=max(2,round(original_height*scale))/original_height
        if 'reference_scale_y'in candidate:
            sy=candidate['reference_scale_y'];phase=candidate.get('sampling_phase_pixels',[0,0])
            if (not np.isfinite(sy)or abs(sy-scale)>1e-8 or len(phase)!=2
                    or candidate.get('sampling_kernel','area')not in SAMPLING_FORMAT['kernels']
                    or any(not any(abs(v-p)<1e-8 for p in phases(scale))for v in phase)):
                raise ValueError('Registered comparison has incompatible reference sampling')
        uncertainty=bank['anchor_registrations'][name]['coordinate_uncertainty_pixels']*sy
        center=row+bank['anchor_registrations'][name]['center_offset_y_pixels']*sy
        choices.append({'template':name,'comparison_index':index,'detected_y_pixels':row,'native_y_pixels':center,
                        'cap_error':error,'scale_y':sy,'uncertainty_pixels':uncertainty})
    if not choices:return {},None
    lo=max(c['native_y_pixels']-c['uncertainty_pixels']for c in choices)
    hi=min(c['native_y_pixels']+c['uncertainty_pixels']for c in choices)
    if lo>hi+1e-6:return {},{'coordinate_intersection_pixels':[lo,hi],'comparisons':choices}
    coincident=[c for c in choices if abs(c['detected_y_pixels']-y)<1e-5]
    if not coincident:return {},None
    chosen=min(coincident,key=lambda c:(c['uncertainty_pixels'],c['comparison_index']))
    return {'native_y_pixels':chosen['native_y_pixels'],
            'native_cap_coordinate_uncertainty_pixels':chosen['uncertainty_pixels'],
            'native_cap_reference_scale_y':chosen['scale_y'],'native_cap_reference_template':chosen['template'],
            'native_cap_reference_error':chosen['cap_error'],'native_cap_comparison_index':chosen['comparison_index']},None


def measure(data,frames):
    bank=load_bank(data['skin_detector']['bank_path'])
    if bank['contract']!=data['skin_detector']['contract']['bank']:
        raise ValueError('Coordinate references differ from acquired image observations')
    templates={t['id']:t for t in bank['templates']};identities={}
    require_origin='comparison_canvas'in data['skin_detector']['contract'].get('detector',{}).get('sampling',{})
    for key,t in templates.items():
        if any(r['name']=='cap'for r in t['regions']):identities[key]=cap_reference(bank,t)
    height=data['analysis_height']
    scale=float(np.median(np.diff([lane['x']*data['analysis_width']for lane in data['layout']['lanes']])))/bank['spacing_pixels']
    expected=defaultdict(list);samples=[[]for _ in data['notes']];conflicts=defaultdict(list)
    for index,note in enumerate(data['notes']):
        for time,y in note.get('detected_points',note['points']):expected[time].append((index,note['lane'],y))
    source_pts={s['time']:s['source_pts']for s in data.get('scroll_motion',{}).get('samples',[])}
    last=None
    for frame in frames:
        time,pts=frame['playback_seconds'],frame['source_pts_seconds']
        if not np.isfinite(time)or not np.isfinite(pts):raise ValueError('Nonfinite native image timestamp')
        if last is not None and (time<=last[0]or pts<=last[1]):
            raise ValueError('Native image timestamps must increase')
        last=(time,pts)
        if time in source_pts and abs(source_pts[time]-pts)>1e-6:
            raise ValueError('Image coordinates disagree with native motion source PTS')
        caps=[o for o in frame.get('skin_observations',[])if o['role']!='hold_body']
        for index,lane,y in expected.pop(time,[]):
            options=[o for o in caps if o['lane']==lane and abs(o['y']*height-y)<1e-5]
            if len(options)!=1:raise ValueError(f'Image coordinate lacks one native cap: note {index}, time {time}')
            image=options[0];template=templates[image['template']]
            for candidate in [image,*image.get('alternatives',[])]:
                if require_origin and 'sampling_origin_pixels'not in candidate:
                    raise ValueError('Image comparison is missing its declared canvas origin')
                validate_origin(candidate,templates[candidate['template']],data['analysis_width'],height,scale)
            region=next((r for r in template['regions']if r['name']=='cap'),None)
            error=image.get('region_errors',{}).get('cap',float('nan'))
            if (region is None or template['lane_kind']!=lane%5 or image.get('skin')!=bank['skin']
                    or type(error)not in(int,float)
                    or not np.isfinite(error)or error<0
                    or np.float32(error)/region.get('maximum_error',.015)>1):
                raise ValueError(f'Image coordinate has no positive cap comparison: note {index}, time {time}')
            registration,conflict=registered_comparison(image,bank,templates,lane,y,height,scale)
            if conflict:
                conflicts[index].append({'time':time,'source_pts_seconds':pts,**conflict})
                registration={'native_cap_registration_status':'conflicting'}
            samples[index].append({'time':time,'source_pts_seconds':pts,'native_y_pixels':y,'detected_y_pixels':y,
                                   'image_anchor':[image['x'],image['y']],'template':image['template'],
                                   'cap_error':error,'cap_reference_sha256':identities[image['template']],
                                   'classification_status':image['classification_status'],
                                   **({'sampling_origin_pixels':image['sampling_origin_pixels']}
                                      if 'sampling_origin_pixels'in image else{}),
                                   **registration,
                                   'trace':'frames.jsonl'})
    if expected:raise ValueError('Image coordinate trajectory has no original source frame')
    records=[{'note':i,'lane':note['lane'],'status':'measured','coordinate_method':FORMAT['method'],
              'observations':samples[i]}for i,note in enumerate(data['notes'])]
    warnings=[{'note':i,'lane':data['notes'][i]['lane'],'reason':'conflicting_registered_image_anchors',
               'check':'timing_reconstruction','visible_start_seconds':evidence[0]['time'],
               'visible_end_seconds':evidence[-1]['time'],'observed_points':len(evidence),
               'source_pts_seconds':[e['source_pts_seconds']for e in evidence],
               'image_anchor_evidence':evidence,'trace':'frames.jsonl'}for i,evidence in conflicts.items()]
    return {'format':FORMAT,'status':'failed'if warnings else'native_image_anchors','notes':records,'warnings':warnings,
            'absolute_registration':'reviewed'if data['skin_detector'].get('registration_reviewed')else'unverified',
            'skin_contract':data['skin_detector']['contract'],'trace':'frames.jsonl'}
