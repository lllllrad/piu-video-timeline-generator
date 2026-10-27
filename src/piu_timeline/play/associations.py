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
    original=assignments(data)
    confirmed=[m for m in original if not m.get('processing_conflict')]
    conflicted=[m for m in original if m.get('processing_conflict')]
    result={**data,'matches':confirmed,'conflicted_matches':conflicted,'association_view_format':FORMAT}
    if 'coverage'in data:
        coverage=dict(data['coverage'])
        counts={'timed_note_heads':len(confirmed),
                'matched_combo_updates':len({m['combo_event']for m in confirmed if m.get('combo_event')is not None}),
                'judgment_only_note_heads':sum(m.get('evidence_source')=='judgment'for m in confirmed),
                'judgment_labeled_note_heads':sum(bool(m.get('judgment_label'))for m in confirmed),
                'unlabeled_timed_note_heads':sum(not m.get('judgment_label')for m in confirmed),
                'combo_frame_labeled_note_heads':sum(m.get('judgment_label_source')=='post_combo_frames'for m in confirmed)}
        coverage.update({k:v for k,v in counts.items()if k in coverage})
        result['coverage']=coverage
    return result


def disputed_refresh(data,note,events):
    """The same disputed assignment cannot reappear as a fresh recovery proof."""
    for match in data.get('conflicted_matches',[]):
        if match['note']!=note:continue
        lower=match.get('observation_lower_seconds',match.get('combo_lower_seconds'))
        upper=match.get('observation_upper_seconds',match.get('combo_upper_seconds'))
        for event in events:
            key={'combo':'combo_event','judgment':'judgment_event'}.get(event['source'])
            if (key and match.get(key)is not None and match[key]==event['event']
                    and lower is not None and upper is not None
                    and lower<=event['upper_seconds']+1e-6 and upper>=event['lower_seconds']-1e-6):return True
            if (lower is not None and upper is not None and abs(lower-event['lower_seconds'])<1e-6
                    and abs(upper-event['upper_seconds'])<1e-6):return True
    return False
