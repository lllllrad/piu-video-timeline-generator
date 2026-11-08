"""Keep neighboring cap artwork out of positive connector measurements."""
import numpy as np

from piu_timeline.play.skins.overlap import runs
from piu_timeline.play.skins.sampling import key
from piu_timeline.play.skins.spatial import visible_region,cells
from piu_timeline.play.skins.classification import identify


FORMAT={'schema':1,'method':'connector_pixels_independent_of_other_caps',
        'same_object':'resolved_cap_anchor_group','hidden_pixels':'never_positive_body_support',
        'endpoint_clip':'opposite_same_lane_cap_full_edge_rows','minimum_retained_connector_fraction':.5,
        'maximum_cap_sampling_weight':.5,'opacity':'absolute_source_kernel_weights',
        'cap_only_remeasurement':'qualified_cap_with_observed_connector_pixels'}


def visible_connector(image,template,region,left,top,hidden,edge_hidden):
    a,b,c,d=region['box'];mask=region['mask'].astype(bool)
    available=mask&~edge_hidden[top+b:top+d,left+a:left+c]
    rows=np.flatnonzero(available.any(axis=1))
    if not len(rows):return None,[]
    lo,hi=int(rows.min()),int(rows.max())+1
    if (lo or hi<len(mask))and mask[lo:hi].sum()>=FORMAT['minimum_retained_connector_fraction']*mask.sum():
        # A neighboring endpoint can hide the far edge. It cannot erase a
        # side column or an interior hole from the remaining spatial checks.
        clipped={**region,'box':[a,b+lo,c,b+hi],'mask':region['mask'][lo:hi].copy()}
        clipped['_cells']=list(cells(clipped))
        measured=visible_region(image,template,clipped,left,top,hidden)
        if measured is None:return None,[]
        support=np.zeros_like(mask);support[lo:hi]=measured[1]
        return (measured[0],support),[[top+b,top+b+lo],[top+b+hi,top+d]]
    return visible_region(image,template,region,left,top,hidden),[]


def qualify(detector,image,candidates):
    roots=detector.resolve(candidates)
    caps=[r for r in roots if r['role']!='hold_body']
    sources=[({**r,'foreground_bounds_pixels':r['bounds_pixels'],'sampling_influence_pixels':0},
              detector.by_sampling[key(r)]['cap_foreground_fraction'])for r in caps]
    masks=[]
    for source,mask in sources:
        a,b,c,d=source['foreground_bounds_pixels']
        plane=np.zeros((detector.height,detector.width),dtype='float32');plane[b:d,a:c]=mask;masks.append(plane)
    total=np.sum(masks,axis=0)if masks else np.zeros((detector.height,detector.width),dtype='float32')
    hidden_cache={};edge_cache={};result=[]
    for record in candidates:
        role=record.get('template_role',record['role'])
        if (role not in ('hold_start','hold_end')or record['classification_status']not in('full_pattern','cap_only')
                or record.get('shared_role')):
            result.append(record);continue
        template=detector.by_sampling[key(record)]
        cap_basis='original_full_pattern'
        if record['classification_status']=='cap_only':
            identified=identify(template,record)
            if not(record.get('cap_context_qualified')or record.get('occlusion_evidence')
                   or identified.get('classification_status')=='cap_role_pattern'):
                result.append(record);continue
            cap_basis=('complete_cap_context'if record.get('cap_context_qualified')else
                       'observed_cap_with_measured_foreground'if record.get('occlusion_evidence')else
                       'declared_discriminating_cap_features')
            other=[r for r in template['regions']if r['name']not in('cap','connection')]
            if any(record['region_errors'].get(r['name'])is None
                   or record['region_errors'][r['name']]>r.get('maximum_error',.015)for r in other):
                result.append(record);continue
        owner=next((i for i,root in enumerate(caps)if root['lane']==record['lane']
                    and abs(root['y']-record['y'])*detector.height<detector.same_anchor_pixels),None)
        if owner is None:raise ValueError('Connector comparison has no resolved cap owner')
        if owner not in hidden_cache:
            hidden_cache[owner]=(total-masks[owner])>FORMAT['maximum_cap_sampling_weight']+1e-7
        hidden=hidden_cache[owner]
        region=next(r for r in template['regions']if r['name']=='connection')
        left,top=record['bounds_pixels'][:2];a,b,c,d=region['box']
        intersects=(region['mask'].astype(bool)&hidden[top+b:top+d,left+a:left+c]).any()
        failed=record['region_errors'].get('connection')
        if not intersects and(record['classification_status']=='full_pattern'
                               or failed is not None and failed>region.get('maximum_error',.015)):
            result.append(record);continue
        if (owner,role)not in edge_cache:
            opposing=[masks[i]for i,root in enumerate(caps)if i!=owner and root['lane']==record['lane']
                      and (root['y']>caps[owner]['y']if role=='hold_start'else root['y']<caps[owner]['y'])]
            edge_cache[owner,role]=(np.sum(opposing,axis=0)>FORMAT['maximum_cap_sampling_weight']+1e-7)if opposing else np.zeros_like(hidden)
        edge_hidden=edge_cache[owner,role]
        measured,clipped=visible_connector(image,template,region,left,top,hidden,edge_hidden)
        proof={'method':FORMAT['method'],'comparison_classification_status':record['classification_status'],
               'cap_identification':cap_basis,
               'full_region_error':record['region_errors'].get('connection'),
               'foreground_caps':[{k:source[k]for k in ('lane','template','bounds_pixels','foreground_bounds_pixels','sampling_influence_pixels')}
                                  for i,(source,_)in enumerate(sources)if i!=owner
                                  and masks[i][top+b:top+d,left+a:left+c].any()]}
        proof['clipped_connector_rows_pixels']=[span for span in clipped if span[0]<span[1]]
        output={**record,'connector_ownership':proof,'visible_cap_runs':record.get('visible_cap_runs',runs(template['cap_support']))}
        support=np.zeros(template['mask'].shape,bool)
        if measured is not None and measured[0]<=region.get('maximum_error',.015):
            support[b:d,a:c]=measured[1]
            proof.update(status='independent_visible_connector',visible_connector_pixels=int(support.sum()),visible_connector_error=measured[0])
            if record['classification_status']=='cap_only':
                output.update(role=role,classification_status='full_pattern',reason='skin_visible_connector_with_measured_foreground',
                    region_errors={**record['region_errors'],'connection_context':record['region_errors'].get('connection'),'connection':measured[0]},
                    quality=min(record['quality'],1-measured[0]/region.get('maximum_error',.015)))
                if 'unavailable_regions'in output:output['unavailable_regions']=[n for n in output['unavailable_regions']if n!='connection']
        else:
            proof.update(status='connector_obscured_by_other_caps',visible_connector_pixels=0)
            output.update(role='unknown',classification_status='cap_only',reason='skin_connection_obscured_by_other_caps',
                          unavailable_regions=sorted(set(record.get('unavailable_regions',[]))|{'connection'}))
        output['visible_connection_runs']=runs(support)
        result.append(output)
    return result
