"""Generic cut-corner caps with short connections beside neighboring borders.

The artwork is generated, not extracted from a recording. References contain
declared neighboring pixels needed for resampling, separately from comparison
regions. The scene oracle stays in TypeScript.
"""
import json

import cv2
import numpy as np


def stamp(image,glyph,x,y):
    """Cut corners expose a wide stem beneath the cap's narrower top/bottom."""
    rows,cols=np.indices((20,20))
    mask=(rows+cols>=5)&(rows+19-cols>=5)&(19-rows+cols>=5)&(38-rows-cols>=5)
    patch=image[y-10:y+10,x-10:x+10]
    patch[mask]=glyph[mask]


def bank_at(root,glyphs,colors,background):
    from piu_timeline.play.skins.bank import load_bank
    entries=[]
    for kind in range(5):
        for arrangement in ('isolated','long','close_hold','close_taps'):
            image=np.full((80,28,3),background,dtype='uint8')
            centers=[18]if arrangement=='isolated'else[18,40]if arrangement.startswith('close')else[18,62]
            held=arrangement in ('long','close_hold')
            if held:image[centers[0]:centers[-1]+1,6:22]=colors[kind]
            for y in centers:stamp(image,glyphs[kind],14,y)
            for i,y in enumerate(centers):
                role='hold_start'if held and i==0 else'hold_end'if held else'tap'
                regions=[('cap',[4,y-10,24,y+10])]
                if held:
                    a,b=(28,30)if arrangement=='close_hold'else(y+10,y+16)if i==0 else(y-16,y-10)
                    regions.append(('connection',[6,a,22,b]))
                else:
                    above=2 if arrangement=='close_taps'and i==1 else 4
                    below=2 if arrangement=='close_taps'and i==0 else 4
                    regions.extend([('clear_above',[6,y-10-above,22,y-10]),
                                    ('clear_below',[6,y+10,22,y+10+below])])
                # Crop context around the measured cap, never compare the
                # neighboring cap merely because its RGB supports the kernel.
                lo=max(0,y-18);hi=min(len(image),y+38 if i==0 and held else y+18)
                if arrangement=='close_taps'and i==0:hi=58
                if i==1:lo=0
                rgb=image[lo:hi];name=f'{kind}-{arrangement}-{i}'
                cv2.imwrite(str(root/(name+'.png')),np.dstack([rgb[:,:,::-1],np.full(rgb.shape[:2],255,dtype='uint8')]))
                entries.append({'id':name,'role':role,'lane_kind':kind,'image':name+'.png',
                    'anchor_pixels':[14,y-lo],'sampling_context':[[0,0,28,len(rgb)]],
                    'regions':[{'name':n,'box':[a,b-lo,c,d-lo],'maximum_error':.002}for n,(a,b,c,d)in regions]})
        for rows in (2,12):
            # Context above/below the measured tile is actual continued stem.
            image=np.full((rows+8,16,3),colors[kind],dtype='uint8');name=f'{kind}-body-{rows}'
            cv2.imwrite(str(root/(name+'.png')),np.dstack([image[:,:,::-1],np.full(image.shape[:2],255,dtype='uint8')]))
            entries.append({'id':name,'role':'hold_body','lane_kind':kind,'image':name+'.png',
                'anchor_pixels':[8,4+rows/2],'sampling_context':[[0,0,16,len(image)]],
                'regions':[{'name':'body','box':[0,4,16,4+rows],'maximum_error':.002}]})
    path=root/'bank.json'
    path.write_text(json.dumps({'schema':1,'skin':'generated-shouldered-caps','spacing_pixels':20,'templates':entries}))
    return load_bank(path)
