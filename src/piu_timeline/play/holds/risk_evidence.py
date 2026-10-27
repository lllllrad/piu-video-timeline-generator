"""Own native risk causes by exact image components, independently of popups."""
from collections import Counter,defaultdict
import math

from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.held import BodyAtReceptor,CAUSE_FORMAT
from piu_timeline.play.skins.anchors import FORMAT as ANCHOR_FORMAT
from piu_timeline.play.holds.input_risk import complete_image_hold

FORMAT={'schema':1,'revision':2,'causes':CAUSE_FORMAT,'ownership':'same_native_temporal_image_component',
        'native_cap_registration':ANCHOR_FORMAT}


def head_position(data,bank,hold,point,frame):
    if data.get('head_registration',{}).get('format',{}).get('native_cap_registration')!=ANCHOR_FORMAT:return None
    record=next((r for r in data['head_registration']['notes']if r['note']==hold['head_note']),None)
    if record is None:return None
    for sample in record['observations']:
        if sample['time']!=frame['playback_seconds']or sample['source_pts_seconds']!=frame['source_pts_seconds']:continue
        if sample.get('native_cap_registration_status')=='conflicting':continue
        if sample.get('native_cap_reference_template')not in bank['anchor_registrations']:continue
        uncertainty,scale=sample.get('native_cap_coordinate_uncertainty_pixels'),sample.get('native_cap_reference_scale_y')
        if any(type(v)not in(int,float)or not math.isfinite(v)or v<=0 for v in(uncertainty,scale)):continue
        if abs(uncertainty-max(ANCHOR_FORMAT['coordinate_uncertainty_pixels'],ANCHOR_FORMAT['coordinate_uncertainty_pixels']*scale))>1e-9:continue
        y=sample['native_y_pixels'];lo,hi=point['covered_bounds_pixels']
        if not math.isfinite(y):continue
        if not lo<=y<=hi or 'head_y'in point and abs(point['head_y']-y)>1e-5:continue
        link=point.get('motion_link',{})
        if link.get('method')!='registered_frame_displacement':continue
        displacement=link.get('displacement_pixels',0)
        if not math.isfinite(displacement)or displacement<=0:continue
        if link.get('source_pts_range',[None,None])[-1]!=frame['source_pts_seconds']:continue
        return {'y_pixels':y,'coordinate_uncertainty_pixels':uncertainty,
                'reference_template':sample['native_cap_reference_template'],'motion_link':link}
    return None


def derive(data,native,bank):
    if bank['contract']!=data['skin_detector']['contract']['bank']:raise ValueError('Risk bank differs from acquired images')
    detector=SkinDetector(bank,data['layout'],data['analysis_width'],data['analysis_height'])
    held=BodyAtReceptor(detector)
    extent=max(held.spacing,*[abs(y-t['anchor'][1])for t in detector.templates if t['role']!='hold_body'
                              for r in t['regions']if r['name']=='cap'for y in(r['box'][1],r['box'][3])])
    components=defaultdict(list)
    for hold in data.get('hold_analysis',{}).get('holds',[]):
        if not complete_image_hold(hold):continue
        for point in hold.get('image_connection_evidence',[]):
            if point.get('body_template_support')and 'covered_bounds_pixels'in point and point.get('trace')=='frames.jsonl':
                components[point['time'],hold['lane']].append((hold,point))
    frames=[];intervals=[];previous=None
    for frame in native:
        time,pts=frame['playback_seconds'],frame['source_pts_seconds']
        if not all(math.isfinite(v)for v in(time,pts))or previous is not None and(time<=previous[0]or pts<=previous[1]):
            raise ValueError('Native risk frames need increasing original PTS')
        previous=time,pts;causes=held.explain(frame['skin_observations'])
        if bool(causes)!=frame['possible_hold_or_dense_stack']:raise ValueError('Reconstructed risk differs from native flag')
        if not causes:continue
        if intervals and time-intervals[-1][1]<.1:intervals[-1][1]=time
        else:intervals.append([time,time])
        records=[]
        for cause in causes:
            a,b=cause['vertical_range_pixels'];owners=defaultdict(list)
            for hold,point in components[time,cause['lane']]:
                lo,hi=point['covered_bounds_pixels']
                if point['source_pts']==pts and lo<=a<=b<=hi:owners[hold['id']].append((hold,point))
            record={**cause,'state':'unresolved','candidate_holds':sorted(owners)}
            if len(owners)==1:
                identifier=next(iter(owners));record['owner_hold']=identifier
                for hold,point in owners[identifier]:
                    head=head_position(data,bank,hold,point,frame)
                    if head is None:continue
                    top=head['y_pixels']-extent-head['coordinate_uncertainty_pixels']
                    if top<=held.receptor or a<=held.receptor:continue
                    record.update(state='approaching',ownership={'method':FORMAT['ownership'],'image_node':point['image_node'],
                        'covered_bounds_pixels':point['covered_bounds_pixels'],'head':head,'minimum_head_top_pixels':top})
                    break
            records.append(record)
        frames.append({'playback_seconds':time,'source_pts_seconds':pts,'causes':records})
    expected=[[r['start_seconds'],r['end_seconds']]for r in data['unsupported_intervals']]
    if intervals!=expected:raise ValueError('Native risk frame groups differ from tracked intervals')
    return {'status':'available','frame_count':len(native),'frames':frames,'verified_native_flags':True,
            'geometry':{'lane_spacing_pixels':held.spacing,'receptor_y_pixels':held.receptor,'cap_extent_pixels':extent},
            'counts':dict(Counter(c['state']for f in frames for c in f['causes'])),'warnings':[]}
