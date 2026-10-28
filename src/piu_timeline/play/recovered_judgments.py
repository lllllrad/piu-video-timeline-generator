"""Attach recovered labels in TypeScript without moving measured brackets."""
from piu_timeline.derived import call,evidence_input


def attach_recovered_labels(data):
    result=call('labels.attachRecoveredLabels',evidence_input(data))
    fields=('matches','judgment_events','conflicted_matches','association_view_format','coverage')
    return {**data,**{k:result[k]for k in fields if k in result}}
