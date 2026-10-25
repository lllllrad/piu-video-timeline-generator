"""Self-contained, local HTML review of video-derived timing evidence."""
import html
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote


def write_report(data, path, final_directory=None):
    native = data
    from piu_timeline.charts.policy import attach_regions, apply_projection
    data = attach_regions(data, path.parent)
    from piu_timeline.play.holds.analysis import presentation
    data = apply_projection(presentation(data))
    from piu_timeline.play.exclusions import exclusion_diagnostics, recognition_diagnostics
    exclusions = exclusion_diagnostics(native, data)
    data = {**data, 'exclusion_diagnostics': exclusions}
    from piu_timeline.play.ranges import timing_ranges, counter_frame_ranges
    ranges = timing_ranges(data)
    frames = path.with_name('frames.jsonl')
    if ranges['counts'].get('unknown') and frames.is_file():
        ranges = timing_ranges({**data, 'counter_frame_events': counter_frame_ranges(frames)})
    data = {**data, 'timing_ranges': ranges}
    recognition = recognition_diagnostics(data, ranges)
    data['recognition_diagnostics'] = recognition
    final_directory = Path(final_directory or path.parent)
    media = quote(os.path.relpath(data['media']['path'], final_directory), safe='/')
    encoded = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    title = html.escape(f"{data.get('song') or 'Unknown song'} · {data.get('chart') or 'Unknown chart'}")
    parts = {'TITLE': title, 'MEDIA': html.escape(media, quote=True), 'DATA': encoded}
    content = re.sub(r'__(TITLE|MEDIA|DATA)__', lambda match: parts[match[1]], TEMPLATE)
    path.write_text(content, encoding='utf-8')
    path.with_name('timing-ranges.json').write_text(json.dumps(data['timing_ranges'], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    path.with_name('excluded-trajectories.json').write_text(json.dumps(exclusions, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    path.with_name('recognition-warnings.json').write_text(json.dumps(recognition, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    count = exclusions['counts']['unaccounted_excluded_tracks']
    if count:
        destination = final_directory / path.name
        print(f'Warning: {count} visible note tracks were excluded without an explicit chart exception. Review {destination} (excluded-trajectories.json).', file=sys.stderr)
    if recognition['warnings']:
        print(f"Warning: {len(recognition['warnings'])} unresolved recognition items. Review {final_directory / path.name} (recognition-warnings.json).", file=sys.stderr)


def write_index(document, root):
    """List every metadata segment, including failures and incomplete analyses."""
    rows = []
    for number, segment in enumerate(document['segments'], 1):
        relative = f'segment-{number:03}'
        analysis = root / relative / 'analysis.json'
        title = html.escape(f"{segment.get('song') or 'Unknown song'} · {segment.get('chart') or 'Unknown chart'}")
        if analysis.is_file():
            from piu_timeline.play.holds.analysis import presentation
            from piu_timeline.charts.policy import attach_regions, apply_projection
            data = apply_projection(presentation(attach_regions(json.loads(analysis.read_text()), analysis.parent)))
            coverage = data['coverage']
            cells = (f'<a href="{relative}/report.html">{title}</a>', str(coverage['visible_note_heads']),
                     str(coverage.get('long_notes', 0)), str(coverage['timed_note_heads']), str(coverage['matched_combo_updates']),str(coverage.get('judgment_only_note_heads',0)),
                     f"{100*data['combo_readable_fraction']:.0f}%", str(data['play_analysis_version']))
        else:
            cells = (title, 'Unavailable', 'Unavailable', 'Unavailable', 'Unavailable', 'Unavailable', 'Unavailable', 'Unavailable')
        rows.append('<tr><td>'+str(number)+'</td>'+''.join('<td>'+cell+'</td>' for cell in cells)+'</tr>')
    path = root / 'index.html'
    path.write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Play timing reports</title><style>body{font:16px/1.6 system-ui;max-width:1200px;margin:40px auto;padding:20px;background:#101719;color:#e5efeb}
a{color:#9cddbe}
table{border-collapse:collapse;width:100%}
td,th{padding:10px;text-align:left;border-bottom:1px solid #314448}
.scroll{overflow:auto}

</style>
<h1>Play timing reports</h1><p>Each report compares visible note trajectories with observed combo and judgment refreshes. A chord is one judged row and may contain several heads. Counts are partial reconstruction, not a complete chart or physical switch measurement. Open a report for excluded motion and unassigned counter evidence.</p>
<div class="scroll"><table><thead><tr><th>Segment</th><th>Play</th><th>Reconstructed heads</th><th>Long notes</th><th>Heads with tap timing</th><th>Matched combo refreshes</th><th>Judgment-only timed heads</th><th>Readable counter frames</th><th>Analyzer version</th></tr></thead><tbody>'''
                    + ''.join(rows) + '</tbody></table></div></html>', encoding='utf-8')
    return path


_RESOURCES = Path(__file__).parent
TEMPLATE = (_RESOURCES / 'report.html').read_text(encoding='utf-8')
TEMPLATE = TEMPLATE.replace('__STYLE__', (_RESOURCES / 'report.css').read_text(encoding='utf-8'))
TEMPLATE = TEMPLATE.replace('__SCRIPT__', (_RESOURCES / 'report-evidence.js').read_text(encoding='utf-8')+'\n'+(_RESOURCES / 'report.js').read_text(encoding='utf-8'))
