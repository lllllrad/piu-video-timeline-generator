"""Consumer views of exact image comparisons; native traces remain unchanged."""


def role_image(image):
    """Retain exactly the first comparison used for each reported role."""
    alternatives=[]
    for role in image.get('conflicting_roles',[image['role']]):
        proof=next((p for p in [image,*image.get('alternatives',[])]
                    if p.get('template_role',p['role'])==role
                    and p.get('classification_status','full_pattern')in('full_pattern','cap_role_pattern','conflict')),image)
        if proof is not image and all(proof is not p for p in alternatives):alternatives.append(proof)
    return {**{k:v for k,v in image.items()if k!='alternatives'},'alternatives':alternatives}


class GeometryImage(dict):
    """Exact compared-row results bound to this calculation's reference objects."""
    def __init__(self,image,queries):
        from piu_timeline.play.skins.coverage import image_spans
        super().__init__(role_image(image))
        self.spans={(id(ref),cap,full):image_spans(image,ref,cap_only=cap,full_only=full)
                    for ref,cap,full in queries}


def geometry_frames(native,references,cap_references,body_references):
    def queries(image):
        result=[]
        if image['role']in('hold_start','hold_body','hold_end'):result.append((references,False,False))
        if image['role']=='unknown'and image.get('classification_status')=='cap_only':result.append((cap_references,True,False))
        if body_references is not None and image['role']in('hold_start','hold_end'):result.append((body_references,False,True))
        return result
    return [{'playback_seconds':f['playback_seconds'],'source_pts_seconds':f['source_pts_seconds'],
             'skin_observations':[GeometryImage(image,queries(image))for image in f.get('skin_observations',[])]}
            for f in native]


def channel_frames(native):
    """Popup scalars, motion positions and exact role proofs, without unused searches."""
    return [{**{k:v for k,v in f.items()if not isinstance(v,(list,dict))},
             'notes':[{k:n[k]for k in ('lane','x','y','quality')if k in n}for n in f.get('notes',[])],
             'skin_observations':[role_image(image)for image in f.get('skin_observations',[])]}
            for f in native]
