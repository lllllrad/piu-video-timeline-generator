"""Prepare report data from retained observations before rendering HTML."""
import json
import sys
from pathlib import Path


def prepare_report(data,path,final_directory=None):
    from piu_timeline.play.support import visual_support
    data={**data,'visual_support':visual_support(data)}
    path.with_name('visual-support.json').write_text(json.dumps(data['visual_support'],ensure_ascii=False,indent=2)+'\n')
    native = data
    from piu_timeline.charts.policy import attach_regions, apply_projection
    data = attach_regions(data, path.parent)
    from piu_timeline.play.holds.analysis import presentation
    from piu_timeline.play.gimmicks import apply_gimmicks
    data = apply_projection(apply_gimmicks(presentation(data),path.parent))
    path.with_name('object-interpretation.json').write_text(json.dumps(data.get('object_interpretation',{}),ensure_ascii=False,indent=2)+'\n')
    from piu_timeline.play.exclusions import exclusion_diagnostics, recognition_diagnostics
    exclusions = exclusion_diagnostics(native, data)
    data = {**data, 'exclusion_diagnostics': exclusions}
    from piu_timeline.play.ranges import timing_ranges, counter_frame_ranges
    ranges = timing_ranges(data)
    frames = path.with_name('frames.jsonl')
    if ranges['counts'].get('unknown') and frames.is_file():
        ranges = timing_ranges({**data, 'counter_frame_events': counter_frame_ranges(frames)})
    from piu_timeline.play.continuity import continuity_diagnostics
    native_frames=[]
    if frames.is_file():
        with frames.open()as stream:native_frames=[json.loads(line)for line in stream]
    continuity = continuity_diagnostics(data,native_frames)
    data = {**data, 'timing_ranges': ranges, 'visibility_diagnostics':continuity}
    path.with_name('visibility-diagnostics.json').write_text(json.dumps(continuity,ensure_ascii=False,indent=2)+'\n')
    path.with_name('beat-timing.json').write_text(json.dumps(data.get('beat_timing',{}),ensure_ascii=False,indent=2)+'\n')
    reconstruction=data.get('timing_reconstruction',{})
    if reconstruction.get('status')=='failed':
        print(f"Warning: timing reconstruction FAILED for {reconstruction['failed_notes']} note trajectories; rejected estimates are retained only for review.",file=sys.stderr)
    path.with_name('timing-reconstruction.json').write_text(json.dumps(reconstruction,ensure_ascii=False,indent=2)+'\n')
    recognition = recognition_diagnostics(data, ranges)
    data['recognition_diagnostics'] = recognition
    if data.get('chart_policy'):
        path.with_name('chart-policy.json').write_text(json.dumps(data['chart_policy'],ensure_ascii=False,indent=2)+'\n')
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
