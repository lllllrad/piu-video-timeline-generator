"""Self-contained, local HTML review of video-derived timing evidence."""
import json
import os
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4


def write_report(data,path,final_directory=None):
    """Render prepared view data only; never inspect observations or infer timing."""
    from piu_timeline.derived import call
    final_directory=Path(final_directory or path.parent)
    media=quote(os.path.relpath(data['media']['path'],final_directory),safe='/')
    content=call('report.render',json.dumps(data,ensure_ascii=False),
                 data.get('song') or 'Unknown song',data.get('chart') or 'Unknown chart',media)
    pending=path.with_name(f'.{path.name}.{uuid4().hex}.tmp')
    try:
        pending.write_text(content,encoding='utf-8')
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)
    return path


def write_index(document,root):
    """Render prepared summaries; incomplete reports never trigger inference."""
    from piu_timeline.derived import call
    entries=[]
    for number,segment in enumerate(document['segments'],1):
        summary=root/f'segment-{number:03}'/'report-summary.json'
        entries.append({'number':number,'song':segment.get('song'),'chart':segment.get('chart'),
                        'summary':json.loads(summary.read_text())if summary.is_file()else None})
    path=root/'index.html'
    path.write_text(call('report.index',entries),encoding='utf-8')
    return path
