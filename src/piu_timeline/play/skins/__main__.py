"""Build image reference banks or inspect their native-frame detections."""
import argparse
from collections import Counter
import json
from pathlib import Path

from piu_timeline.play.frames import decode_frames
from piu_timeline.play.layout import fixed_layout
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.build import build
from piu_timeline.play.skins.calibration import register_anchors
from piu_timeline.play.skins.detector import FORMAT as DETECTOR_FORMAT
from piu_timeline.play.skins.pipeline import classified_frames
from piu_timeline.play.skins.review import review_bank
from piu_timeline.workflow import LOCAL_DATA, source_id


def scan(source, segment, bank_path, output, start=None, duration=3, width=650):
    data = json.loads((LOCAL_DATA / source_id(source) / 'analysis/analysis.json').read_text())
    before = Path(data['media']['path']).stat()
    if (before.st_size, before.st_mtime_ns) != (data['media']['size_bytes'], data['media']['mtime_ns']):
        raise ValueError('Image review source identity changed')
    play = data['segments'][segment - 1]
    layout = fixed_layout(play)
    if layout is None:
        raise ValueError('Image review requires a known full-screen layout and player side')
    start = play['start_seconds'] if start is None else start
    end = min(play['end_seconds'], start + duration)
    if not play['start_seconds'] <= start < end or duration <= 0:
        raise ValueError('Image review range must lie inside the selected play')
    bank = load_bank(bank_path)
    counts, frames = Counter(), []
    height=max(1,round(width*data['game_roi'][3]/data['game_roi'][2]))
    decoded=decode_frames(data['media'], start, end, data['game_roi'], width)
    for pts, time, _, observations in classified_frames(decoded,bank,layout,width,height):
        counts.update(o['role'] for o in observations)
        frames.append({'source_pts_seconds': pts, 'playback_seconds': time, 'observations': observations})
    if not frames:raise ValueError('No native source frames were available for image review')
    output = Path(output)
    after = Path(data['media']['path']).stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Source changed during image review')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'media': data['media'], 'segment': segment,
        'bank': bank['contract'], 'detector':DETECTOR_FORMAT,'analysis_width':width,
        'analysis_height':height,'layout':layout,'counts': dict(counts), 'frames': frames}) + '\n')
    print(json.dumps({'frames': len(frames), 'counts': dict(counts), 'output': str(output)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('build')
    create.add_argument('specification', type=Path)
    create.add_argument('--output', type=Path, required=True)
    anchors = commands.add_parser('register-anchors')
    anchors.add_argument('bank', type=Path)
    anchors.add_argument('--analysis', type=Path, required=True)
    anchors.add_argument('--registration', type=Path, required=True)
    anchors.add_argument('--output', type=Path, required=True)
    references = commands.add_parser('review-bank')
    references.add_argument('bank', type=Path)
    references.add_argument('--output', type=Path, required=True)
    references.add_argument('--lane-kind', type=int, choices=range(5))
    review = commands.add_parser('scan')
    review.add_argument('source')
    review.add_argument('--segment', type=int, required=True)
    review.add_argument('--bank', type=Path, required=True)
    review.add_argument('--output', type=Path, required=True)
    review.add_argument('--start', type=float)
    review.add_argument('--duration', type=float, default=3)
    args = parser.parse_args()
    if args.command == 'build':
        print(build(args.specification, args.output))
    elif args.command == 'register-anchors':
        print(register_anchors(args.bank,args.analysis,args.registration,args.output))
    elif args.command == 'review-bank':
        print(review_bank(args.bank,args.output,args.lane_kind))
    else:
        scan(args.source, args.segment, args.bank, args.output, args.start, args.duration)


if __name__ == '__main__':
    main()
