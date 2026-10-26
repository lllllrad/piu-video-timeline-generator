"""Account for every interruption of a previously observed native head."""
from bisect import bisect_left, bisect_right
from collections import Counter

import numpy as np

from piu_timeline.play.screen_regions import note_occluders, overlapping_occluders

FORMAT = {'schema':1, 'revision':1}


def continuity_diagnostics(data, frames):
    """Inspect internal holes and premature endings, including successful fits."""
    warnings, occlusions, exits = [],[],[]
    if not frames or not data.get('layout',{}).get('lanes'):
        return {'format':FORMAT,'warnings':[], 'known_occlusions':[], 'accounted_exits':[], 'counts':{}}
    times = [f['playback_seconds'] for f in frames]
    width,height = data['analysis_width'],data['analysis_height']
    layout = data['layout']
    spacing = float(np.median(np.diff([l['x']*width for l in layout['lanes']])))
    receptor = layout['receptor_y']*height
    peers = {s['time']:s for s in data.get('scroll_motion',{}).get('samples',[])}
    processing = {p['note']:p for p in data.get('visual_channels',{}).get('processing',{}).get('notes',[])}
    for ni,note in enumerate(data.get('notes',[])):
        points = note.get('points',[])
        if not points:
            continue
        # Native source detections are the authority. No fitted target, input
        # match, hold membership or majority vote makes a missing frame present.
        observed = {t for t,_ in points}
        pending = []
        for pi,(t,y) in enumerate(points):
            last = pi == len(points)-1
            end = min(times[-1],t+.65) if last else points[pi+1][0]
            first_frame = bisect_right(times,t)
            last_frame = bisect_left(times,end) if not last else bisect_right(times,end)
            if first_frame >= last_frame:
                continue
            recent = np.asarray(points[max(0,pi-11):pi+1],dtype=float)
            velocity = None
            if len(recent)>=4 and recent[-1,0]-recent[0,0]>=.065:
                slope,intercept = np.polyfit(recent[:,0]-t,recent[:,1],1)
                residual = np.sqrt(np.mean((recent[:,1]-np.polyval([slope,intercept],recent[:,0]-t))**2))
                if slope < -spacing and residual <= .14*spacing:
                    velocity = float(slope)
            start_peer = peers.get(t)
            for fi in range(first_frame,last_frame):
                frame = frames[fi];now=times[fi]
                if now in observed:
                    continue
                peer = peers.get(now)
                if start_peer and peer and start_peer['chunk']==peer['chunk']:
                    predicted = y-(peer['phase']-start_peer['phase'])
                    method = 'peer_displacement'
                elif not last:
                    nt,ny = points[pi+1]
                    predicted = y+(ny-y)*(now-t)/(nt-t)
                    method = 'bounded_reappearance_interpolation'
                elif velocity is not None:
                    predicted = y+velocity*(now-t)
                    method = 'local_approach_extrapolation'
                else:
                    predicted = y;method = 'last_observed_position_only'
                base = {'note':ni,'lane':note['lane'],'visible_start_seconds':now,'visible_end_seconds':now,
                        'source_pts_seconds':[frame['source_pts_seconds'],frame['source_pts_seconds']],
                        'last_observed_seconds':t,'last_observed_y':y,'expected_y':float(predicted),
                        'position_method':method,'observed_points':len(points)}
                if predicted <= receptor+.85*spacing:
                    if last:exits.append({**base,'reason':'head_enters_receptor_detection_boundary'})
                    break
                # A separately registered source trajectory can show the head
                # is still detected. This does not establish chart ownership.
                same = [n for n in frame.get('notes',[]) if n['lane']==note['lane']
                        and abs(n['y']*height-predicted)<=2]
                if len(same)==1:
                    if last:
                        exits.append({**base,'reason':'native_detection_continues_under_another_track'})
                        break
                    continue
                hud = overlapping_occluders(layout,note['lane'],predicted,width,height,spacing)
                loss = processing.get(ni,{})
                if hud:
                    pending.append(('known_occlusions',{**base,'reason':'documented_hud_occlusion','regions':hud}))
                elif (last and loss.get('status')=='visibility_modified'
                      and loss.get('visibility_loss',{}).get('range')
                      and now >= loss['visibility_loss']['range'][0]):
                    pending.append(('known_occlusions',{**base,'reason':'chart_visibility_modifier',
                                                       'gimmick_candidates':loss['gimmick_candidates']}))
                else:
                    reason = 'unexplained_head_disappearance' if last else 'unexplained_head_detection_gap'
                    pending.append(('warnings',{**base,'reason':reason,'check':'note_visibility'}))
                # Without a motion estimate, only the next real source frame is
                # testable; do not pretend to know its later hidden path.
                if last and method=='last_observed_position_only':
                    break
        # Consecutive absent frames with the same explanation form one review
        # interval. Even a single missing source frame remains a warning.
        groups=[]
        for destination,record in pending:
            signature=(destination,record['reason'],tuple(record.get('regions',[])),record['last_observed_seconds'])
            if groups and groups[-1][0]==signature and record['visible_start_seconds']-groups[-1][1]['visible_end_seconds'] <= .05:
                group=groups[-1][1];group['visible_end_seconds']=record['visible_end_seconds']
                group['source_pts_seconds'][1]=record['source_pts_seconds'][1];group['missing_frames']+=1
            else:
                groups.append((signature,{**record,'missing_frames':1}))
        for (destination,*_),record in groups:
            (warnings if destination=='warnings' else occlusions).append(record)
    from piu_timeline.play.motion_warnings import motion_warnings
    from piu_timeline.play.scroll_pauses import classify_warnings
    native_motion = motion_warnings(data,frames)
    remaining,expected_motion=classify_warnings(data,native_motion)
    warnings.extend(remaining)
    return {'format':FORMAT,'native_motion_warnings':native_motion,'known_motion_effects':expected_motion,'warnings':warnings,'known_occlusions':occlusions,'accounted_exits':exits,
            'regions':note_occluders(layout),'counts':dict(Counter(r['reason'] for r in warnings))}
