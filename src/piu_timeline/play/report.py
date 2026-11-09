"""Self-contained, local HTML review of video-derived timing evidence."""
import json
import os
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4


def write_summary(data,directory):
    """Publish index fields from the prepared view, without running inference."""
    summary={key:data.get(key)for key in ('coverage','combo_readable_fraction','play_analysis_version')}
    path=directory/'report-summary.json'
    pending=path.with_name(f'.report-summary.{uuid4().hex}.tmp')
    try:
        pending.write_text(json.dumps(summary,ensure_ascii=False)+'\n',encoding='utf-8')
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)
    return summary


def write_report(data,path,final_directory=None,*,prepared_path=None):
    """Render prepared view data only; never inspect observations or infer timing."""
    from piu_timeline.derived import call
    final_directory=Path(final_directory or path.parent)
    media=quote(os.path.relpath(data['media']['path'],final_directory),safe='/')
    pending=path.with_name(f'.{path.name}.{uuid4().hex}.tmp')
    prepared=Path(prepared_path)if prepared_path is not None else pending.with_suffix('.data.json')
    try:
        if prepared_path is None:
            with prepared.open('w',encoding='utf-8')as stream:
                json.dump(data,stream,ensure_ascii=False,allow_nan=False)
        call('report.renderFile',str(prepared),str(pending),
             data.get('song') or 'Unknown song',data.get('chart') or 'Unknown chart',media)
        pending.replace(path)
        write_summary(data,path.parent)
    finally:
        pending.unlink(missing_ok=True)
        if prepared_path is None:prepared.unlink(missing_ok=True)
    return path


def write_index(document,root):
    """Render prepared summaries; incomplete reports never trigger inference."""
    from piu_timeline.derived import call
    entries=[]
    for number,segment in enumerate(document['segments'],1):
        summary=root/f'segment-{number:03}'/'report-summary.json'
        prepared=summary.with_name('report-data.json')
        try:
            saved=json.loads(summary.read_text())
            if prepared.is_file() and prepared.stat().st_mtime_ns>summary.stat().st_mtime_ns:
                saved=write_summary(json.loads(prepared.read_text()),summary.parent)
        except FileNotFoundError:
            # Existing prepared reports can repair a missing summary offline.
            try:
                saved=write_summary(json.loads(prepared.read_text()),summary.parent)if summary.with_name('report.html').is_file()else None
            except FileNotFoundError:saved=None  # A producer may be promoting this directory.
        entries.append({'number':number,'song':segment.get('song'),'chart':segment.get('chart'),
                        'summary':saved})
    path=root/'index.html'
    pending=path.with_name(f'.index.{uuid4().hex}.tmp')
    try:
        pending.write_text(call('report.index',entries),encoding='utf-8')
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)
    return path
