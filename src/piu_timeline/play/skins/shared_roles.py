"""Independent cap appearance and role context, joined by declared native centers."""
import numpy as np

from piu_timeline.play.skins.sampling import key
from piu_timeline.play.skins.support import cap_support

FORMAT={'schema':1,'method':'declared_cap_family_with_independent_context',
        'maximum_center_rounding_pixels':.5,'context':'all_spatial_cells',
        'foreground':'other_measured_cap_support','context_cap_overlap':'exclude_measured_own_cap',
        'minimum_independent_connection_fraction':.5,'body_coverage':'all_remaining_connection_pixels'}
FIELDS=('template','x','y','bounds_pixels','sampling_phase_pixels','reference_scale_y',
        'sampling_kernel','sampling_origin_pixels')


def validate(families,templates):
    if not isinstance(families,list):raise ValueError('Shared cap families must be a list')
    by_id={t['id']:t for t in templates};seen=set()
    for family in families:
        required={'id','appearance_templates','role_templates'}
        if (not isinstance(family,dict)or not required<=set(family)
                or set(family)-required-{'body_templates'}
                or not isinstance(family['id'],str)or not family['id']or family['id']in seen):
            raise ValueError('Shared cap family needs a unique identity and explicit references')
        seen.add(family['id'])
        for field in ('appearance_templates','role_templates'):
            ids=family[field]
            if (not isinstance(ids,list)or not ids or any(not isinstance(v,str)or v not in by_id for v in ids)
                    or len(set(ids))!=len(ids)):
                raise ValueError('Shared cap family references must exist and be unique')
        body_ids=family.get('body_templates',[])
        if (not isinstance(body_ids,list)
                or any(not isinstance(name,str)or name not in by_id or by_id[name]['role']!='hold_body'for name in body_ids)
                or len(set(body_ids))!=len(body_ids)):
            raise ValueError('Shared cap body references must be distinct body templates')
        members=[by_id[name]for field in ('appearance_templates','role_templates')for name in family[field]]
        if (len({t['lane_kind']for t in members+[by_id[name]for name in body_ids]})!=1
                or any(t['role']=='hold_body'for t in members)):
            raise ValueError('Shared cap family must use one lane kind and cap references')
        if any(by_id[name]['role']not in('hold_start','hold_end')for name in family['role_templates']):
            raise ValueError('Shared cap context must be a hold endpoint')
    return families


def native_offset(template):
    source=template.get('native_center_pixels',template['anchor_pixels'])
    return np.subtract(source,template['anchor_pixels'])*template['reference_scale_y']


def row_runs(mask,top):
    rows=np.flatnonzero(mask.any(axis=1));result=[]
    for row in rows:
        row=int(row)+top
        if result and result[-1][1]==row:result[-1][1]=row+1
        else:result.append([row,row+1])
    return result


