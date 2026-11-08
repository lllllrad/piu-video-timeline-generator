"""A declared distinct cap can identify its role without proving a connector."""
import math
import numpy as np

from piu_timeline.play.skins.overlap import runs

FORMAT={'schema':1,'role':'declared_distinct_full_cap_or_cap_features',
        'features':'all_discriminating_regions_fully_observed','connection':'independently_compared_regions'}
QUALIFIED={'full_pattern','cap_role_pattern'}


def identify(template,record):
    mode=template.get('cap_role_identification')
    if (mode not in('distinct_full_cap','distinct_cap_features')
            or record.get('classification_status')!='cap_only'):
        return record
    if mode=='distinct_full_cap'and(record.get('occlusion_evidence')or record.get('cap_context_qualified')is False):return record
    features=template.get('cap_features',[])
    if mode=='distinct_cap_features':
        if not features:return record
        visible=np.zeros(template['mask'].shape,bool)
        if 'visible_cap_runs'not in record:return record
        for row,a,b in record['visible_cap_runs']:visible[row,a:b]=True
        for region in template['regions']:
            if region['name']not in features:continue
            a,b,c,d=region['box']
            if (region['mask'].astype(bool)&~visible[b:d,a:c]).any():return record
    required={'cap',*template.get('cap_features',[])}
    for region in template['regions']:
        if region['name']not in required:continue
        error=record.get('region_errors',{}).get(region['name'])
        if not isinstance(error,(int,float))or not math.isfinite(error)or error>region.get('maximum_error',.015):
            return record
    return {**record,'role':template['role'],'template_role':template['role'],
            'classification_status':'cap_role_pattern','reason':'distinct_cap_with_unverified_connection',
            'visible_cap_runs':record.get('visible_cap_runs',runs(template['cap_support'])),
            'visible_connection_runs':record.get('visible_connection_runs',[]),
            'role_evidence':{'method':'declared_distinct_cap_features'if mode=='distinct_cap_features'else'declared_distinct_full_cap',
                             'discriminating_features':features if mode=='distinct_cap_features'else[],
                             'required_cap_regions':sorted(required),
                             'connection_confirmed':False}}
