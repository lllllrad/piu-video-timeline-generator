"""Recording-specific visual capability review, independent of chart gimmicks."""
import json
import math
from pathlib import Path


def visual_support(data):
    media=data.get('media',{});raw=Path(media.get('path','')).parent
    if raw.name!='raw':return None
    path=raw.parent/'visual-support.json'
    if not path.is_file():return None
    saved=json.loads(path.read_text())
    if (saved.get('schema')!=1 or saved.get('media')!={key:media[key] for key in ('size_bytes','mtime_ns')}):
        raise ValueError('Visual support review has stale source identity or unsupported schema')
    matches=[]
    for item in saved['regions']:
        lo,hi=item.get('start_seconds'),item.get('end_seconds')
        if (any(isinstance(t,bool) or not isinstance(t,(int,float)) or not math.isfinite(t) for t in (lo,hi))
                or not 0<=lo<hi or type(item.get('chart_geometry')) is not bool
                or not isinstance(item.get('reason'),str) or not item['reason'].strip()):
            raise ValueError('Visual support regions require bounded source times, capability and reason')
        if lo<data['end_seconds'] and hi>data['start_seconds']:matches.append(item)
    if not matches:return None
    return {'chart_geometry':all(item['chart_geometry'] for item in matches),
            'regions':matches,'review_file':str(path)}


def require_chart_geometry(data):
    support=visual_support(data)
    if support and not support['chart_geometry']:
        reasons='; '.join(item['reason'] for item in support['regions'] if not item['chart_geometry'])
        raise ValueError('Unsupported visual profile for UCS generation: '+reasons)
