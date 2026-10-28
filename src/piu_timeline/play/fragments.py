"""Acquisition Track adapters for TypeScript native-identity reconstruction."""
from piu_timeline.derived import CONTRACTS, call
FORMAT=CONTRACTS['fragments']


def same_native_head(note, owner):
    """Close target times alone cannot identify a duplicated head component."""
    if note['lane']!=owner['lane']:return False
    positions=dict(owner.get('points',[]))
    errors=[abs(y-positions[t]) for t,y in note.get('points',[]) if t in positions]
    return len(errors)>=4 and sum(error<=2 for error in errors)>=.8*len(errors)


def _motion(motion):
    return {**motion._state(),'evidence_format':getattr(motion,'evidence_format',{})} if motion is not None else None


def _restore(tracks,result):
    from piu_timeline.play.tracking import Track
    values,origins=result
    restored=[tracks[ids[0]] if len(ids)==1 else Track(value['lane'],[tuple(p)for p in value['points']])
              for value,ids in zip(values,origins,strict=True)]
    for track,value,ids in zip(restored,values,origins,strict=True):
        if len(ids)>1 and value.get('fragment_connections'):track.fragment_connections=value['fragment_connections']
    return restored,origins


def interleaved_tracks(tracks,spacing,motion):
    result=call('fragments.interleaved',[{'lane':t.lane,'points':t.points}for t in tracks],spacing,_motion(motion))
    return _restore(tracks,result)


def stitch_tracks(tracks,receptor,spacing,motion=None,layout=None):
    result=call('fragments.stitch',[{'lane':t.lane,'points':t.points}for t in tracks],receptor,spacing,_motion(motion),layout)
    values,origins=_restore(tracks,result)
    return list(zip(values,origins,strict=True))
