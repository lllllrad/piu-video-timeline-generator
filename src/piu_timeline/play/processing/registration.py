"""Map a continuously located source crop onto the retained integer pixel grid."""
import math

FORMAT={'schema':1,'method':'source_crop_pixel_phase','axes':['y'],
        'maximum_source_rounding_error_pixels':.5}


def centers(y,evidence,y_range=None):
    """Keep nominal alignment plus floor/ceil of the translated source center.

    A reference cut at round(anchor) stores the head at anchor-round(anchor)
    inside its patch. Translating that patch to a continuous target requires
    preserving this fractional offset before selecting integer image rows.
    """
    nominal=round(y)
    if y_range is not None:
        lo,hi=y_range
        if not all(math.isfinite(v)for v in (lo,hi))or not lo<=y<=hi:raise ValueError('Invalid native position interval')
        phase=evidence.get('anchor_y_pixels',0)-evidence.get('crop_center_y_pixels',0)
        # Cover every integer crop reached anywhere inside the feasible interval.
        exact=centers(y,evidence)
        return sorted(set(exact)|set(range(math.floor(lo-phase+1e-9),math.ceil(hi-phase-1e-9)+1))|
                      set(range(math.floor(lo+1e-9),math.ceil(hi-1e-9)+1)))
    if 'anchor_y_pixels'not in evidence:return [nominal]
    anchor=evidence['anchor_y_pixels'];crop=evidence['crop_center_y_pixels']
    if not math.isfinite(anchor)or crop!=round(anchor):
        raise ValueError('Processing reference crop differs from its native anchor')
    target=y-(anchor-crop)
    result=sorted({nominal,math.floor(target+1e-9),math.ceil(target-1e-9)})
    if any(abs(center-nominal)>1 for center in result):
        raise ValueError('Processing crop phase exceeds native rounding bounds')
    return result
