"""Measure position-discriminating cap pixels, without selecting a coordinate."""
import numpy as np

from piu_timeline.play.skins.sampling import key
from piu_timeline.play.skins.support import cap_support

FORMAT={'schema':1,'method':'visible_cap_rgb_and_vertical_contrast',
        'contrast_threshold':'cap_squared_rgb_error_bound','numeric_error':32*np.finfo('float64').eps}


def measure(image,template,record):
    a,b,c,d=record['bounds_pixels'];patch=image[b:d,a:c]
    support=cap_support(template,record)&template['cap_core_support']
    cap=next(r for r in template['regions']if r['name']=='cap')
    reference=template['rgb'].astype('float64');observed=patch.astype('float64')
    pairs=support[:-1]&support[1:]
    expected=np.diff(reference,axis=0)
    selected=pairs&(np.square(expected).mean(axis=2)>cap.get('maximum_error',.015))
    return {'method':FORMAT['method'],'compared_pixels':int(support.sum()),
            'squared_rgb_error':float(np.square(observed[support]-reference[support]).mean())if support.any()else None,
            'vertical_contrast_pixels':int(selected.sum()),
            'vertical_contrast_error':float(np.square(np.diff(observed,axis=0)[selected]-expected[selected]).mean())if selected.any()else None}


def acquire(detector,image,candidates):
    for record in candidates:
        if record['role']=='hold_body':continue
        record['cap_localization']=measure(image,detector.by_sampling[key(record)],record)
    return candidates
