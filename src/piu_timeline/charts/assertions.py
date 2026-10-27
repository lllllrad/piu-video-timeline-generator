"""Validate reviewed chart facts stored in the separate chart repository."""
import math


def validate(document, assertions):
    if not isinstance(assertions,list):raise ValueError('Chart row assertions must be a list')
    seen=set();grid=list(document.grid()) if assertions else []
    for fact in assertions:
        if (not isinstance(fact,dict) or set(fact)!={'id','start_seconds','end_seconds','cells','reason'}
                or not isinstance(fact['id'],str) or not fact['id'] or fact['id']in seen
                or not isinstance(fact['reason'],str) or not fact['reason'].strip()):
            raise ValueError('Invalid reviewed chart row assertion')
        seen.add(fact['id']);lo,hi=fact['start_seconds'],fact['end_seconds'];cells=fact['cells']
        if (any(type(t)not in (int,float)or not math.isfinite(t)for t in (lo,hi)) or not 0<=lo<hi
                or not isinstance(cells,dict)or not cells):
            raise ValueError('Invalid reviewed chart assertion interval or cells')
        if any(not isinstance(lane,str)or not lane.isascii()or not lane.isdecimal()
               or not 0<=int(lane)<document.lanes or kind not in ('.','X','M','H','W') for lane,kind in cells.items()):
            raise ValueError('Invalid reviewed chart assertion lane or note kind')
        if not any(lo<=float(t)<hi and all(document.sections[si].rows[ri][int(lane)]==kind for lane,kind in cells.items())
                   for si,ri,t in grid):
            raise ValueError(f'Chart row assertion {fact["id"]} failed: {fact["reason"]}')
