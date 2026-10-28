"""Warn about observed stops, reversals and speed changes independently of fitting success."""
from piu_timeline.play.frames import TIME_EPSILON

import numpy as np

from piu_timeline.play.screen_regions import overlapping_occluders


def motion_warnings(data, frames):
    result=[]
    layout=data.get('layout',{})
    if len(layout.get('lanes',[]))<2:
        return result
    width,height=data['analysis_width'],data['analysis_height']
    spacing=float(np.median(np.diff([l['x']*width for l in layout['lanes']])))
    pts={f['playback_seconds']:f['source_pts_seconds'] for f in frames}
    for ni,note in enumerate(data.get('notes',[])):
        points=[(t,y) for t,y in note.get('points',[]) if
                layout['receptor_y']*height+.85*spacing<y<layout.get('note_y_max',.95)*height-.55*spacing
                and not overlapping_occluders(layout,note['lane'],y,width,height,spacing)]
        if len(points)<4:
            continue
        def record(reason,lo,hi,**measurements):
            return {'note':ni,'lane':note['lane'],'reason':reason,'check':'scroll_motion',
                    'visible_start_seconds':lo,'visible_end_seconds':hi,'observed_points':len(points),
                    'source_pts_seconds':[pts.get(lo),pts.get(hi)],**measurements}
        start=0;stops=[]
        for j in range(1,len(points)):
            if points[j][0]-points[j-1][0]>.05+TIME_EPSILON or abs(points[j][1]-points[start][1])>.75:
                if j-start>=4 and points[j-1][0]-points[start][0]>=.1-TIME_EPSILON:
                    stops.append((points[start][0],points[j-1][0]))
                start=j
        if len(points)-start>=4 and points[-1][0]-points[start][0]>=.1-TIME_EPSILON:
            stops.append((points[start][0],points[-1][0]))
        for lo,hi in stops:
            result.append(record('possible_scroll_stop_or_capture_freeze',lo,hi,
                                 stationary_duration_seconds=hi-lo,position_tolerance_pixels=.75))
        # Adjacent observed windows are compared with fit error AND pixel
        # quantization. An arbitrary percentage is not a measurement limit.
        windows=[]
        for i in range(0,len(points)-3,4):
            block=np.asarray(points[i:i+4],dtype=float)
            span=block[-1,0]-block[0,0]
            if span<.05-TIME_EPSILON or np.diff(block[:,0]).max()>.05+TIME_EPSILON:
                continue
            x=block[:,0]-block[0,0];y=block[:,1]
            slope,intercept=np.polyfit(x,y,1)
            residual=y-(slope*x+intercept)
            error=3*np.sqrt(np.dot(residual,residual)/max(1,len(x)-2)/max(np.sum((x-x.mean())**2),1e-9))+2/span
            windows.append((float(block[0,0]),float(block[-1,0]),float(slope),float(error)))
        reverse=[]
        for window in windows:
            if window[2]<=window[3]:continue
            if not reverse or window[0]-reverse[-1][-1][1]>.05+TIME_EPSILON:
                reverse.append([])
            reverse[-1].append(window)
        for run in reverse:
            result.append(record('reverse_scroll_motion',run[0][0],run[-1][1],
                                 direction='downward',observed_points=4*len(run),
                                 direction_windows=len(run),
                                 velocity_lower_bound_pixels_per_second=min(w[2]-w[3]for w in run),
                                 velocity_upper_bound_pixels_per_second=max(w[2]+w[3]for w in run)))
        changes=[]
        for before,after in zip(windows,windows[1:]):
            if after[0]-before[1]>.05+TIME_EPSILON or abs(after[2]-before[2])<=before[3]+after[3]:
                continue
            changes.append(record('scroll_speed_change',before[0],after[1],
                                  velocity_before_pixels_per_second=before[2],velocity_after_pixels_per_second=after[2],
                                  velocity_error_before=before[3],velocity_error_after=after[3]))
        result.extend(changes)
    return result
