"""Join positive image regions through measured motion, including clipped holds."""
from collections import defaultdict
from piu_timeline.play.observations.coordinates import detection_points,fit_trajectory

from piu_timeline import derived
from piu_timeline.play.skins.coverage import image_spans


def measured_steps(data,native):
    layout=data['layout'];spacing=(layout['lanes'][1]['x']-layout['lanes'][0]['x'])*data['analysis_width']
    notes=[{'motion_trajectory':fit_trajectory(n),**({'duplicate_of':n['duplicate_of']}if 'duplicate_of'in n else{})}for n in data['notes']]
    timeline=[{'time':f['playback_seconds'],'source_pts':f['source_pts_seconds']}for f in native]
    return {s['time']:s for s in derived.call('holdMotion.steps',notes,
            data.get('scroll_motion',{}).get('samples',[]),timeline,spacing)}


def temporal_pairs(data,native,roles,references,cap_references,*,length_checks=None):
    """No interpolated image or assumed constant velocity supplies an edge."""
    if length_checks is None:
        from piu_timeline.play.skins.extents import LengthChecks
        length_checks=LengthChecks(data)
    known=defaultdict(list)
    for i,note in enumerate(data['notes']):
        role=('head'if roles[i]=={'hold_start'}else'tail'if roles[i]=={'hold_end'}
              else'barrier'if 'tap'in roles[i]else None)
        if role:
            for time,y in detection_points(note):
                known[time,note['lane']].append((i,y,role))
    steps=measured_steps(data,native)
    spacing=(data['layout']['lanes'][1]['x']-data['layout']['lanes'][0]['x'])*data['analysis_width']
    height=data['analysis_height'];nodes=[];parents=[];previous=[];before=None
    def root(i):
        while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
        return i
    for frame in native:
        time=frame['playback_seconds'];lanes=defaultdict(list)
        for image in frame.get('skin_observations',[]):
            if image.get('cap_subfeature'):continue
            lane=image['lane']
            owned=any(role!='barrier'and abs(y-image['y']*height)<1e-5 for i,y,role in known[time,lane])
            if image['role']in('hold_start','hold_end','hold_body'):rows=image_spans(image,references)
            elif image['role']=='unknown'and image.get('classification_status')=='cap_only'and owned:
                rows=image_spans(image,cap_references,cap_only=True)
            else:continue
            lanes[lane].extend((a,b,image['role']=='hold_body')for a,b in rows)
        current=[]
        for lane,spans in lanes.items():
            merged=[]
            for a,b,body in sorted(spans):
                if merged and a<=merged[-1][1]+1:
                    merged[-1][1]=max(merged[-1][1],b);merged[-1][2]|=body
                else:merged.append([a,b,body])
            for a,b,body in merged:
                tags=[(i,role)for i,y,role in known[time,lane]if a<=y<=b]
                index=len(nodes);parents.append(index)
                nodes.append({'time':time,'source_pts':frame['source_pts_seconds'],'lane':lane,
                              'covered_bounds_pixels':[a,b],'body_template_support':body,'tags':tags,'image_node':index,'connected_to':[]})
                current.append(index)
        measured=steps.get(time)if before is not None else None
        if measured is not None:
            delta=measured['displacement_pixels']
            for b in current:
                last=nodes[b];lo,hi=last['covered_bounds_pixels']
                for a in previous:
                    first=nodes[a];x,y=first['covered_bounds_pixels']
                    if first['lane']==last['lane']and max(x-delta,lo)<=min(y-delta,hi)+1:
                        parents[root(b)]=root(a);last['connected_to'].append(a)
                        last['motion_link']={k:v for k,v in measured.items()if k!='time'}
        previous=current;before=time
    components=defaultdict(list)
    for i,node in enumerate(nodes):components[root(i)].append(node)
    pairs=defaultdict(list);refuted=defaultdict(list)
    for component in components.values():
        tags={tag for node in component for tag in node['tags']}
        heads={i for i,role in tags if role=='head'};tails={i for i,role in tags if role=='tail'}
        if len(heads)!=1 or len(tails)!=1:continue
        head,tail=next(iter(heads)),next(iter(tails));first,last=data['notes'][head],data['notes'][tail]
        times={n['time']for n in component}
        if len(times)<4 or max(times)-min(times)<.065:continue
        body_times={n['time']for n in component if n['body_template_support']}
        if len(body_times)<4 or max(body_times)-min(body_times)<.065:continue
        observed=[y for t,y in detection_points(first)if t in times]
        if len(observed)<2 or max(observed)-min(observed)<.5*spacing:continue
        before,after=dict(detection_points(first)),dict(detection_points(last))
        gaps=[after[t]-before[t]for t in before.keys()&after.keys()]
        if gaps and (min(gaps)<=0 or max(gaps)-min(gaps)>2 and length_checks.check(head,tail)['status']!='consistent'):continue
        by_time=defaultdict(list)
        for node in component:by_time[node['time']].append(node)
        # A conflicting note between positive islands refutes the interval too.
        conflicts=[]
        for time,group in by_time.items():
            lo=before.get(time,min(n['covered_bounds_pixels'][0]for n in group))
            hi=after.get(time,max(n['covered_bounds_pixels'][1]for n in group))
            for i,y,role in known[time,first['lane']]:
                if role=='barrier'and lo<y<hi:
                    conflicts.append({'time':time,'source_pts':group[0]['source_pts'],
                                      'source_note':i,'observed_roles':sorted(roles[i]),'trace':'frames.jsonl'})
        if conflicts:refuted[head,tail].extend(conflicts);continue
        for node in component:
            proof={k:v for k,v in node.items()if k!='tags'}
            proof['trace']='frames.jsonl'
            if any(i==head for i,role in node['tags']):proof['head_y']=before[node['time']]
            if any(i==tail for i,role in node['tags']):proof['tail_y']=after[node['time']]
            pairs[head,tail].append(proof)
    return {'pairs':[{'head':head,'tail':tail,'proof':sorted(proof,key=lambda p:(p['time'],p['image_node'])),
                      'missing':coverage_losses(data,native,proof,steps)}
                     for (head,tail),proof in pairs.items()if (head,tail)not in refuted],
            'refuted':[{'head':head,'tail':tail,'evidence':evidence}for (head,tail),evidence in refuted.items()]}


