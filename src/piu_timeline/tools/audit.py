"""Summarize saved recognition warnings without decoding or rewriting analyses."""
import argparse
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
from urllib.parse import quote

from piu_timeline import ROOT
from piu_timeline.play.holds.analysis import presentation


def label_cause(match, events, observations, times):
    index = match.get('combo_event')
    if index is None:
        return 'no_counter_anchor'
    event = events[index]
    if event['delta'] != 1:
        return 'aggregate_counter_jump'
    if event['upper_seconds']-event['lower_seconds'] > .1:
        return 'wide_counter_bracket'
    start = event['upper_seconds']; stop = start+.050001
    if index+1 < len(events):
        stop = min(stop, events[index+1]['lower_seconds']-1e-6)
    frames = observations[bisect_left(times, start-1e-6):bisect_right(times, stop)]
    if len({f['label'] for f in frames if f['label']}) > 1:
        return 'conflicting_label_reads'
    known = [f for f in frames if f['label'] and f['confidence'] >= .8]
    return 'fewer_than_two_clear_reads' if len(known) < 2 else 'late_or_disconnected_label_reads'


def summarize(path):
    directory = path.parent
    before = path.stat()
    data = json.loads(path.read_text())
    warnings = json.loads((directory/'recognition-warnings.json').read_text())
    excluded = json.loads((directory/'excluded-trajectories.json').read_text())
    ranges = json.loads((directory/'timing-ranges.json').read_text())
    records = [dict(item) for item in warnings['warnings']]
    projected = None; matches = {}; observations = []; times = []
    if any(item['reason'] == 'judgment_label_unresolved' for item in records):
        projected = presentation(data)
        matches = {m['note']:m for m in projected['matches']}
        trace = directory/'judgments.jsonl'
        if trace.is_file():
            observations = [json.loads(line) for line in trace.open()]
            times = [f['playback_seconds'] for f in observations]
    for item in records:
        reason = item['reason']; record = ranges['notes'].get(str(item.get('note')), {})
        item['classification'] = reason
        if reason == 'timing_evidence_unresolved':
            item.update(classification=record.get('reason', 'missing_timing_range'),
                        timing_status=record.get('status'), rejected_candidates=record.get('rejected_candidates', []))
        elif reason == 'judgment_label_unresolved':
            match = matches.get(item['note'])
            item['classification'] = (label_cause(match, projected['combo_events'], observations, times)
                                      if match else 'owned_refresh_missing_from_projection')
        elif reason == 'unresolved_hold_geometry':
            continuity = item.get('cap_continuity') or {}
            item['classification'] = ('weak_or_inconsistent_intercap_color' if continuity.get('decision') == 'unresolved'
                                      else 'insufficient_independent_cap_registration')
    media = data.get('media', {})
    try:
        stat = Path(media['path']).stat()
        preserved = (stat.st_size, stat.st_mtime_ns) == (media['size_bytes'], media['mtime_ns'])
    except (KeyError, OSError):
        preserved = None
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError('Analysis changed during review; retry after promotion')
    return {'source':directory.parents[1].name, 'segment':int(directory.name.removeprefix('segment-')),
            'song':data.get('song'), 'chart':data.get('chart'), 'report':str(directory/'report.html'),
            'play_analysis_version':data.get('play_analysis_version'),
            'hold_association_format':data.get('hold_analysis', {}).get('association_contract', {}).get('format'),
            'warning_counts':dict(Counter(item['reason'] for item in records)),
            'classifications':dict(Counter(item['classification'] for item in records)),
            'excluded_counts':excluded['counts'],
            'excluded_reasons':dict(Counter(item['reason'] for item in excluded['warnings'])),
            'source_identity_preserved':preserved, 'items':records}


def review(root, output, sources=(), segments=()):
    root, output = Path(root), Path(output)
    plays, errors = [], []
    for path in sorted((root/'.local/data').glob('*/play/segment-[0-9][0-9][0-9]/analysis.json')):
        source, number = path.parents[2].name, int(path.parent.name.removeprefix('segment-'))
        if sources and source not in sources or segments and number not in segments:
            continue
        try:
            plays.append(summarize(path))
        except (OSError, ValueError, KeyError, IndexError) as error:
            errors.append({'source':source, 'segment':number, 'error':str(error)})
    counts = Counter()
    for play in plays:
        counts.update(play['warning_counts'])
    document = {'created':datetime.now(timezone.utc).isoformat(), 'warning_counts':dict(counts),
                'plays':plays, 'errors':errors,
                'scope':'Saved warning classifications only. Not a verified chart accuracy or stage-grade consistency estimate.'}
    output.mkdir(parents=True, exist_ok=True)
    pending = output/'review.build-json'; pending.write_text(json.dumps(document, ensure_ascii=False, indent=2)+'\n')
    pending.replace(output/'review.json')
    parts = ['<!doctype html><meta charset="utf-8"><title>Recognition review</title>',
             '<h1>Recognition review</h1><p>'+html.escape(document['scope'])+'</p>',
             '<p><a href="review.json">Complete evidence classification</a></p>']
    for play in plays:
        link = quote(os.path.relpath(play['report'], output), safe='/')
        title = f'{play["source"]} / {play["segment"]:03} / {play["song"]} / {play["chart"]}'
        parts.append('<h2><a href="'+html.escape(link, quote=True)+'">'+html.escape(title)+'</a></h2><table>')
        parts.extend('<tr><td>'+html.escape(k.replace('_', ' '))+'</td><td>'+str(v)+'</td></tr>'
                     for k,v in play['classifications'].items())
        parts.append('</table>')
    for error in errors:
        parts.append('<p>Unavailable: '+html.escape(str(error))+'</p>')
    pending = output/'index.build-html'; pending.write_text(''.join(parts)); pending.replace(output/'index.html')
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', nargs='+')
    parser.add_argument('--segments', nargs='+', type=int)
    parser.add_argument('--output', type=Path, default=ROOT/'.local/reports/recognition-review')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'.local'):
        parser.error('--output must stay under .local/')
    result = review(ROOT, args.output, args.sources or (), args.segments or ())
    print(args.output/'index.html')
    if result['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
