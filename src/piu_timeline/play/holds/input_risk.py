"""Bound possible hold ticks from geometry and native receptor observations."""

def native_body_risk_available(data):
    """A complete image detector supplies receptor-local risk, not warning spans."""
    from piu_timeline.play.skins.held import FORMAT
    skin=data.get('skin_detector',{})
    return (skin.get('contract',{}).get('held_body')==FORMAT
            and skin.get('missing_template_roles')==[] and 'unsupported_intervals'in data)


def hold_overlap(data, lo, hi, guard):
    analysis = data.get('hold_analysis', {})
    for hold in analysis.get('holds', []):
        end = hold['end_range'][1] if hold.get('end_range') else hold['last_body_seconds']+.25
        if hold['start_range'][0]-guard <= hi and end+guard >= lo:
            return True
    if any(interval['start_seconds']-guard<=hi and interval['end_seconds']+guard>=lo
           for interval in data.get('unsupported_intervals',[])):return True
    for track in analysis.get('unresolved_tracks', []):
        if (native_body_risk_available(data)
                and track.get('failure_detail')=='known_hold_image_connection_not_observed_in_clear_frames'
                and any(h.get('id')==track.get('hold')and h.get('id')is not None
                        and h.get('head_note')==track.get('note')and h.get('head_note')is not None
                        and h.get('tail_note')==track.get('tail_note')and h.get('tail_note')is not None
                        and h.get('start_censored')is False and h.get('end_censored')is False
                        and h.get('end_range')and h.get('body_frames',0)>=4
                        and h.get('body_evidence')in('skin_start_body_end_images','skin_temporal_image_regions')
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

