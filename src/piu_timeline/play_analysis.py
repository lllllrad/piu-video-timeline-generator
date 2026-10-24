"""Opt-in, evidence-based reconstruction of visible notes and combo timing."""
import argparse
from collections import Counter
import fcntl
import json
import math
from pathlib import Path
import re
import shutil
import uuid

import cv2
import numpy as np

from .ocr import ocr_images
from .play_frames import decode_frames, crop_region
from .play_tracking import NoteTracker, DigitReader, ComboTracker, associate
from .recognition import capture_game
from .workflow import LOCAL_DATA, source_id

VERSION = 4
COLORS = ('blue', 'red', 'yellow', 'red', 'blue')
NAMES = ('DL', 'UL', 'C', 'UR', 'DR')


def result_reference(segment, player=None):
    """Reuse corroborated result OCR as a coverage reference, not a chart count."""
    results = segment.get('results') or {}
    players = results.get('players', {})
    if player is None and len(players) == 1:
        player = next(iter(players))
    result = players.get(player, {})
    fields = result.get('fields', {})
    names = ('perfect', 'great', 'good', 'bad', 'miss')
    if not all(fields.get(name, {}).get('status') == 'recognized'
               and isinstance(result.get(name), int) for name in names):
        return None
    counts = {name: result[name] for name in names}
    return {'player': player, 'counts': counts, 'total': sum(counts.values()),
            'max_combo': result.get('max_combo'), 'evidence': results.get('evidence')}


def validate_layout(layout):
    if not isinstance(layout, dict) or not isinstance(layout.get('lanes'), list) or len(layout['lanes']) not in (5, 10):
        raise ValueError('Layout needs 5 or 10 ordered lanes')
    xs = []
    for lane in layout['lanes']:
        x = lane.get('x')
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 < x < 1:
            raise ValueError('Lane x must be a finite game-relative fraction')
        if lane.get('color') not in COLORS:
            raise ValueError('Lane color must be blue, red or yellow')
        xs.append(x)
    if any(b - a < .01 for a, b in zip(xs, xs[1:])):
        raise ValueError('Lane centers must be ordered and separated')
    receptor = layout.get('receptor_y')
    bottom = layout.get('note_y_max', .95)
    if not isinstance(receptor, (int, float)) or not isinstance(bottom, (int, float)) or not 0 < receptor < bottom < 1:
        raise ValueError('Layout needs 0 < receptor_y < note_y_max < 1')
    region = layout.get('combo_roi', [])
    if len(region) != 4 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in region):
        raise ValueError('combo_roi needs four finite fractions')
    x, y, w, h = region
    if not (0 <= x < x + w <= 1 and 0 <= y < y + h <= 1):
        raise ValueError('combo_roi must fit inside the game image')
    return layout


def locate_layout(rgb, chart, player=None):
    height, width = rgb.shape[:2]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = ((hsv[:, :, 1] < 65) & (hsv[:, :, 2] > 160)).astype('uint8') * 255
    mask[:int(height * .065)] = 0; mask[int(height * .23):] = 0
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if .035 * width < w < .09 * width and .05 * height < h < .15 * height:
            candidates.append((x + w / 2, y + h / 2))
    groups = []
    for x, y in sorted(candidates):
        if groups and x - np.mean([p[0] for p in groups[-1]]) < .012 * width:
            groups[-1].append((x, y))
        else:
            groups.append([(x, y)])
    centers = [(float(np.median([p[0] for p in g])), float(np.median([p[1] for p in g]))) for g in groups]
    expected = 10 if chart and str(chart).startswith(('D', 'HD')) else 5
    if len(centers) == 10 and expected == 5 and player:
        centers = centers[:5] if player == 'p1' else centers[5:]
    if len(centers) != expected:
        raise ValueError(f'Found {len(centers)} receptor centers, expected {expected}; provide --layout JSON after reviewing preview.png')
    spacing = np.diff([p[0] for p in centers])
    if np.std(spacing) / np.mean(spacing) > .15 or np.std([p[1] for p in centers]) > height * .025:
        raise ValueError('Receptor geometry is ambiguous; provide --layout JSON')
    middle = float(np.mean([p[0] for p in centers])) / width
    return validate_layout({'method': 'observed_receptor_outlines',
                            'receptor_y': float(np.median([p[1] for p in centers])) / height,
                            'note_y_max': .95, 'combo_roi': [middle - .07, .52, .14, .075],
                            'lanes': [{'x': x / width, 'color': COLORS[i % 5],
                                       'name': f'{i // 5 + 1}:{NAMES[i % 5]}'} for i, (x, _) in enumerate(centers)]})


