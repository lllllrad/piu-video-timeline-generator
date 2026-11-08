"""A declared distinct cap can identify its role without proving a connector."""
import math

from piu_timeline.play.skins.overlap import runs

FORMAT={'schema':1,'role':'declared_distinct_full_cap','connection':'independently_compared_regions'}
QUALIFIED={'full_pattern','cap_role_pattern'}


def identify(template,record):
    if (template.get('cap_role_identification')!='distinct_full_cap'
            or record.get('classification_status')!='cap_only' or record.get('occlusion_evidence')):
        return record
    if record.get('cap_context_qualified')is False:return record
    required={'cap',*template.get('cap_features',[])}
    for region in template['regions']:
        if region['name']not in required:continue
        error=record.get('region_errors',{}).get(region['name'])
        if not isinstance(error,(int,float))or not math.isfinite(error)or error>region.get('maximum_error',.015):
            return record
    return {**record,'role':template['role'],'template_role':template['role'],
            'classification_status':'cap_role_pattern','reason':'distinct_cap_with_unverified_connection',
            'visible_cap_runs':runs(template['cap_support']),'visible_connection_runs':[],
            'role_evidence':{'method':FORMAT['role'],'required_cap_regions':sorted(required),
                             'connection_confirmed':False}}
