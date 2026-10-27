"""Narrow beat-row domains using independently located, uniquely placed heads."""
import math

from piu_timeline.play.beats.coordinates import fit, FORMAT as COORDINATE_FORMAT

FORMAT = {'schema': 1, 'revision': 2, 'references': 'frozen_unique_rows_in_shared_native_block',
          'measurement_limits': COORDINATE_FORMAT}


def constrain(options, step, origin, blocks):
    """Intersect existing domains; image geometry cannot add a candidate row."""
    result = list(options);proofs = []
    for index, (lo, hi) in enumerate(options):
        if lo >= hi:
            continue
        for block in blocks:
            heads = block['heads']
            if index not in heads:
                continue
            radius = COORDINATE_FORMAT['reference_radius_seconds']
            references = [dict(r) for r in block.get('references',())
                          if origin+lo*step-radius <= r['target_seconds'] <= origin+hi*step+radius]
            for peer, head in heads.items():
                a,b = options[peer]
                if peer == index or a != b:
                    continue
                target = origin+a*step
                if origin+lo*step-radius <= target <= origin+hi*step+radius:
                    references.append({'note': head.get('native_note',peer), 'target_seconds': target, **head})
            model = fit(references)
            if model is None:
                continue
            lower, upper = model['reference_target_range']
            # A model cannot refute candidates outside its independent anchors.
            if not lower <= origin+lo*step <= origin+hi*step <= upper:
                continue
            error = COORDINATE_FORMAT['maximum_native_error_pixels']+model['maximum_reference_error_pixels']
            velocity = model['velocity_pixels_per_second'];offset = heads[index]['offset']
            time = model['origin_seconds']+(offset-model['offset_at_origin_pixels'])/velocity
            allowed = (max(lo, math.ceil((max(lower,time-error/velocity)-origin)/step-1e-8)),
                       min(hi, math.floor((min(upper,time+error/velocity)-origin)/step+1e-8)))
            before = result[index]
            result[index] = max(before[0],allowed[0]), min(before[1],allowed[1])
            proofs.append({'index': index, 'note': heads[index].get('native_note',index), 'chunk': block['chunk'], 'original_domain': [lo,hi],
                           'allowed_domain': list(allowed), 'measured_offset_pixels': offset,
                           'maximum_position_error_pixels': error, 'model': model})
    return result, proofs
