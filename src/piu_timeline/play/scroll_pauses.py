"""Acquire processing pixels around concrete models calculated in TypeScript."""
from piu_timeline.derived import call


def model_input(data):
    return {key:data[key]for key in ('layout','analysis_height','scroll_pause_model','scroll_speed_model')if key in data}


def position_adapter(result,chunks=None):
    if not result or not result['supported']:return result
    model=result['position_model']
    if model['kind']=='registered':
        samples,times,_=chunks[model['chunk']]
        original=chunks[model['from_chunk']][2]if model['from_chunk']is not None else {}
    def position(time):
        if model['kind']=='linear':return model['receptor']+model['velocity']*(time-model['target'])
        if model['kind']=='registered':
            from bisect import bisect_left
            if time in original:return model['receptor']+(model['motion_target_phase']-original[time]['phase'])*model['scale']
            i=bisect_left(times,time-1e-6)
            if i==len(samples)or abs(times[i]-time)>1e-6:return None
            return model['receptor']+(model['phase']-samples[i]['phase'])*model['scale']
        if model['kind']=='pause':
            moving=time-sum(min(max(time-p['start'],0),p['end']-p['start'])for p in model['pauses'])
            return model['speed']*(moving-model['origin'])+model['intercept']
        bounds=model['model']
        if not bounds['start']<=time<=bounds['end']:return None
        delta=time-model['center']
        return model['intercept']+model['speed']*(delta if delta<0 else bounds['ratio']*delta)
    return {**result,'position':position}


def apply(data):
    return {**data,'scroll_pause_model':call('scroll.models',{'chart_policy':data.get('chart_policy',{})},'pause')}


def moving_time(times,pauses):
    import numpy as np
    return np.asarray(call('scroll.movingTime',list(times),pauses))


def observed_path(note,data,receptor,spacing,scale):
    return position_adapter(call('scroll.pausePath',{'points':note.get('points',[])},model_input(data),receptor,spacing,scale))


def classify_warnings(data,records):
    return tuple(call('scroll.classify',model_input(data),records,'pause'))


def refresh_processing(data,directory):
    """Reinterpret retained receptor pixels with the paused motion model."""
    path=directory/'processing-features.npz'
    if not (data.get('scroll_pause_model') or data.get('scroll_speed_model')) or not path.is_file():
        return data
    from piu_timeline.play.processing import observe_processing
    channels=data.get('visual_channels',{})
    processing={**channels.get('processing',{}),**observe_processing(data,path)}
    for record in processing['notes']:
        record['id']='processing:'+str(record['note'])
    return {**data,'visual_channels':{**channels,'processing':processing}}
