"""Bounded standalone evidence reports and an explicit legacy inspector renderer."""
import json
import os
import re
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4


def skin_state(root,number):
    """Saved per-segment skin decision; a report retained under an unresolved skin is stale."""
    path=Path(root)/'skin-selections'/f'segment-{number:03}.json'
    if not path.is_file():return None
    decision=json.loads(path.read_text()).get('decision')or {}
    status=decision.get('status')
    if status=='selected':return {'status':'selected','selection':decision.get('selection')}
    if status:return {'status':status,'reason':decision.get('reason')}
    return None


def segment_skin(directory):
    """Resolve the skin decision for a `segment-NNN` directory, ignoring other layouts."""
    match=re.fullmatch(r'segment-(\d+)',Path(directory).name)
    return skin_state(Path(directory).parent,int(match.group(1)))if match else None


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
    # A newly generated report is always backed by a selected skin; record it so the index
    # and report never present an unresolved-skin reconstruction as current evidence.
    skin=segment_skin(directory)
    if skin is not None and skin['status']=='selected':summary['skin']=skin
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


def _surface_stale(directory,document,segment,number,summary,skin):
    """Mark a retained summary and standalone report as stale under an unresolved skin.

    Presentation only: it never touches native analysis evidence or recognition warnings.
    """
    from piu_timeline.derived import call
    if summary is None:return summary  # no report to mark
    patched={**summary,'skin':skin}
    # Pre-gate summaries omit the recording interval; the segment metadata is authoritative for it.
    for key in ('start_seconds','end_seconds'):
        if patched.get(key)is None and segment.get(key)is not None:patched[key]=segment[key]
    if patched==summary:return summary  # already surfaced
    summary=patched
    path=directory/'report-summary.json'
    pending=path.with_name(f'.report-summary.{uuid4().hex}.tmp')
    try:
        pending.write_text(json.dumps(summary,ensure_ascii=False)+'\n',encoding='utf-8')
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)
    report=directory/'report.html'
    if report.is_file():
        media=quote(os.path.relpath(document['media']['path'],directory),safe='/')
        pending=report.with_name(f'.report.{uuid4().hex}.tmp')
        try:
            call('report.renderShellFile',str(directory/'report-data.json'),str(pending),
                 segment.get('song')or 'Unknown song',segment.get('chart')or 'Unknown chart',media,summary)
            pending.replace(report)
        finally:
            pending.unlink(missing_ok=True)
    return summary


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
        skin=skin_state(root,number)
        if skin is not None and skin['status']!='selected':
            # Existing stale artifacts predate the skin gate and carry no skin field; surface
            # the unresolved decision in the retained summary and standalone report too.
            saved=_surface_stale(summary.parent,document,segment,number,saved,skin)
        entries.append({'number':number,'song':segment.get('song'),'chart':segment.get('chart'),
                        'summary':saved,'skin':skin})
    path=root/'index.html'
    pending=path.with_name(f'.index.{uuid4().hex}.tmp')
    try:
        pending.write_text(call('report.index',entries),encoding='utf-8')
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)
    return path
