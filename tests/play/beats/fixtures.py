"""Generate native observation records from an independently specified tap chart."""


def native_scene(events,spacing=40.,fps=60,lanes=5):
    width,height=spacing*16.25,spacing*9.125
    receptor,velocity=spacing*1.3,spacing*6
    times=[.2+i/fps for i in range(round(.85*fps)+1)]
    notes=[];registrations=[];offsets=[]
    for index,(target,lane)in enumerate(events):
        points=[(t,receptor+velocity*(target-t))for t in times
                if receptor+.85*spacing<receptor+velocity*(target-t)<.95*height-.55*spacing]
        notes.append({'lane':lane,'status':'estimated','target_seconds':target,
                      'prediction_uncertainty_seconds':.5/fps,'points':points,
                      'motion_clock':{'origin':0,'velocity':velocity,'intercept':0},
                      'motion_target_phase':velocity*target})
        registrations.append({'note':index,'status':'registered','coordinate_method':'native_cap_measurements',
                              'coordinate_uncertainty_pixels':.025*spacing,
                              'observations':[{'time':t,'source_pts_seconds':80+t}for t,_ in points]})
        offsets.append({'note':index,'offset_pixels':receptor+velocity*target})
    return {'analysis_width':width,'analysis_height':height,'start_seconds':.2,'end_seconds':2.2,
            'layout':{'receptor_y':receptor/height,'note_y_max':.95,
                      'lanes':[{'x':.1+i*spacing/width}for i in range(lanes)]},
            'notes':notes,'head_registration':{'notes':registrations},
            'scroll_motion':{'samples':[{'time':t,'source_pts':80+t,'phase':velocity*t,'chunk':0}for t in times],
                             'coordinate_registration':{'chunks':[{'chunk':0,'status':'fitted','head_offsets':offsets}]}}}
