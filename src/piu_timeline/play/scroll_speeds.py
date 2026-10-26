"""Measured relative speed transitions, distinct from official BPM and input timing."""
import numpy as np


def apply(data):
    models=[]
    for effect in data.get('chart_policy',{}).get('gimmick_candidates',[]):
        if effect['kind']!='scroll_speed_change' or effect['review_status']=='rejected':continue
        origin=effect['playback_start_seconds']-effect['start_seconds']
        models.append({'id':effect['id'],'start':effect['playback_start_seconds'],'end':effect['playback_end_seconds'],
                       'transition_range':[origin+t for t in effect['transition_range_seconds']],
                       'ratio':effect['speed_multiplier'],'ratio_range':effect['speed_ratio_range']})
    return {**data,'scroll_speed_model':models}


def observed_path(note,data,receptor,spacing,scale):
    points=np.asarray(note.get('points',[]),dtype=float)
    if len(points)<8:return None
    owners=[m for m in data.get('scroll_speed_model',[]) if points[0,0]<m['transition_range'][0]
            and points[-1,0]>m['transition_range'][1]]
    if not owners:return None
    failed={'supported':False,'basis':'configured_speed_native_trajectory','velocity':0,'target':None}
    if len(owners)!=1:return failed
    model=owners[0];lo,hi=model['transition_range'];center=(lo+hi)/2;ratio=model['ratio']
    bottom=data.get('layout',{}).get('note_y_max',.95)*data['analysis_height']*scale-.55*spacing
    kept=points[(points[:,0]>=model['start'])&(points[:,0]<=model['end'])
                &(points[:,1]*scale>receptor+.85*spacing)&(points[:,1]*scale<bottom)]
    if sum(kept[:,0]<lo)<4 or sum(kept[:,0]>hi)<4:return failed
    # The piecewise clock is a hypothesis checked against this actual head.
    # Multiple changes, a curved ramp or contradictory geometry stay unresolved.
    times=kept[:,0]-center;clock=np.where(times<0,times,ratio*times)
    speed,intercept=np.polyfit(clock,kept[:,1]*scale,1)
    residual=float(np.sqrt(np.mean((kept[:,1]*scale-(speed*clock+intercept))**2)))
    if speed>=-spacing or residual>max(.75,.04*spacing):return failed
    phase=(receptor-intercept)/speed
    target=float(center+(phase if phase<0 else phase/ratio))
    if not kept[-1,0]<=target<=min(model['end'],kept[-1,0]+.25):return failed
    def position(time):
        if not model['start']<=time<=model['end']:return None
        delta=time-center
        return float(intercept+speed*(delta if delta<0 else ratio*delta))
    return {'supported':True,'basis':'configured_speed_native_trajectory','velocity':float(speed*(ratio if target>=center else 1)),
            'target':target,'position':position}


def classify_warnings(data,records):
    remaining,expected=[],[]
    for record in records:
        owners=[]
        if record['reason']=='scroll_speed_change':
            a=-record['velocity_before_pixels_per_second'];b=-record['velocity_after_pixels_per_second']
            ea=record['velocity_error_before'];eb=record['velocity_error_after']
            if a>ea and b>eb:
                bounds=[(b-eb)/(a+ea),(b+eb)/(a-ea)]
                for model in data.get('scroll_speed_model',[]):
                    lo,hi=model['transition_range']
                    if (record['visible_start_seconds']<=hi and record['visible_end_seconds']>=lo
                            and max(bounds[0],model['ratio_range'][0])<=min(bounds[1],model['ratio_range'][1])):
                        owners.append(model['id'])
        if owners:
            expected.append({**record,'native_reason':record['reason'],'reason':'configured_scroll_speed_change',
                             'gimmick_candidates':owners})
        else:remaining.append(record)
    return remaining,expected
