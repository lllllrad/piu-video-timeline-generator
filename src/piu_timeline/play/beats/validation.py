"""Validate known chart rows before using them as native timing references."""
from piu_timeline.play.spacing_checks import spacing_failures
from piu_timeline.play.beats.chords import prepare,conflicts as chord_conflicts


def validate(data,notes,spacing,support,baseline_indices=None,changed_indices=None):
    if spacing is None:return [],[],[]
    checks=[]
    warnings=spacing_failures(notes,spacing,data.get('scroll_motion'),support,checks,baseline_indices,changed_indices)
    for warning in warnings:
        warning['reason']='beat_grid_conflicts_with_spatial_spacing'
        note=notes[warning['note']]
        note.update(status='excluded',reason=warning['reason'],target_seconds=None,
                    beat_reconstruction={**note['beat_reconstruction'],'status':'failed','reason':warning['reason']})
    chords=prepare({**data,'notes':notes},spacing)
    constraints=[p for p in chords if changed_indices is None or any(i in changed_indices for i in p['peer_notes'])]
    conflicts=chord_conflicts(notes,constraints)
    for warning in conflicts:
        note=notes[warning['note']]
        note.update(status='excluded',reason=warning['reason'],target_seconds=None,
                    beat_reconstruction={**note['beat_reconstruction'],'status':'failed','reason':warning['reason']})
    return warnings+conflicts,chords,checks
