"""Map a continuously located source crop onto the retained integer pixel grid."""
import math

FORMAT={'schema':1,'method':'source_crop_pixel_phase','axes':['y'],
        'maximum_source_rounding_error_pixels':.5}


def centers(y,evidence):
    """Keep nominal alignment plus floor/ceil of the translated source center.

    A reference cut at round(anchor) stores the head at anchor-round(anchor)
    inside its patch. Translating that patch to a continuous target requires
    preserving this fractional offset before selecting integer image rows.
    """
    nominal=round(y)
    if 'anchor_y_pixels'not in evidence:return [nominal]
    anchor=evidence['anchor_y_pixels'];crop=evidence['crop_center_y_pixels']
    if not math.isfinite(anchor)or crop!=round(anchor):
        raise ValueError('Processing reference crop differs from its native anchor')
    target=y-(anchor-crop)
    result=sorted({nominal,math.floor(target+1e-9),math.ceil(target-1e-9)})
    if any(abs(center-nominal)>1 for center in result):
        raise ValueError('Processing crop phase exceeds native rounding bounds')
    return result
