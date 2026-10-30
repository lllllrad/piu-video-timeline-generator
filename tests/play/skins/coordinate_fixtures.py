"""Generic coordinate inputs for native image-adapter integration tests."""

def clock_fixture():
    times=[.5+i*.02 for i in range(10)]
    notes=[{'lane':i%3,'status':'estimated','target_seconds':1+i*.125,
            'points':[(t,40+240*(1+i*.125-t))for t in times],
            'motion_clock':{'origin':0,'velocity':244 if i==4 else 240,'intercept':0},
            'motion_target_phase':240*(1+i*.125)}for i in range(9)]
    return {'analysis_height':600,'layout':{'receptor_y':40/600},'notes':notes,
            'head_registration':{'notes':[{'note':i,'status':'registered','coordinate_method':'native_cap_measurements',
                'observations':[{'time':t}for t in times]}for i in range(9)]},
            'scroll_motion':{'samples':[{'time':t,'source_pts':80+t,'phase':240*t,'chunk':0}for t in times],
                'coordinate_registration':{'chunks':[{'chunk':0,'status':'fitted','head_offsets':[
                    {'note':i,'offset_pixels':40+240*(1+i*.125)}for i in range(9)]}]}}}

def chord_fixture():
    times=[.6+i*.01 for i in range(9)]
    notes=[{'lane':i,'status':'estimated','target_seconds':target,'prediction_uncertainty_seconds':error,
            'points':[[t,40+500*(actual-t)]for t in times]}
           for i,(target,error,actual)in enumerate(((1.001,.006,1.),(1.02,.03,1.),(1.03125,.002,1.03125)))]
    records=[{'note':i,'status':'registered','coordinate_method':'native_cap_measurements','coordinate_uncertainty_pixels':1.,
              'observations':[{'time':t,'source_pts_seconds':50+t}for t in times]}for i in range(3)]
    return {'notes':notes,'head_registration':{'notes':records},'analysis_width':400,'analysis_height':400,
            'layout':{'receptor_y':.1,'lanes':[{'x':.2+.1*i}for i in range(3)]}}
