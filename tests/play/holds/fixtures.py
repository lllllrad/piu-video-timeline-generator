"""Synthetic measured future holds and independent native popup observations."""
from piu_timeline.play.skins.held import FORMAT


def scenario():
    notes=[{'lane':0,'status':'estimated','type_status':'tap','target_seconds':1.01,'prediction_uncertainty_seconds':.005},
           {'lane':1,'status':'estimated','target_seconds':1.15,'prediction_uncertainty_seconds':.01,
            'velocity_pixels_per_second':-500},
           {'lane':1,'status':'estimated','target_seconds':1.35,'prediction_uncertainty_seconds':.01,
            'velocity_pixels_per_second':-500}]
    hold={'id':0,'head_note':1,'tail_note':2,'covered_notes':[1,2],'lane':1,
          'start_range':[1.14,1.16],'end_range':[1.34,1.36],'start_censored':False,'end_censored':False,
          'body_frames':8,'body_evidence':'skin_start_body_end_images','input':{'segments':[]}}
    warning={'hold':0,'note':1,'tail_note':2,'lane':1,
             'failure_detail':'known_hold_image_connection_not_observed_in_clear_frames',
             'visible_start_seconds':.8,'visible_end_seconds':1.12}
    event={'label':'PERFECT','delta':1,'lower_seconds':1.,'upper_seconds':1.017,
           'status':'excluded','reason':'possible_hold_or_dense_stack','detection_status':'candidate'}
    return {'notes':notes,'layout':{'receptor_y':.1,'lanes':[{'x':.2},{'x':.3}]},'analysis_width':200,
            'skin_detector':{'contract':{'held_body':FORMAT},'missing_template_roles':[]},
            'unsupported_intervals':[{'start_seconds':1.11,'end_seconds':1.12}],
            'matches':[],'deferred_matches':[],'combo_events':[],'judgment_events':[event],
            'coverage':{},'limitations':[],
            'hold_analysis':{'holds':[hold],'unresolved_tracks':[warning],'receptor_runs':[]},
            'visual_channels':{'note_types':{'notes':[{'note':0,'observations':[{
                'kind':'tap','role':'tap','reason':'image_cap_with_native_clearance',
                'playback_seconds':.9,'source_pts_seconds':10.9}]}]}}}