def contexts(detector,image,cap,template,obstructions,bodies):
    donor=detector.by_sampling[key(cap)]
    center=np.array([cap['x']*detector.width,cap['y']*detector.height])+native_offset(donor)
    desired=center-native_offset(template)-template['anchor']
    left,top=np.rint(desired).astype(int);h,w=template['mask'].shape
    if (max(abs(desired-[left,top]))>FORMAT['maximum_center_rounding_pixels']+1e-6
            or not 0<=left<left+w<=detector.width or not 0<=top<top+h<=detector.height):return None
    own=np.zeros((detector.height,detector.width),bool)
    a,b,c,d=cap['bounds_pixels'];own[b:d,a:c]=cap_support(donor,cap)
    required={'connection',*template.get('cap_features',[])};errors={};support=np.zeros((h,w),bool);body_proof=None
    for region in template['regions']:
        if region['name']not in required:continue
        a,b,c,d=region['box'];mask=region['mask'].astype(bool)
        if region['name']=='connection':
            mask=mask&~own[top+b:top+d,left+a:left+c]
            if mask.sum()<FORMAT['minimum_independent_connection_fraction']*region['mask'].sum():return None
        if not mask.any()or(obstructions[top+b:top+d,left+a:left+c]&mask).any():return None
        values=[]
        for part in region.get('_cells')or[region]:
            x,y,z,v=part['box'];selected=part['mask'].astype(bool)
            if region['name']=='connection':selected=selected&~own[top+y:top+v,left+x:left+z]
            if not selected.any():continue
            delta=image[top+y:top+v,left+x:left+z]-template['rgb'][y:v,x:z]
            values.append(float(np.square(delta[selected]).mean()))
        if not values:return None
        error=max(values)
        if not np.isfinite(error)or error>region.get('maximum_error',.015):
            if region['name']!='connection' or (mask&~bodies[0][top+b:top+d,left+a:left+c]).any():return None
            matched=[]
            for pattern,footprint in bodies[1]:
                x,y,z,v=pattern['bounds_pixels'];lo,up,hi,down=max(left+a,x),max(top+b,y),min(left+c,z),min(top+d,v)
                if lo<hi and up<down and (mask[up-top-b:down-top-b,lo-left-a:hi-left-a]&footprint[up-y:down-y,lo-x:hi-x]).any():
                    matched.append({k:pattern[k]for k in (*FIELDS,'region_errors')if k in pattern})
            body_proof={'method':'positive_body_reference_coverage','reference_region_error':error,
                        'covered_pixels':int(mask.sum()),'observations':matched}
            error=max(p['region_errors']['body']for p in matched)
        errors[region['name']]=error
        if region['name']=='connection':support[b:d,a:c]|=mask
    ax,ay=template['anchor']
    return {'template':template['id'],'role':template['role'],
            'x':float((left+ax)/detector.width),'y':float((top+ay)/detector.height),
            'bounds_pixels':[int(left),int(top),int(left+w),int(top+h)],
            **{k:template[k]for k in FIELDS if k.startswith('sampling_')or k=='reference_scale_y'if k in template},
            'region_errors':errors,'connection_rows_pixels':row_runs(support,int(top)),
            **({'body_coverage':body_proof}if body_proof is not None else{})}


def candidates(detector,image,measured):
    families=detector.bank.get('shared_cap_families',[])
    if not families:return []
    roots=detector.resolve(measured);result=[];bodies={}
    for family in families:
        support=np.zeros((detector.height,detector.width),bool);proof=[]
        for root in roots:
            if root['role']!='hold_body'or root.get('cap_subfeature'):continue
            for pattern in [root,*root.get('alternatives',[])]:
                if pattern['template']not in family.get('body_templates',[]):continue
                footprint=detector.by_sampling[key(pattern)]['support']
                a,b,c,d=pattern['bounds_pixels'];support[b:d,a:c]|=footprint;proof.append((pattern,footprint))
        bodies[family['id']]=support,proof
    for root in roots:
        if root['role']=='hold_body':continue
        obstructions=np.zeros((detector.height,detector.width),bool)
        for other in roots:
            if other['role']=='hold_body'or other is root:continue
            a,b,c,d=other['bounds_pixels']
            obstructions[b:d,a:c]|=cap_support(detector.by_sampling[key(other)],other)
        seen=set()
        for cap in [root,*root.get('alternatives',[])]:
            for family in families:
                if cap['template']not in family['appearance_templates']:continue
                cap={**cap,'lane':root['lane'],'skin':root['skin']}
                for template in detector.shared_contexts[family['id']]:
                    identity=key(cap),tuple(cap['bounds_pixels']),key(template)
                    if identity in seen:continue
                    seen.add(identity)
                    context=contexts(detector,image,cap,template,obstructions,bodies[family['id']])
                    if context is None:continue
                    a,b,_,_=cap['bounds_pixels']
                    support=cap_support(detector.by_sampling[key(cap)],cap)
                    result.append({**cap,'role':template['role'],'template_role':template['role'],
                        'classification_status':'full_pattern','reason':'shared_cap_with_positive_role_context',
                        'shared_role':{'format':FORMAT,'family':family['id'],
                            'cap_template_role':cap.get('template_role',root.get('template_role')),
                            'cap_rows_pixels':row_runs(support,b),'context':context}})
    return result
