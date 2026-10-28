"""Prepare report data from retained observations before rendering HTML."""
import json
import sys
from pathlib import Path


def prepare_report(data,path,final_directory=None):
    from piu_timeline.play.observations.presentation import prepare
    from piu_timeline.derived import call
    request = prepare(data, path.parent)
    pending = path.with_name('presentation-input.build.json')
    pending.write_text(json.dumps(request, ensure_ascii=False, allow_nan=False)+'\n')
    pending.replace(path.with_name('presentation-input.json'))
    source = data
    data = call('presentation.prepare', request, str(path.parent))
    from piu_timeline.play.observations.inspector import snapshot
    data['inspector_artifacts'] = snapshot(source, path.parent)
    artifacts = {'visual-support.json': data.get('visual_support'),
                 'object-interpretation.json': data.get('object_interpretation', {}),
                 'visibility-diagnostics.json': data['visibility_diagnostics'],
                 'beat-timing.json': data.get('beat_timing', {}),
                 'timing-reconstruction.json': data.get('timing_reconstruction', {})}
    if data.get('chart_policy'):
        artifacts['chart-policy.json'] = data['chart_policy']
    for name, value in artifacts.items():
        path.with_name(name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    reconstruction = data.get('timing_reconstruction', {})
    if reconstruction.get('status') == 'failed':
        print(f"Warning: timing reconstruction FAILED for {reconstruction['failed_notes']} note trajectories; rejected estimates are retained only for review.", file=sys.stderr)
    exclusions, recognition = data['exclusion_diagnostics'], data['recognition_diagnostics']
    final_directory=Path(final_directory or path.parent)
    path.with_name('timing-ranges.json').write_text(json.dumps(data['timing_ranges'], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    path.with_name('excluded-trajectories.json').write_text(json.dumps(exclusions, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    path.with_name('recognition-warnings.json').write_text(json.dumps(recognition, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    count = exclusions['counts']['unaccounted_excluded_tracks']
    if count:
        destination = final_directory / path.name
        print(f'Warning: {count} visible note tracks were excluded without an explicit chart exception. Review {destination} (excluded-trajectories.json).', file=sys.stderr)
    if recognition['warnings']:
        print(f"Warning: {len(recognition['warnings'])} unresolved recognition items. Review {final_directory / path.name} (recognition-warnings.json).", file=sys.stderr)
    prepared=path.with_name('report-data.json')
    pending=prepared.with_suffix('.build.json')
    pending.write_text(json.dumps(data,ensure_ascii=False)+'\n')
    pending.replace(prepared)
    return data


def build_report(data,path,final_directory=None):
    from piu_timeline.play.report import write_report
    prepared=prepare_report(data,path,final_directory)
    result=write_report(prepared,path,final_directory)
    summary={key:prepared[key]for key in ('coverage','combo_readable_fraction','play_analysis_version')if key in prepared}
    pending=path.with_name('report-summary.build.json')
    pending.write_text(json.dumps(summary)+'\n')
    pending.replace(path.with_name('report-summary.json'))
    return result


def refresh_registration(data, directory):
    """Refresh saved registration provenance after chart registration, without analysis."""
    from piu_timeline.play.observations.inspector import snapshot
    from piu_timeline.play.report import write_report
    directory = Path(directory)
    prepared = directory/'report-data.json'
    if not prepared.is_file():
        return
    view = json.loads(prepared.read_text())
    artifacts = snapshot(data, directory)
    if artifacts == view.get('inspector_artifacts'):
        return
    view['inspector_artifacts'] = artifacts
    pending = directory/'report-data.build.json'
    pending.write_text(json.dumps(view, ensure_ascii=False)+'\n')
    write_report(view, directory/'report.html')
    pending.replace(prepared)