def coverage_losses(data,native,proof,steps):
    """Lost previously positive rows are warnings, never filled image evidence."""
    from piu_timeline.play.screen_regions import note_occluders
    by_time=defaultdict(list)
    for node in proof:by_time[node['time']].append(node['covered_bounds_pixels'])
    width,height=data['analysis_width'],data['analysis_height'];layout=data['layout']
    spacing=(layout['lanes'][1]['x']-layout['lanes'][0]['x'])*width
    top=layout['receptor_y']*height+.85*spacing;bottom=layout.get('note_y_max',.95)*height-.55*spacing
    lane=proof[0]['lane']if 'lane'in proof[0]else None
    if lane is None:raise ValueError('Temporal coverage requires a source lane')
    center=layout['lanes'][lane]['x']*width
    hud=[(r['rect'][1]*height,(r['rect'][1]+r['rect'][3])*height)for r in note_occluders(layout)
         if r['rect'][0]*width<center+.25*spacing and (r['rect'][0]+r['rect'][2])*width>center-.25*spacing]
    previous=None;losses=[];start,end_time=min(by_time),max(by_time)
    for frame in native:
        time=frame['playback_seconds']
        if not start<=time<=end_time:continue
        if previous is not None and by_time[previous['playback_seconds']]:
            measured=steps.get(time)
            gaps=[]
            if measured is not None:
                delta,basis=measured['displacement_pixels'],measured['method'];available=sorted([*by_time[time],*hud],key=lambda interval:interval[0])
                for lo,hi in by_time[previous['playback_seconds']]:
                    cursor,end=max(top,lo-delta),min(bottom,hi-delta)
                    for a,b in available:
                        if b<cursor:continue
                        if a>end:break
                        if a>cursor+1:gaps.append([cursor,min(a,end)])
                        cursor=max(cursor,b)
                        if cursor>=end:break
                    if end>cursor+1:gaps.append([cursor,end])
                if gaps:losses.append({'time':time,'source_pts':frame['source_pts_seconds'],
                                       'expected_from_source_pts':previous['source_pts_seconds'],
                                       'missing_intervals_pixels':gaps,'displacement_pixels':delta,'motion_basis':basis})
            else:losses.append({'time':time,'source_pts':frame['source_pts_seconds'],
                                'failure_detail':'temporal_image_displacement_unverified'})
        previous=frame
    return losses
