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
