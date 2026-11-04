"""Separate observed hold rows from gaps explained by named foreground HUD."""
from piu_timeline.play.screen_regions import note_occluders

SUPPORT={'minimum_frames':4,'minimum_travel_spacing':.5,'maximum_capture_gap_seconds':.05,
         'method':'captured_endpoint_pairs_with_measured_travel'}


def uncovered(lo,hi,spans):
    cursor=lo;gaps=[]
    for a,b in sorted(spans):
        if b<=cursor:continue
        if a>=hi:break
        if a>cursor+1:gaps.append([cursor,min(a,hi)])
        cursor=max(cursor,b)
        if cursor>=hi:break
    if hi>cursor+1:gaps.append([cursor,hi])
    return gaps


def lane_regions(data,lane):
    width,height=data['analysis_width'],data['analysis_height'];center=data['layout']['lanes'][lane]['x']*width
    return [{'region':r['id'],'bounds_pixels':[r['rect'][1]*height,(r['rect'][1]+r['rect'][3])*height]}
            for r in note_occluders(data['layout'])
            if r['rect'][0]*width<=center<(r['rect'][0]+r['rect'][2])*width and r['rect'][2]>0 and r['rect'][3]>0]


def coverage(lo,hi,spans,regions):
    """HUD explains only actual holes, never positive image support or endpoints."""
    observed=[]
    for a,b in sorted((max(lo,a),min(hi,b))for a,b in spans if max(lo,a)<min(hi,b)):
        if observed and a<=observed[-1][1]:observed[-1][1]=max(observed[-1][1],b)
        else:observed.append([a,b])
    gaps=uncovered(lo,hi,observed)
    masks=[r['bounds_pixels']for r in regions]
    if any(a<=lo or b>=hi or uncovered(a,b,masks)for a,b in gaps):return None
    hidden=[{'region':r['region'],'bounds_pixels':[max(a,x),min(b,y)]}
            for a,b in gaps for r in regions for x,y in [r['bounds_pixels']]if max(a,x)<min(b,y)]
    return {'observed_intervals_pixels':observed,
            **({'occluded_intervals':hidden}if hidden else{})}


def supported(proof,spacing):
    """Repeated rendered positions retain PTS; measured travel supplies motion."""
    runs=[];run=[]
    for point in proof:
        if run and any(not 0<point[key]-run[-1][key]<=SUPPORT['maximum_capture_gap_seconds']+1e-6
                       for key in ('time','source_pts')):
            runs.append(run);run=[]
        run.append(point)
    runs.append(run)
    return any(len(r)>=SUPPORT['minimum_frames'] and all(
        r[0][edge]-r[-1][edge]>=SUPPORT['minimum_travel_spacing']*spacing
        for edge in ('head_y','tail_y'))for r in runs if r)
