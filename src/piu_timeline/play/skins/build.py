"""Extract editable, source-bound RGB references from reviewed image rectangles."""
import json
from pathlib import Path

import cv2
import numpy as np

from piu_timeline.play.skins.bank import load_bank


def build(specification, output):
    specification, output = Path(specification).resolve(), Path(output).resolve()
    spec = json.loads(specification.read_text())
    if output.exists():
        raise ValueError('Refusing to overwrite an existing skin bank')
    output.mkdir(parents=True)
    entries = []
    for item in spec['templates']:
        source = (specification.parent / item['source_image']).resolve()
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError('Missing reference source image: ' + str(source))
        x0, y0, x1, y1 = item['crop']
        if not 0 <= x0 < x1 <= image.shape[1] or not 0 <= y0 < y1 <= image.shape[0]:
            raise ValueError('Reference crop extends outside its source image')
        reference_width = spec.get('analysis_width', image.shape[1])
        if type(reference_width) is not int or not 320 <= reference_width <= 1300:
            raise ValueError('Reference analysis width must be 320..1300')
        sx = reference_width / image.shape[1]
        reference_height = round(image.shape[0] * sx)
        sy = reference_height / image.shape[0]
        # Resize the full source image before cropping. Resizing an odd-origin
        # crop independently changes the source pixel sampling phase.
        resized = cv2.resize(image, (reference_width, reference_height), interpolation=cv2.INTER_AREA)
        left, top, right, bottom = round(x0*sx), round(y0*sy), round(x1*sx), round(y1*sy)
        crop = resized[top:bottom, left:right]
        def transform(box):
            return [round((x0+box[0])*sx)-left,round((y0+box[1])*sy)-top,
                    round((x0+box[2])*sx)-left,round((y0+box[3])*sy)-top]
        regions = [{**r,'box':transform(r['box']),
                    **({'comparison_boxes':[transform(box)for box in r['comparison_boxes']]}
                       if 'comparison_boxes'in r else{})}for r in item['regions']]
        context=[transform(box)for box in item.get('sampling_context',[])]
        alpha = np.zeros(crop.shape[:2], dtype='uint8')
        for box in [*[r['box']for r in regions],*context]:
            a,b,c,d=box
            if not 0 <= a < c <= crop.shape[1] or not 0 <= b < d <= crop.shape[0]:
                raise ValueError('Reference support is outside its crop')
            alpha[b:d, a:c] = 255
        name = f'{len(entries):04}.png'
        cv2.imwrite(str(output / name), np.dstack([crop, alpha]))
        entries.append({key: value for key, value in item.items() if key not in ('source_image', 'crop')}
                       | {'image': name, 'source_image': str(source), 'source_crop': item['crop'],
                          'regions': regions, 'anchor_pixels': [(x0+item['anchor_pixels'][0])*sx-left,
                                                              (y0+item['anchor_pixels'][1])*sy-top],
                          **({'sampling_context':context}if context else{})})
    (output / 'bank.json').write_text(json.dumps({'schema': 1, 'skin': spec['skin'],
        'spacing_pixels': spec['spacing_pixels']*sx, 'templates': entries}, indent=2) + '\n')
    load_bank(output / 'bank.json')
    return output / 'bank.json'
