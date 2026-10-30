"""Generic event input for native body-risk adapter integration."""

def evidence():
    return {'notes':[{'status':'estimated','lane':i,'target_seconds':t,'prediction_uncertainty_seconds':.01}
                     for i,t in enumerate((1.,1.1))],
            'matches':[{'note':0,'target_seconds':1.,'combo_event':None,'judgment_event':0,
                        'observation_lower_seconds':1.01,'observation_upper_seconds':1.02,
                        'judgment_label':'GREAT','evidence_source':'judgment'}],
            'combo_events':[{'delta':2,'lower_seconds':1.,'upper_seconds':1.08,
                             'before':10,'after':12,'status':'excluded','reason':'ambiguous_note_or_combo_association'}],
            'judgment_events':[{'label':'GREAT','delta':1,'lower_seconds':1.01,'upper_seconds':1.02,'status':'matched'}],
            'hold_analysis':{'holds':[], 'receptor_runs':[
                {'lane':i,'lit':True,'frames':3,'start_seconds':hi,'end_seconds':hi+.04,
                 'onset_range':[lo,hi],'onset_source_pts_seconds':[100+lo,100+hi]}
                for i,(lo,hi) in enumerate(((1.,1.01),(1.06,1.08)))]}}
