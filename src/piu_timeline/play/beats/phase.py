"""Choose a common bounded song phase before selecting local subdivisions."""
import math

from piu_timeline.play.beats.timing import fit_grid


def fit_phase(groups, uncertainty, consistent_notes=None):
    # A phase-search grid is an inference resolution, never a replacement for
    # native frame times. Its half-step is retained in the phase range.
    steps=max(1,math.ceil(2*uncertainty/.001))
    phases=[0.] if uncertainty==0 else [-uncertainty+2*uncertainty*i/steps for i in range(steps+1)]
    best=None;winners=[];trials=[]
    for phase in phases:
        fits=[]
        for group in groups:
            if group.get('invalid'):
                fits.append({'status':'failed','reason':group['invalid']});continue
            fits.append(fit_grid(group['targets'],group['errors'],group['bpm'],group['origin']+phase,
                                 native_chords=group.get('native_chords',())))
        count=sum(len(g['targets']) for g,f in zip(groups,fits) if f['status']=='restored')
        complexity=sum(f['split']*len(g['targets']) for g,f in zip(groups,fits) if f['status']=='restored')
        supported=tuple(sorted(consistent_notes(fits)))if consistent_notes else None
        score=(len(supported)if supported is not None else count,count,-complexity)
        signature=tuple((f['status'],f['split'],tuple(f['rows'])) if f['status']=='restored' else ('failed',) for f in fits)
        trials.append({'phase_seconds':phase,'restored_targets':count,
                       'consistent_targets':score[0],'subdivision_complexity':complexity})
        if best is None or score>best:best=score;winners=[(phase,fits,signature,supported)]
        elif score==best:winners.append((phase,fits,signature,supported))
    if not best[0] or len({(w[2],w[3]) for w in winners})!=1:
        return {'status':'failed','reason':'ambiguous_or_unsupported_song_phase','fits':[
            {'status':'failed','reason':g.get('invalid','ambiguous_or_unsupported_song_phase')} for g in groups],
                'phase_trials':trials}
    lo,hi=winners[0][0],winners[-1][0];phase=(lo+hi)/2
    fits=[({'status':'failed','reason':g['invalid']} if g.get('invalid') else
           fit_grid(g['targets'],g['errors'],g['bpm'],g['origin']+phase,
                    native_chords=g.get('native_chords',()))) for g in groups]
    if consistent_notes and tuple(sorted(consistent_notes(fits)))!=winners[0][3]:
        return {'status':'failed','reason':'unstable_spatial_song_phase','phase_trials':trials,
                'fits':[{'status':'failed','reason':'unstable_spatial_song_phase'}for _ in groups]}
    half_step=uncertainty/steps if uncertainty else 0
    return {'status':'restored','phase':phase,'phase_range':[max(-uncertainty,lo-half_step),min(uncertainty,hi+half_step)],
            'resolution_seconds':2*half_step,'fits':fits,'phase_trials':trials,
            'consistent_notes':list(winners[0][3])if winners[0][3]is not None else None}