def bootstrap_digits(record, roi, start, end, layout, directory, width=650, samples=32):
    directory.mkdir(parents=True, exist_ok=True)
    reader, crops, images, metadata, labels = DigitReader(), [], [], [], []
    for i, seconds in enumerate(np.linspace(start + (end-start)*.08, end - (end-start)*.05, samples)):
        path = directory / f'combo-source-{i:02}.png'
        frame = capture_game(record, path, float(seconds), roi)
        rgb = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
        crop = crop_region(rgb, layout['combo_roi'])
        from .play_tracking import glyphs
        if not glyphs(crop):
            continue
        crop_path = directory / f'combo-{i:02}.png'
        cv2.imwrite(str(crop_path), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
        crops.append(crop_path); images.append(crop); metadata.append(frame)
    for result, image, frame in zip(ocr_images(crops, english=True), images, metadata):
        lines = sorted(result['lines'], key=lambda line: line['box'][0])
        tokens = [line['text'].strip() for line in lines if re.fullmatch(r'\d{1,5}', line['text'].strip()) and line['confidence'] >= .5]
        text = ''.join(tokens)
        if text and len(text) <= 5:
            accepted = reader.train(image, text, source=frame['source_pts_seconds'])
            labels.append({'source_pts_seconds': frame['source_pts_seconds'], 'text': text,
                           'accepted': accepted, 'ocr': lines})
            scale = width / roi[2]
            small = cv2.resize(image, (max(1, round(image.shape[1]*scale)), max(1, round(image.shape[0]*scale))), interpolation=cv2.INTER_AREA)
            reader.train(small, text, source=frame['source_pts_seconds'])
    counts = {digit: len(sources) for digit, sources in reader.sources.items()}
    # Keep the full-resolution source examples and their exact PTS for review.
    (directory / 'bootstrap.json').write_text(json.dumps({'frames': metadata, 'template_counts': counts,
                                                         'ocr_images': len(crops), 'labels': labels}, indent=2) + '\n')
    return reader, {'template_counts': counts, 'ocr_images': len(crops),
                    'missing_digits': [digit for digit, n in counts.items() if n < 2]}


def analyze_play(document, segment, output, player=None, layout=None, start=None, duration=None,
                 width=650, display_delay_ms=0):
    record, roi = document['media'], tuple(document['game_roi'])
    source = Path(record['path'])
    before = source.stat()
    if (before.st_size, before.st_mtime_ns) != (record['size_bytes'], record['mtime_ns']):
        raise ValueError('Source changed since timeline analysis; run just auto again')
    start = segment['start_seconds'] if start is None else start
    end = min(segment['end_seconds'], start + duration) if duration is not None else segment['end_seconds']
    if not segment['start_seconds'] <= start < end <= segment['end_seconds']:
        raise ValueError('Requested window must lie inside the gameplay segment')
    output.mkdir(parents=True, exist_ok=False)
    preview = output / 'preview.png'
    stage_file = Path(segment.get('stage_evidence') or '')
    stage = json.loads(stage_file.read_text()) if stage_file.is_file() else {}
    if not isinstance(stage, dict):
        stage = {}
    if stage.get('file') and Path(stage['file']).is_file() and tuple(stage.get('roi', ())) == roi:
        shutil.copyfile(stage['file'], preview)
        calibration = {key: stage.get(key) for key in ('source_pts_seconds', 'playback_seconds', 'requested_seconds', 'roi')}
    else:
        calibration = capture_game(record, preview, min(segment['start_seconds'] + 3, (start+end)/2), roi)
    rgb = cv2.cvtColor(cv2.imread(str(preview)), cv2.COLOR_BGR2RGB)
    if len(segment.get('players', {})) > 1 and (not player or layout is None):
        raise ValueError('Simultaneous players require --player p1 or p2 and a verified --layout')
    try:
        layout = validate_layout(layout) if layout is not None else locate_layout(rgb, segment.get('chart'), player)
    except ValueError as error:
        raise ValueError(f'{error}. Calibration frame: {preview.resolve()}') from error
    (output / 'layout.json').write_text(json.dumps(layout, indent=2) + '\n')
    print('Learning combo digit templates (at most 32 small OCR images)...', flush=True)
    digits, bootstrap = bootstrap_digits(record, roi, start, end, layout, output / 'evidence', width=width)
    combo, tracker, times = ComboTracker(), None, []
    observed, known, previous_mask, previous_read = 0, 0, None, (None, 0.0)
    with (output / 'frames.jsonl').open('w') as trace:
        for pts, playback, image in decode_frames(record, start, end, roi, width):
            if tracker is None:
                tracker = NoteTracker(layout, image.shape[1], image.shape[0])
            notes = tracker.detect(image)
            tracker.update(playback, notes)
            crop = crop_region(image, layout['combo_roi'])
            # Full-resolution examples are resized to the decoded crop before
            # template learning below; glyph normalization removes text scale.
            signature = crop.tobytes()
            if signature != previous_mask:
                previous_read = digits.read(crop)
                previous_mask = signature
            value, confidence = previous_read
            combo.update(playback, value)
            times.append(playback); observed += 1; known += value is not None
            trace.write(json.dumps({'source_pts_seconds': pts, 'playback_seconds': playback,
                                    'notes': notes, 'possible_hold_or_dense_stack': tracker.hold_candidate, 'combo': value, 'combo_confidence': confidence}) + '\n')
            if observed % 300 == 0:
                print(f'  {observed} native frames, {playback-start:.1f}/{end-start:.1f}s, combo readable {known/observed:.0%}', flush=True)
    if not times:
        raise ValueError('No native gameplay frames decoded')
    notes = tracker.finish()
    candidates = associate(notes, combo.events, display_delay=display_delay_ms/1000)
    matches = []
    for match in candidates:
        if any(match['combo_upper_seconds'] >= interval['start_seconds'] - .1
               and match['combo_lower_seconds'] <= interval['end_seconds'] + .1
               for interval in tracker.unsupported_intervals):
            combo.events[match['combo_event']].update(status='excluded', reason='possible_hold_or_dense_stack')
        else:
            matches.append(match)
    after = source.stat()
    if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
        raise ValueError('Source changed during play analysis')
    interval = float(np.median(np.diff(times))) if len(times) > 1 else None
    return {'schema_version': 1, 'play_analysis_version': VERSION, 'media': record,
            'participant_slots': sorted(segment.get('players',{})), 'song': segment.get('song'), 'chart': segment.get('chart'), 'player': player,
            'start_seconds': start, 'end_seconds': end, 'game_roi': list(roi), 'layout': layout,
            'calibration': calibration, 'analysis_width': width, 'analysis_height': round(width*roi[3]/roi[2]),
            'frame_count': observed, 'median_frame_interval_seconds': interval,
            'combo_readable_fraction': known/observed, 'bootstrap': bootstrap,
            'display_delay_correction_ms': display_delay_ms, 'notes': notes,
            'combo_events': combo.events, 'matches': matches, 'unsupported_intervals': tracker.unsupported_intervals,
            'result_reference': result_reference(segment, player),
            'coverage': {'visible_note_heads': sum(n['status'] == 'estimated' for n in notes),
                         'timed_note_heads': len(matches),
                         'matched_combo_updates': len({m['combo_event'] for m in matches}),
                         'observed_combo_updates': sum(e['delta'] > 0 for e in combo.events)},
            'excluded_notes': dict(Counter(note['reason'] for note in notes if note['status'] == 'excluded')),
            'limitations': ['Combo display updates are a proxy, not measured physical switch input.',
                            'Display/input latency is unknown unless externally calibrated.',
                            'Chart reconstruction covers visible supported-color note heads, not an authoritative chart file.',
                            'Coverage is partial. Result judgments include hold ticks and are not a visible note-head count.',
                            'Chords share a bracket only when the visible row size equals the counter increment.',
                            'Holds, rolls, unresolved counter jumps, ambiguous associations and nonlinear trajectories are excluded.',
                            'No missed press is inferred from a combo reset or an unreadable counter.']}


def run(source, segment_number=1, force=False, **options):
    directory = LOCAL_DATA / source_id(source)
    analysis = directory / 'analysis/analysis.json'
    if not analysis.is_file():
        raise ValueError('Run just auto SOURCE first; play analysis never starts metadata OCR implicitly')
    document = json.loads(analysis.read_text())
    segments = document.get('segments', [])
    if not 1 <= segment_number <= len(segments):
        raise ValueError(f'--segment must be between 1 and {len(segments)}')
    root = directory / 'play'; root.mkdir(exist_ok=True)
    with (root / f'.segment-{segment_number:03}.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('This play is already being analyzed') from error
        final = root / f'segment-{segment_number:03}'
        previous = final / 'analysis.json'
        expected_start = options.get('start') if options.get('start') is not None else segments[segment_number-1]['start_seconds']
        expected_end = min(segments[segment_number-1]['end_seconds'], expected_start + options['duration']) if options.get('duration') is not None else segments[segment_number-1]['end_seconds']
        if previous.is_file() and not force:
            cached = json.loads(previous.read_text())
            stat = Path(document['media']['path']).stat()
            same_source = (stat.st_size, stat.st_mtime_ns) == (cached['media']['size_bytes'], cached['media']['mtime_ns']) and cached['media']['path'] == document['media']['path']
            same_settings = (cached.get('play_analysis_version') == VERSION and cached['start_seconds'] == expected_start
                             and cached['end_seconds'] == expected_end and cached['game_roi'] == document['game_roi']
                             and cached['analysis_width'] == options.get('width',650)
                             and cached.get('player') == options.get('player')
                             and cached.get('song') == segments[segment_number-1].get('song')
                             and cached.get('chart') == segments[segment_number-1].get('chart')
                             and cached.get('participant_slots',[]) == sorted(segments[segment_number-1].get('players',{}))
                             and cached.get('display_delay_correction_ms',0) == options.get('display_delay_ms',0)
                             and (options.get('layout') is None or cached['layout'] == options['layout']))
            if same_source and same_settings:
                from .play_report import write_report
                write_report(cached, final / 'report.html', final)
                print('Reusing saved native-frame play analysis; no decoding or OCR.')
                print(final / 'report.html')
                return final / 'report.html'
        pending = root / f'segment-{segment_number:03}.build-{uuid.uuid4().hex[:8]}'
        result = analyze_play(document, segments[segment_number-1], pending, **options)
        result['segment_number'] = segment_number
        (pending / 'analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        from .play_report import write_report
        write_report(result, pending / 'report.html', final)
        from .storage import relocate_evidence
        relocate_evidence(pending, final)
        backup = root / f'segment-{segment_number:03}.previous-{uuid.uuid4().hex[:8]}'
        if final.exists():
            final.rename(backup)
        try:
            pending.rename(final)
        except OSError:
            if backup.exists() and not final.exists():
                backup.rename(final)
            raise
        print(final / 'report.html')
        return final / 'report.html'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--force', action='store_true', help='Rebuild play evidence instead of reusing a matching cache')
    parser.add_argument('--segment', type=int, default=1)
    parser.add_argument('--player', choices=('p1', 'p2'))
    parser.add_argument('--layout', type=Path)
    parser.add_argument('--start', type=float, help='Absolute local playback seconds inside the segment')
    parser.add_argument('--duration', type=float)
    parser.add_argument('--width', type=int, default=650)
    parser.add_argument('--display-delay-ms', type=float, default=0)
    args = parser.parse_args()
    if not 320 <= args.width <= 1300:
        parser.error('--width must be 320..1300')
    if any(value is not None and (not math.isfinite(value) or value < 0) for value in (args.start, args.duration)):
        parser.error('Start/duration must be finite and nonnegative')
    if not math.isfinite(args.display_delay_ms) or abs(args.display_delay_ms) > 500:
        parser.error('--display-delay-ms must be finite and between -500 and 500')
    try:
        run(args.source, args.segment, force=args.force, player=args.player,
            layout=json.loads(args.layout.read_text()) if args.layout else None,
            start=args.start, duration=args.duration, width=args.width, display_delay_ms=args.display_delay_ms)
    except (ValueError, OSError, cv2.error) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
