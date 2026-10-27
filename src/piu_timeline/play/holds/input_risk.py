"""Bound possible hold ticks from geometry and native receptor observations."""
import math


def complete_image_hold(hold):
    return (hold.get('head_note')is not None and hold.get('tail_note')is not None
            and hold.get('start_censored')is False and hold.get('end_censored')is False
            and bool(hold.get('end_range'))and hold.get('body_frames',0)>=4
            and hold.get('body_evidence')in('skin_start_body_end_images','skin_temporal_image_regions'))

def native_body_risk_available(data):
    """A complete image detector supplies receptor-local risk, not warning spans."""
    from piu_timeline.play.skins.held import FORMAT
    skin=data.get('skin_detector',{})
    return (skin.get('contract',{}).get('held_body')==FORMAT
            and skin.get('missing_template_roles')==[] and 'unsupported_intervals'in data)


def hold_overlap(data, lo, hi, guard, accounted_native_intervals=()):
    analysis = data.get('hold_analysis', {})
    for hold in analysis.get('holds', []):
        end = hold['end_range'][1] if hold.get('end_range') else hold['last_body_seconds']+.25
        if hold['start_range'][0]-guard <= hi and end+guard >= lo:
            return True
    if any(interval['start_seconds']-guard<=hi and interval['end_seconds']+guard>=lo
           for interval in data.get('unsupported_intervals',[])
           if (interval['start_seconds'],interval['end_seconds'])not in accounted_native_intervals):return True
    for track in analysis.get('unresolved_tracks', []):
        if (native_body_risk_available(data)
                and track.get('failure_detail')=='known_hold_image_connection_not_observed_in_clear_frames'
                and any(h.get('id')==track.get('hold')and h.get('id')is not None
                        and h.get('head_note')==track.get('note')and h.get('head_note')is not None
                        and h.get('tail_note')==track.get('tail_note')and h.get('tail_note')is not None
                        and complete_image_hold(h)
                        for h in analysis.get('holds',[]))):continue
        # These are unrelated image tiles grouped for review, not a connected
        # body persisting from the first tile to the last. Their actual receptor
        # risk is measured independently in the native frame observations.
        if (native_body_risk_available(data)
                and track.get('failure_detail')=='skin_body_images_without_complete_endpoint_ownership'
                and track.get('image_evidence')
                and all(p.get('role')=='hold_body'for p in track['image_evidence'])):continue
        if track['visible_start_seconds']-guard<=hi and track['visible_end_seconds']+.25+guard>=lo:return True
    return False


def cap_extent_spacing(data):
    """Bound the cap footprint from the acquired bank, including larger skins."""
    from piu_timeline.play.skins.bank import load_bank
    skin=data.get('skin_detector',{})
    try:
        bank=load_bank(skin['bank_path'])
        if bank['contract']!=skin['contract']['bank']:return None
        extents=[abs(y-t['anchor_pixels'][1])/bank['spacing_pixels']for t in bank['templates']
                 if t['role']!='hold_body'for r in t['regions']if r['name']=='cap'for y in(r['box'][1],r['box'][3])]
        return max(1.,*extents)if extents else None
    except (OSError,ValueError,KeyError):return None


def cap_guard(data,hold,extent_spacing=1.):
    if not complete_image_hold(hold):return None
    lanes=data.get('layout',{}).get('lanes',[])
    if len(lanes)<2:return None
    spacing=(lanes[1]['x']-lanes[0]['x'])*data['analysis_width'];speeds=[]
    for index in(hold['head_note'],hold['tail_note']):
        note=data['notes'][index]
        if note['status']!='estimated'or any((note.get(k)or{}).get('status')=='failed'
                                           for k in('timing_reconstruction','beat_reconstruction')):return None
        measured=[abs(v)for v in(note.get('velocity_pixels_per_second'),(note.get('motion_clock')or{}).get('velocity'))
                  if type(v)in(int,float)and math.isfinite(v)and abs(v)>0]
        if not measured:return None
        speeds.extend(measured)
    return max(2*(data.get('median_frame_interval_seconds')or .017),extent_spacing*spacing/min(speeds))


def pre_hold_accounting(data,lo,hi,extent_spacing=1.):
    """Account for every nearby risk flag before reconsidering an early word."""
    if not native_body_risk_available(data):return None
    correction=data.get('display_delay_correction_ms',0)/1000
    if not math.isfinite(correction):return None
    risk_lo,risk_hi=lo-correction,hi-correction
    guards=[]
    for hold in data.get('hold_analysis',{}).get('holds',[]):
        guard=cap_guard(data,hold,extent_spacing)
        if guard is None:return None
        if hold['start_range'][0]-guard<=risk_hi and hold['end_range'][1]+guard>=risk_lo:return None
        guards.append((hold,guard))
    relevant=[r for r in data['unsupported_intervals']if r['start_seconds']-.1<=hi and r['end_seconds']+.1>=lo]
    if not relevant:return None
    records=[];used=set();maximum=0;accounted=[]
    for interval in relevant:
        owners=[(h,g)for h,g in guards if risk_hi<h['start_range'][0]-g
                and h['start_range'][0]-g<=interval['start_seconds']
                and interval['end_seconds']<=h['end_range'][1]+g]
        from piu_timeline.play.holds.risk_ownership import account_interval
        geometric=account_interval(data,interval,guards,risk_hi)
        if geometric is not None:
            owners=[(h,g)for h,g in guards if h['id']in geometric['holds']]
            accounted.append((interval['start_seconds'],interval['end_seconds']))
        if not owners:return None
        used.update(h['id']for h,_ in owners);maximum=max(maximum,*(g for _,g in owners))
        records.append({**interval,'accounted_holds':[h['id']for h,_ in owners],
                        **({'native_image_ownership':geometric}if geometric else {})})
    if hold_overlap(data,risk_lo,risk_hi,maximum,accounted):return None
    return {'method':'before_accounted_native_hold_regions','holds':sorted(used),
            'maximum_cap_guard_seconds':maximum,'native_risk_intervals':records,
            'risk_time_range':[risk_lo,risk_hi],'display_delay_correction_ms':correction*1000,
            'cap_extent_spacing':extent_spacing}

