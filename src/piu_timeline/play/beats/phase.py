"""Choose a common bounded song phase before selecting local subdivisions."""
import math

from piu_timeline.play.beats.timing import fit_grid
from piu_timeline.play.beats.coordinates import FORMAT as COORDINATE_FORMAT


def signature(fits):
    return tuple((f['status'],f['split'],tuple(f['rows']))if f['status']in('restored','partial')else('failed',)for f in fits)


def fit_groups(groups, phase, consistent_notes=None):
    """Freeze unique neighbors before using them across a measure boundary."""
    def run(group, blocks):
        if group.get('invalid'):return {'status':'failed','reason':group['invalid']}
        return fit_grid(group['targets'],group['errors'],group['bpm'],group['origin']+phase,
                        native_chords=group.get('native_chords',()),native_coordinates=blocks)
    initial=[run(g,g.get('native_coordinates',()))for g in groups]
    qualified=set(consistent_notes(initial))if consistent_notes else None
    unique={}
    for group,fit in zip(groups,initial,strict=True):
        if fit['status']not in('restored','partial'):continue
        for note,target in zip(group.get('notes',()),fit['targets']):
            if target is not None and(qualified is None or note in qualified):unique[note]=(target,group['bpm'])
    results=[]
    for group in groups:
        blocks=[]
        for block in group.get('native_coordinates',()):
            blocks.append(block)
            references=[{'note':i,'target_seconds':unique[i][0],**head}
                        for i,head in block.get('neighbor_heads',{}).items()
                        if i in unique and unique[i][1]==group['bpm']]
            if references:
                blocks.append({**block,'references':references})
                radius=COORDINATE_FORMAT['reference_radius_seconds']
                blocks.append({**block,'references':references,'neighbors_only':True,
                               'reference_window':[min(group['targets'])-radius,max(group['targets'])+radius]})
        results.append(run(group,blocks))
    # A reference which changed or failed during the second pass cannot prove
    # another group. Propagate invalidation without promoting recovered rows.
    for _ in groups:
        final={i:t for g,f in zip(groups,results,strict=True)if f['status']in('restored','partial')
               for i,t in zip(g.get('notes',()),f['targets'])if t is not None}
        invalid=[]
        for j,(group,result)in enumerate(zip(groups,results,strict=True)):
            local=set(group.get('notes',()))
            refs=[r for p in result.get('native_coordinate_constraints',())for r in p['model']['references']if r['note']not in local]
            if any(r['note']not in final or abs(final[r['note']]-r['target_seconds'])>1e-8 for r in refs):invalid.append(j)
        if not invalid:break
        for j in invalid:results[j]={'status':'failed','reason':'unstable_neighbor_reference_rows'}
    return results


def fit_phase(groups, uncertainty, consistent_notes=None):
    # A phase-search grid is an inference resolution, never a replacement for
    # native frame times. Its half-step is retained in the phase range.
    steps=max(1,math.ceil(2*uncertainty/.001))
    phases=[0.] if uncertainty==0 else [-uncertainty+2*uncertainty*i/steps for i in range(steps+1)]
    best=None;winners=[];trials=[]
    for phase in phases:
        fits=fit_groups(groups,phase,consistent_notes)
        count=sum(sum(t is not None for t in f['targets'])for f in fits if f['status']in('restored','partial'))
        complexity=sum(f['split']*sum(t is not None for t in f['targets'])for f in fits if f['status']in('restored','partial'))
        supported=tuple(sorted(consistent_notes(fits)))if consistent_notes else None
        score=(len(supported)if supported is not None else count,count,-complexity)
        assignment=signature(fits)
        trials.append({'phase_seconds':phase,'restored_targets':count,
                       'consistent_targets':score[0],'subdivision_complexity':complexity})
        if best is None or score>best:best=score;winners=[(phase,fits,assignment,supported)]
        elif score==best:winners.append((phase,fits,assignment,supported))
    if not best[0] or len({(w[2],w[3]) for w in winners})!=1:
        return {'status':'failed','reason':'ambiguous_or_unsupported_song_phase','fits':[
            {'status':'failed','reason':g.get('invalid','ambiguous_or_unsupported_song_phase')} for g in groups],
                'phase_trials':trials}
    lo,hi=winners[0][0],winners[-1][0];phase=(lo+hi)/2
    fits=fit_groups(groups,phase,consistent_notes)
    unstable=('unstable_song_phase_assignment'if signature(fits)!=winners[0][2]else
              'unstable_spatial_song_phase'if consistent_notes and tuple(sorted(consistent_notes(fits)))!=winners[0][3]else None)
    if unstable:
        return {'status':'failed','reason':unstable,'phase_trials':trials,
                'fits':[{'status':'failed','reason':unstable}for _ in groups]}
    half_step=uncertainty/steps if uncertainty else 0
    return {'status':'restored','phase':phase,'phase_range':[max(-uncertainty,lo-half_step),min(uncertainty,hi+half_step)],
            'resolution_seconds':2*half_step,'fits':fits,'phase_trials':trials,
            'consistent_notes':list(winners[0][3])if winners[0][3]is not None else None}
