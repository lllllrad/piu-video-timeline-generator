"""Observe continued passage, separately from disappearance and input success."""


def evidence(samples,receptor,spacing,minimum_coverage):
    def positive(sample):
        if sample['state']=='present':return True
        coverage=sample.get('template_coverage',{})
        return (sample.get('unknown_reason')=='partial_head_present'and sample.get('score',0)>=.65
                and all(coverage.get(k,0)>=minimum_coverage for k in('area_fraction','foreground_fraction')))
    beyond=[s for s in samples if positive(s)and s['y']<receptor-.65*spacing]
    pairs=[(a,b)for a,b in zip(beyond,beyond[1:])if 0<b['time']-a['time']<=.05 and b['y']<a['y']]
    if not pairs:return None
    a,b=pairs[-1]
    return {'range':[a['time'],b['time']],'source_pts_seconds':[a['pts'],b['pts']],
            'y_pixels':[a['y'],b['y']],
            'partial_presence':[a['state']!='present',b['state']!='present']}


def after_refresh(event,upper,guard=0):
    """Flag a measured ordering conflict; do not manufacture a replacement input."""
    from piu_timeline.derived import call
    return call('evidence.afterRefresh',event,upper,guard)
