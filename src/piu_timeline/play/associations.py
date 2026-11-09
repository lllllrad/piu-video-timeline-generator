"""Separate usable associations from retained, disputed refresh assignments."""
FORMAT={'schema':1,'revision':1,'policy':'processing_conflicts_quarantined'}


def assignments(data):
    current=list(data.get('matches',[]));notes={m['note']for m in current}
    return current+[m for m in data.get('conflicted_matches',[])if m['note']not in notes]


def source_assignments(data):
    """Keep initial counter/word hypotheses stable across later quarantine."""
    notes=data.get('notes',[])
    def order(match):
        note=notes[match['note']]if match['note']<len(notes)else{}
        return match.get('target_seconds',note.get('target_seconds',float('inf'))),match['note']
    return sorted(assignments(data),key=order)


def partition(data):
    from piu_timeline.derived import call
    fields=('matches','conflicted_matches','coverage')
    return {**data,**call('evidence.associationPatch',{k:data[k]for k in fields if k in data})}


def disputed_refresh(data,note,events):
    from piu_timeline.derived import call
    return call('evidence.disputedRefresh',{'conflicted_matches':data.get('conflicted_matches',[])},note,events)


def associate_counters(data,combo,display_delay_ms,directory=None):
    notes=data['notes']
    from piu_timeline.play.counter_refinement import refine_events, refinement_constraints
    original = combo.events
    combo.events = refine_events(original,combo.observations)
    constraints = None
    if len(combo.events) != len(original):
        from piu_timeline.play.tracking import associate
        baseline = associate(notes,[dict(e) for e in original],display_delay=display_delay_ms/1000)
        constraints = {str(event):sorted(allowed) for event,allowed in
                       refinement_constraints(notes,original,baseline,combo.events).items()}
    from piu_timeline.derived import call
    request={'schema':1,'notes':[{key:note[key] for key in ('lane','status','target_seconds','prediction_uncertainty_seconds','reason') if key in note} for note in notes],'events':combo.events,'display_delay_seconds':display_delay_ms/1000,
             'unsupported_intervals':data['unsupported_intervals'],'constraints':constraints}
    associations=call('stageAssociations.counters',request)
    if directory is not None:
        from pathlib import Path
        from piu_timeline.play.observations.artifacts import save_input
        save_input(Path(directory)/'counter-input.json',request)
        save_input(Path(directory)/'counter-associations.json',associations)
    return {**data,**associations['data']}
