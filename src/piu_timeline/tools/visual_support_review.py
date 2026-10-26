"""Render recording-specific skin observations independently of detector readiness."""
import argparse
import html
import json
import os
from pathlib import Path
from urllib.parse import quote

from piu_timeline import ROOT
from piu_timeline.play.support import visual_support

TAIL_LABELS = {
    'tap_like': 'Tap-like tail: body and nearby-frame evidence required',
    'distinct_endpoint': 'Visually distinct endpoint: promising for separation; timing needs calibration',
    'not_observed': 'Tail not observed in the reviewed sample',
    'not_reviewed': 'Not reviewed',
}


def recording_rows(directory):
    document = json.loads((directory/'analysis/analysis.json').read_text())
    path = directory/'visual-support.json'
    profile = json.loads(path.read_text()) if path.is_file() else {}
    reviews = profile.get('reviews', [])
    by_number = {}
    for review in reviews:
        number = review.get('segment_number')
        if (type(number) is not int or not 1 <= number <= len(document['segments']) or number in by_number
                or review.get('tail_appearance') not in TAIL_LABELS
                or not isinstance(review.get('observation'), str) or not review['observation'].strip()):
            raise ValueError('Skin reviews require a unique play number, tail appearance and observation')
        by_number[number] = review
    rows = []
    for number, segment in enumerate(document['segments'], 1):
        support = visual_support({**segment, 'media': document['media']})
        review = by_number.get(number, {})
        reasons = [r['reason'] for r in (support or {}).get('regions', []) if not r['chart_geometry']]
        rows.append({'source': directory.name, 'segment': number, 'song': segment.get('song'),
                     'chart': segment.get('chart'), 'start_seconds': segment['start_seconds'],
                     'end_seconds': segment['end_seconds'],
                     'tail_appearance': review.get('tail_appearance', 'not_reviewed'),
                     'observation': review.get('observation', 'No tail evidence has been reviewed.'),
                     'evidence': review.get('evidence', []), 'ucs_block_reasons': reasons})
    return rows


def render(rows, output):
    def escape(value):return html.escape(str(value or 'Unknown'))
    rendered = []
    for row in rows:
        evidence = []
        for item in row['evidence']:
            path = Path(item['path']).resolve()
            if not path.is_file():raise ValueError('Missing skin review evidence: '+str(path))
            link = quote(os.path.relpath(path, output.parent), safe='/')
            evidence.append(f'<a href="{link}"><img loading="lazy" src="{link}" alt="Native review frame">'
                            f'<br>{escape(item.get("caption", path.name))}</a>')
        gate = ('Blocked: '+'; '.join(row['ucs_block_reasons']) if row['ucs_block_reasons'] else
                'No recording-specific block configured. This is not verified UCS support.')
        rendered.append('<tr><td>'+escape(row['source'])+f'<br>Play {row["segment"]:03}<br>'+
                        escape(row['song'])+' / '+escape(row['chart'])+
                        f'<br>{row["start_seconds"]:.3f}–{row["end_seconds"]:.3f}s</td><td>'+
                        escape(TAIL_LABELS[row['tail_appearance']])+'<p>'+escape(row['observation'])+
                        '</p></td><td>'+escape(gate)+'</td><td>'+''.join(evidence)+'</td></tr>')
    return ('<!doctype html><meta charset="utf-8"><title>Recording skin review</title>'
            '<style>body{font:16px system-ui;background:#15171c;color:#eee;padding:24px}table{border-collapse:collapse;'
            'width:100%}td,th{border:1px solid #555;padding:12px;vertical-align:top}img{max-width:300px}a{color:#9dc9ff}</style>'
            '<h1>Recording skin review</h1><p>Tail appearance and current implementation are separate observations. '
            'Head detection counts do not establish hold-tail separation. A tap-like tail needs body connectivity '
            'and nearby-frame evidence; a distinct flat or notched endpoint can be easier to separate even when '
            'the current detector needs adaptation. Neither appearance certifies its receptor timing anchor.</p>'
            '<p>Unreviewed plays are not promoted by default. Export blocks below come directly from the current '
            'recording support file. All reconstruction warnings remain active. Times are original recording times.</p>'
            '<table><tr><th>Play</th><th>Observed tail appearance</th><th>Current UCS processing gate</th>'
            '<th>Native evidence</th></tr>'+''.join(rendered)+'</table>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', nargs='+', required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'.local/reports/new-skins/index.html')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'.local'):parser.error('--output must stay under .local/')
    rows = []
    for source in args.sources:rows.extend(recording_rows(ROOT/'.local/data'/source))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(rows, args.output.resolve()), encoding='utf-8')
    print(args.output)


if __name__ == '__main__':main()
