"""Synthetic moving-head pixels, independent of popup and receptor events."""
import cv2
import numpy as np

from piu_timeline.play.processing import ReceptorPixels
from piu_timeline.play.pixel_cache import native_measurements,source_contract


def edge_flash_frame(radius=6):
    """A flash clips one possible crop, beside a still-visible moving shape."""
    size=2*radius+1;center=3*radius+2
    mask=np.zeros((size,size),dtype=bool);mask[-6:-1,3:-3]=True
    color=np.zeros((6*radius+5,size),dtype=bool)
    color[center-radius:center+radius+1]=mask
    light=np.zeros_like(color)
    light[center-radius:center-radius+int(np.ceil(.45*size))]=True
    assert not (color&light).any()
    reference={'mask':mask,'poses':[{'mask':mask,'evidence':{
        'anchor_y_pixels':12.6,'crop_center_y_pixels':13}}]}
    return color,light,reference,center+.2,radius,radius/.45


def fixture(root,animated=False,hud=True):
    source=root/'source.mkv';source.write_bytes(b'unchanged recording')
    layout={'lanes':[{'x':.2+.1*i,'color':'blue'}for i in range(5)],'receptor_y':.142,
            'note_y_max':.95,'combo_roi':[.34,.52,.12,.075],'judgment_roi':[.34,.32,.12,.19]}
    if not hud:
        layout.pop('combo_roi');layout.pop('judgment_roi')
    data={'layout':layout,'media':{'path':str(source)},'game_roi':[0,0,325,200],
          'analysis_width':325,'analysis_height':200,'start_seconds':0,'end_seconds':1.4,
          'notes':[{'lane':2,'status':'estimated','target_seconds':1.,'prediction_uncertainty_seconds':.01,
                    'velocity_pixels_per_second':-240.,'points':[]}],'hold_analysis':{'holds':[]}}
    decoded=[]
    for i in range(84):
        t=i/60;y=round(28.4+240*(1-t));image=np.full((200,325,3),70,dtype='uint8')
        if t<1 and 15<=y<185:
            cv2.rectangle(image,(116,y-14),(144,y+14),(255,255,255),-1)
            cv2.rectangle(image,(119,y-11),(141,y+11),(0,130,255),-1)
            if animated:
                image[y-11:y+12,119:142]=70
                left=119+(i%3)*8
                image[y-11:y+12,left:min(left+7,142)]=(0,130,255)
            if y>28.4+32.5*.85:data['notes'][0]['points'].append([t,y])
        if hud:image[74:86,116:145]=255  # Known judgment foreground in the old learning band.
        decoded.append((42+t,t,image))
    pixels=ReceptorPixels(layout,325,200)
    for pts,time,planes,_ in native_measurements(data,root,lambda *args:iter(decoded)):
        pixels.observe_masks(planes,pts,time)
    pixels.save(root/'processing-features.npz',source_contract(data))
    return data,np.array([t for _,t,_ in decoded]),np.array([p for p,_,_ in decoded])

