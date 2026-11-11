"""Bounded standalone evidence reports and an explicit legacy inspector renderer."""
import json
import os
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4


def write_summary(data,directory):
    """Publish index fields from the prepared view, without running inference."""
    summary={key:data.get(key)for key in ('coverage','combo_readable_fraction','play_analysis_version')}
    summary['counts']={key:len(data.get(key) or [])for key in ('notes','matches','combo_events','judgment_events')}
    summary['start_seconds']=data.get('start_seconds')
    summary['end_seconds']=data.get('end_seconds')
    summary['warnings']=[]
    summary['warning_count']=0
    for kind in ('recognition_diagnostics','exclusion_diagnostics'):
        warnings=(data.get(kind) or {}).get('warnings') or []
        summary['warning_count']+=len(warnings)
        for warning in warnings[:max(0,30-len(summary['warnings']))]:
            summary['warnings'].append({key:warning[key][:240]if isinstance(warning[key],str)else warning[key]for key in
                ('reason','check','lane','visible_start_seconds','visible_end_seconds','start_seconds','end_seconds')if key in warning})
    path=directory/'report-summary.json'
    pending=path.with_name(f'.report-summary.{uuid4().hex}.tmp')
    try:
        pending.write_text(json.dumps(summary,ensure_ascii=False)+'\n',encoding='utf-8')
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)
    return summary


def write_report(data,path,final_directory=None,*,prepared_path=None,legacy=False):
    """Render prepared view data only; never inspect observations or infer timing."""
    from piu_timeline.derived import call
    final_directory=Path(final_directory or path.parent)
    media=quote(os.path.relpath(data['media']['path'],final_directory),safe='/')
    pending=path.with_name(f'.{path.name}.{uuid4().hex}.tmp')
    prepared=Path(prepared_path)if prepared_path is not None else pending.with_suffix('.data.json')
    owns_prepared=prepared_path is None
    try:
        if owns_prepared:
            with prepared.open('w',encoding='utf-8')as stream:
                json.dump(data,stream,ensure_ascii=False,allow_nan=False)
        summary=write_summary(data,path.parent)
        arguments=[str(prepared),str(pending),data.get('song') or 'Unknown song',data.get('chart') or 'Unknown chart',media]
        if not legacy:arguments.append(summary)
        call('report.renderFile' if legacy else 'report.renderShellFile',*arguments)
        pending.replace(path)
        if not legacy and owns_prepared:
            prepared.replace(path.with_name('report-data.json'))
    finally:
        pending.unlink(missing_ok=True)
        if owns_prepared:prepared.unlink(missing_ok=True)
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
