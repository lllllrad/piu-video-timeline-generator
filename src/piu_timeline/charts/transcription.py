"""Infer bounded UCS rows per measure without a nearest-cell fallback."""
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from fractions import Fraction
import math

from piu_timeline.charts.ucs import Document, Section, NATURAL_SPLITS


FORMAT={'schema':1,'revision':2,'method':'per_measure_unique_intervals',
        'natural_splits':list(NATURAL_SPLITS),'maximum_row_residual_seconds':.012}
EPSILON=1e-8


def measures(document):
    """Retain exact timing boundaries, delays and fractional measure phase."""
    settings={};time=Fraction(0);phase=Fraction(0);meter=None;measure=0;result=[]
    for si,section in enumerate(document.sections):
        settings.update(section.directives)
        beat=int(settings['Beat']);split=int(settings['Split'])
        if meter is not None and meter!=beat:
            if phase:measure+=1
            phase=Fraction(0)
        meter=beat
        time+=Fraction(dict(section.directives).get('Delay','0'))/1000
        remaining=Fraction(len(section.rows),split);duration=60/Fraction(settings['BPM']);first=True
        while remaining:
            length=min(remaining,beat-phase)
            result.append({'source_section':si,'measure':measure,'phase':phase,'beats':length,
                           'start':time,'end':time+length*duration,'beat_duration':duration,
                           'directives':section.directives if first else []})
            first=False;time+=length*duration;remaining-=length;phase+=length
            if phase==beat:phase=Fraction(0);measure+=1
    return result


def choices(span, split, lower, upper, following):
    step=float(span['beat_duration']/split);start=float(span['start'])
    count=int(span['beats']*split)
    lo=max(0,math.ceil((lower-start-EPSILON)/step))
    hi=min(count-1,math.floor((upper-start+EPSILON)/step))
    rows=[(start+i*step,i) for i in range(lo,hi+1)]
    if following is not None and lower-EPSILON<=following<=upper+EPSILON:
        rows.append((following,count))
    return rows


def transcribe(document, endpoints):
    """Maximize uniquely supported endpoints, breaking ties toward coarse grids."""
    spans=measures(document);starts=[float(s['start']) for s in spans];groups=defaultdict(list)
    for key,interval in endpoints.items():
        center=sum(interval)/2
        groups[max(0,min(len(spans)-1,bisect_right(starts,center)-1))].append((key,interval))
    sections=[];fits=[];assigned={};failures={};flat=0
    for index,span in enumerate(spans):
        following=starts[index+1] if index+1<len(spans) else None
        factor=math.lcm(span['phase'].denominator,span['beats'].denominator)
        splits=sorted({math.lcm(factor,s) for s in NATURAL_SPLITS if math.lcm(factor,s)<=1536})
        trials=[];best=None
        for split in splits:
            count=int(span['beats']*split);step=span['beat_duration']/split
            if following is not None and float(span['start']+(count-1)*step)>=following-EPSILON:
                continue
            matches={};rejected={}
            for key,(lower,upper) in groups[index]:
                rows=choices(span,split,lower,upper,following)
                if len(rows)==1 and abs(sum((lower,upper))/2-rows[0][0])<=FORMAT['maximum_row_residual_seconds']+EPSILON:
                    matches[key]=rows[0]
                else:
                    rejected[key]='Ambiguous rows at selected measure Split' if len(rows)>1 else 'No bounded row at selected measure Split'
            trials.append({'split':split,'unique_endpoints':len(matches)})
            score=(len(matches),-split)
            if best is None or score>best[0]:best=(score,split,matches,rejected)
        if best is None:
            raise ValueError('Official timing boundaries cannot form an increasing measure grid')
        _,split,matches,rejected=best
        directives=[(key,value) for key,value in span['directives'] if key!='Split']+[('Split',str(split))]
        sections.append(Section(directives,['.'*document.lanes]*int(span['beats']*split)))
        for key,(time,row) in matches.items():assigned[key]=(time,flat+row,index)
        failures.update({key:f'{reason}={split}' for key,reason in rejected.items()})
        fits.append({'measure':span['measure'],'source_section':span['source_section'],
                     'start_seconds':float(span['start']),'end_seconds':float(span['end']),
                     'beat_offset':str(span['phase']),'split':split,
                     'row_duration_seconds':float(span['beat_duration']/split),
                     'status':'empty' if not groups[index] else 'partial' if rejected and matches else 'failed' if rejected else 'restored',
                     'endpoints':len(groups[index]),'unique_endpoints':len(matches),'tested_splits':trials})
        flat+=len(sections[-1].rows)
    result=Document(document.header,sections);grid=list(result.grid());times=[float(t)for _,_,t in grid]
    if any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('Overlapping UCS timing sections need manual placement')
    accepted={}
    for key,(time,row,index) in assigned.items():
        lower,upper=endpoints[key];lo=bisect_left(times,lower-EPSILON);hi=bisect_right(times,upper+EPSILON)
        if hi-lo!=1 or lo!=row or abs(sum((lower,upper))/2-time)>FORMAT['maximum_row_residual_seconds']+EPSILON:
            failures[key]='Chart interval is ambiguous or outside tolerance across measure grids'
            fits[index]['post_grid_unresolved_endpoints']=fits[index].get('post_grid_unresolved_endpoints',0)+1
            fits[index]['status']='partial'
        else:
            accepted[key]=row
    counts=Counter(assigned[key][2]for key in accepted)
    for index,fit in enumerate(fits):
        fit['unique_endpoints']=counts[index]
        fit['status']=('empty' if not fit['endpoints'] else 'restored' if counts[index]==fit['endpoints']
                       else 'partial' if counts[index] else 'failed')
    return result,grid,accepted,failures,{'format':FORMAT,'measures':fits}
