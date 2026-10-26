"""Concrete zero-speed intervals; preserve observations and unresolved chart times."""
import numpy as np


def apply(data):
    effects = [e for e in data.get('chart_policy',{}).get('gimmick_candidates',[])
               if e['kind']=='scroll_pause' and e['review_status']!='rejected']
    return {**data,'scroll_pause_model':[
        {'id':e['id'],'start':e['playback_start_seconds'],'end':e['playback_end_seconds'],
         'speed_multiplier':0,'boundary_uncertainty_seconds':e['boundary_uncertainty_seconds']}
        for e in effects]}


def moving_time(times, pauses):
    result = np.asarray(times,dtype=float).copy()
    for pause in pauses:
        result -= np.clip(np.asarray(times)-pause['start'],0,pause['end']-pause['start'])
    return result


def observed_path(note, data, receptor, spacing, scale):
    """Use measured positions in a clock that pauses; never fabricate presses."""
    points = np.asarray(note.get('points',[]),dtype=float)
    pauses = data.get('scroll_pause_model',[])
    if len(points)<4 or not pauses:
        return None
    pauses = sorted([p for p in pauses if points[0,0]<=p['end'] and points[-1,0]>=p['start']],key=lambda p:p['start'])
    if not pauses:
        return None
    failed = {'supported':False,'basis':'configured_pause_native_trajectory','velocity':0,'target':None}
    bottom=data.get('layout',{}).get('note_y_max',.95)*data['analysis_height']*scale-.55*spacing
    points=points[(points[:,1]*scale>receptor+.85*spacing)&(points[:,1]*scale<bottom)]
    if len(points)<8:
        return failed
    # Both moving flanks establish speed independently of stationary duration.
    before=points[:,0]<pauses[0]['start'];after=points[:,0]>pauses[-1]['end']
    if sum(before)<4 or sum(after)<4:
        return failed
    for pause in pauses:
        interior=points[(points[:,0]>=pause['start'])&(points[:,0]<=pause['end'])]
        if len(interior)<4 or np.ptp(interior[:,1]*scale)>max(.75,.04*spacing):
            return failed
    times=moving_time(points[:,0],pauses);origin=times[-1]
    speed,intercept=np.polyfit(times-origin,points[:,1]*scale,1)
    residual=float(np.sqrt(np.mean((points[:,1]*scale-(speed*(times-origin)+intercept))**2)))
    if speed>=-spacing or residual>max(.75,.04*spacing):
        return failed
    target=float(origin+(receptor-intercept)/speed)
    for pause in pauses:
        if target>=pause['start']-max(.75,residual)/abs(speed):
            if abs(target-pause['start'])<=max(.75,residual)/abs(speed):
                return failed  # Crossing at a plateau has no unique target.
            target+=pause['end']-pause['start']
    if not 0<=target-points[-1,0]<=.25:
        return failed
    def position(time):
        return float(speed*(moving_time([time],pauses)[0]-origin)+intercept)
    return {'supported':True,'basis':'configured_pause_native_trajectory','velocity':float(speed),
            'target':target,'position':position,'residual_pixels':residual}


def classify_warnings(data, records):
    """Recognize only measured stationary states and their zero-speed edges."""
    warnings,expected=[],[]
    for record in records:
        owners=[]
        for pause in data.get('scroll_pause_model',[]):
            lo,hi=record['visible_start_seconds'],record['visible_end_seconds']
            error=pause['boundary_uncertainty_seconds']
            if (record['reason']=='possible_scroll_stop_or_capture_freeze'
                    and pause['start']-error<=lo and hi<=pause['end']+error):
                owners.append(pause['id'])
            elif record['reason']=='scroll_speed_change':
                stopped_after=abs(record['velocity_after_pixels_per_second'])<=record['velocity_error_after']
                stopped_before=abs(record['velocity_before_pixels_per_second'])<=record['velocity_error_before']
                if (stopped_after and lo-error<=pause['start']<=hi+error
                        or stopped_before and lo-error<=pause['end']<=hi+error):
                    owners.append(pause['id'])
        if owners:
            expected.append({**record,'native_reason':record['reason'],'reason':'configured_scroll_pause',
                             'gimmick_candidates':owners,'speed_multiplier':0})
        else:
            warnings.append(record)
    return warnings,expected


def refresh_processing(data,directory):
    """Reinterpret retained receptor pixels with the paused motion model."""
    path=directory/'processing-features.npz'
    if not data.get('scroll_pause_model') or not path.is_file():
        return data
    from piu_timeline.play.processing import observe_processing
    channels=data.get('visual_channels',{})
    processing={**channels.get('processing',{}),**observe_processing(data,path)}
    for record in processing['notes']:
        record['id']='processing:'+str(record['note'])
    return {**data,'visual_channels':{**channels,'processing':processing}}
