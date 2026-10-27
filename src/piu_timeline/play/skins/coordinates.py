"""Retain native reference anchors without claiming absolute game calibration."""
from collections import defaultdict

import numpy as np

from piu_timeline.play.skins.bank import load_bank

FORMAT={'schema':1,'revision':1,'method':'native_image_anchors','trace':'frames.jsonl'}


def measure(data,frames):
    bank=load_bank(data['skin_detector']['bank_path'])
    if bank['contract']!=data['skin_detector']['contract']['bank']:
        raise ValueError('Coordinate references differ from acquired image observations')
    templates={t['id']:t for t in bank['templates']};height=data['analysis_height']
    expected=defaultdict(list);samples=[[]for _ in data['notes']]
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
            samples[index].append({'time':time,'source_pts_seconds':pts,'native_y_pixels':y,
                                   'image_anchor':[image['x'],image['y']],'template':image['template'],
                                   'cap_error':error,'classification_status':image['classification_status'],
                                   'trace':'frames.jsonl'})
    if expected:raise ValueError('Image coordinate trajectory has no original source frame')
    records=[{'note':i,'lane':note['lane'],'status':'measured','coordinate_method':FORMAT['method'],
              'observations':samples[i]}for i,note in enumerate(data['notes'])]
    return {'format':FORMAT,'status':'native_image_anchors','notes':records,
            'absolute_registration':'reviewed'if data['skin_detector'].get('registration_reviewed')else'unverified',
            'skin_contract':data['skin_detector']['contract'],'trace':'frames.jsonl'}
