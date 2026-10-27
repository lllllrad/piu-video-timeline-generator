"""Retain native reference anchors without claiming absolute game calibration."""
from collections import defaultdict

import numpy as np

from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.anchors import cap_reference, FORMAT as ANCHOR_FORMAT

FORMAT={'schema':1,'revision':4,'method':'native_image_anchors','trace':'frames.jsonl','native_cap_registration':ANCHOR_FORMAT}



def registered_comparison(image,bank,templates,lane,y,height,scale):
    """Use a positive source-bound comparison at the unchanged measured row."""
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
        uncertainty=max(ANCHOR_FORMAT['coordinate_uncertainty_pixels'],
                        bank['anchor_registrations'][name]['coordinate_uncertainty_pixels']*sy)
        choices.append({'template':name,'comparison_index':index,'native_y_pixels':row,
                        'cap_error':error,'scale_y':sy,'uncertainty_pixels':uncertainty})
    if not choices:return {},None
    lo=max(c['native_y_pixels']-c['uncertainty_pixels']for c in choices)
    hi=min(c['native_y_pixels']+c['uncertainty_pixels']for c in choices)
    if lo>hi+1e-6:return {},{'coordinate_intersection_pixels':[lo,hi],'comparisons':choices}
    coincident=[c for c in choices if abs(c['native_y_pixels']-y)<1e-5]
    if not coincident:return {},None
    chosen=min(coincident,key=lambda c:(c['uncertainty_pixels'],c['comparison_index']))
    return {'native_cap_coordinate_uncertainty_pixels':chosen['uncertainty_pixels'],
            'native_cap_reference_scale_y':chosen['scale_y'],'native_cap_reference_template':chosen['template'],
            'native_cap_reference_error':chosen['cap_error'],'native_cap_comparison_index':chosen['comparison_index']},None


def measure(data,frames):
    bank=load_bank(data['skin_detector']['bank_path'])
    if bank['contract']!=data['skin_detector']['contract']['bank']:
        raise ValueError('Coordinate references differ from acquired image observations')
    templates={t['id']:t for t in bank['templates']};identities={}
    for key,t in templates.items():
        if any(r['name']=='cap'for r in t['regions']):identities[key]=cap_reference(bank,t)
    height=data['analysis_height']
    scale=float(np.median(np.diff([lane['x']*data['analysis_width']for lane in data['layout']['lanes']])))/bank['spacing_pixels']
    expected=defaultdict(list);samples=[[]for _ in data['notes']];conflicts=defaultdict(list)
    for index,note in enumerate(data['notes']):
        for time,y in note['points']:expected[time].append((index,note['lane'],y))
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
            samples[index].append({'time':time,'source_pts_seconds':pts,'native_y_pixels':y,
                                   'image_anchor':[image['x'],image['y']],'template':image['template'],
                                   'cap_error':error,'cap_reference_sha256':identities[image['template']],
                                   'classification_status':image['classification_status'],
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
