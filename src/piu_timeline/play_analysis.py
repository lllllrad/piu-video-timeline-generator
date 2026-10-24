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
from .play_judgments import augment_judgments, cache_current as judgment_cache_current

VERSION = 11
FRAME_OBSERVATION_VERSION = 4
NATIVE_FRAME_FORMAT = {'schema':1,'notes':'normalized_lane_centers','time':'source_pts_and_playback'}
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
    for name in ('combo_roi','judgment_roi'):
        if name=='judgment_roi' and name not in layout:
            continue
        region=layout.get(name,[])
        if len(region)!=4 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in region):
            raise ValueError(f'{name} needs four finite fractions')
        x,y,w,h=region
        if not (0<=x<x+w<=1 and 0<=y<y+h<=1):
            raise ValueError(f'{name} must fit inside the game image')
    return layout


def receptor_centers(rgb):
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
    return centers


def locate_layout(rgb, chart, player=None):
    height, width = rgb.shape[:2]
    centers = receptor_centers(rgb)
    expected = (10 if str(chart).startswith(('D', 'HD')) else 5) if chart else None
    if len(centers) == 10 and expected == 5 and player:
        centers = centers[:5] if player == 'p1' else centers[5:]
    if len(centers) not in ((expected,) if expected else (5, 10)):
        raise ValueError(f'Found {len(centers)} receptor centers, expected {expected or '5 or 10'}; provide --layout JSON after reviewing preview.png')
    spacing = np.diff([p[0] for p in centers])
    if np.std(spacing) / np.mean(spacing) > .15 or np.std([p[1] for p in centers]) > height * .025:
        raise ValueError('Receptor geometry is ambiguous; provide --layout JSON')
    middle = float(np.mean([p[0] for p in centers])) / width
    return validate_layout({'method': 'observed_receptor_outlines',
                            'receptor_y': float(np.median([p[1] for p in centers])) / height,
                            'note_y_max': .95, 'combo_roi': [middle - .07, .52, .14, .075],
                            'lanes': [{'x': x / width, 'color': COLORS[i % 5],
                                       'name': f'{i // 5 + 1}:{NAMES[i % 5]}'} for i, (x, _) in enumerate(centers)]})


def recover_layout(record, roi, segment, preview, rgb, calibration, player=None):
    """Require agreement across source frames; recover receivers hidden by flashes."""
    candidates, seen, images, observations = [], [], [rgb], [dict(calibration)]
    expected = (10 if str(segment['chart']).startswith(('D','HD')) else 5) if segment.get('chart') else None
    for saved_path in sorted(preview.parent.parent.glob('segment-*/analysis.json')):
        if not re.fullmatch(r'segment-\d{3}', saved_path.parent.name):
            continue
        saved = json.loads(saved_path.read_text())
        if saved.get('media') != record or saved.get('game_roi') != list(roi):
            continue
        candidate = saved.get('layout')
        if candidate and (expected is None or len(candidate['lanes']) == expected):
            candidates.append((candidate, {'source_pts_seconds': None, 'shared_from': str(saved_path)}))

    def observe(image, observation):
        centers = receptor_centers(image)
        seen.append((centers, observation))
        try:
            candidates.append((locate_layout(image, segment.get('chart'), player), observation))
        except ValueError:
            pass
        height,width = image.shape[:2]
        for candidate,source in candidates:
            xs = [lane['x'] for lane in candidate['lanes']]
            for points,other_source in seen:
                if source.get('source_pts_seconds') == other_source.get('source_pts_seconds'):
                    continue
                matched = {min(range(len(xs)),key=lambda i:abs(xs[i]-x/width))
                           for x,y in points if abs(y/height-candidate['receptor_y'])<.012
                           and min(abs(x/width-cx) for cx in xs)<.008}
                if len(matched)>=min(4,len(xs)) and max(matched)-min(matched)>=len(xs)//2:
                    result = dict(candidate)
                    result['method'] = 'corroborated_shared_geometry' if source.get('shared_from') else 'corroborated_receptor_outlines'
                    if source.get('shared_from'):
                        calibration['geometry_reference'] = source['shared_from']
                    return result
        return None

    layout = observe(rgb, calibration)
    if layout is not None:
        calibration['supporting_frames'] = observations
        return layout
    directory = preview.parent / 'calibration'; directory.mkdir(exist_ok=True)
    offsets = (.5, 1.5, 3, 5, 8, 13, 21, 34)
    for index, offset in enumerate(offsets):
        seconds = min(segment['start_seconds'] + offset, segment['end_seconds'] - .1)
        path = directory / f'source-{index:02}.png'
        observation = capture_game(record, path, seconds, roi)
        image = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
        images.append(image); observations.append(observation)
        layout = observe(image, observation)
        if layout is not None:
            calibration['supporting_frames'] = observations
            return layout
    # Flash positions move while the static receiver outlines stay in place.
    median = np.median(np.stack(images), axis=0).astype('uint8')
    layout = locate_layout(median, segment.get('chart'), player)
    layout['method'] = 'temporal_median_receptor_outlines'
    cv2.imwrite(str(directory / 'median.png'), cv2.cvtColor(median, cv2.COLOR_RGB2BGR))
    calibration['supporting_frames'] = observations
    return layout


def previous_digit_reader(directory, record):
    """Reuse font examples, never counter values or timestamps from another play."""
    root = directory.parent.parent
    for previous in sorted(root.glob('segment-*/analysis.json')):
        if not re.fullmatch(r'segment-\d{3}', previous.parent.name):
            continue
        saved = json.loads(previous.read_text())
        if any(saved.get('media', {}).get(key) != record.get(key) for key in ('path', 'size_bytes', 'mtime_ns')):
            continue
        bank = previous.parent / 'evidence/digit-templates.npz'
        if bank.is_file():
            reader = DigitReader.load(bank)
            imported = directory / 'imported-digit-templates.npz'
            shutil.copyfile(bank, imported)
            return reader, {'template_archive': str(imported), 'source_media': record['path'],
                            'source_pts_by_digit': {digit: sorted(times) for digit,times in reader.sources.items()}}
        evidence = previous.parent / 'evidence/bootstrap.json'
        if not evidence.is_file():
            continue
        bootstrap = json.loads(evidence.read_text())
        labels = {label['source_pts_seconds']: label['text'] for label in bootstrap.get('labels', []) if label['accepted']}
        reader = DigitReader()
        for frame in bootstrap.get('frames', []):
            text = labels.get(frame['source_pts_seconds'])
            if text is None or not Path(frame['file']).is_file():
                continue
            image = cv2.cvtColor(cv2.imread(frame['file']), cv2.COLOR_BGR2RGB)
            crop = crop_region(image, saved['layout']['combo_roi'])
            reader.train(crop, text, source=frame['source_pts_seconds'])
            scale = saved['analysis_width'] / image.shape[1]
            reader.train(cv2.resize(crop, (round(crop.shape[1]*scale), round(crop.shape[0]*scale))),
                         text, source=frame['source_pts_seconds'])
        if all(len(sources) >= 2 for sources in reader.sources.values()):
            return reader, {'source_media': record['path'], 'ocr_labels': bootstrap.get('labels', []),
                            'source_pts_by_digit': {digit: sorted(times) for digit,times in reader.sources.items()}}
    return DigitReader(), None


def bootstrap_digits(record, roi, start, end, layout, directory, width=650, samples=32):
    directory.mkdir(parents=True, exist_ok=True)
    reader, reused_from = previous_digit_reader(directory, record)
    crops, images, metadata, labels = [], [], [], []
    if reused_from:
        samples = min(samples, 8)
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
    unknown = [i for i,image in enumerate(images) if reader.read(image)[0] is None]
    for result, i in zip(ocr_images([crops[i] for i in unknown], english=True) if unknown else [], unknown):
        image, frame = images[i], metadata[i]
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
                                                         'ocr_images': len(unknown), 'labels': labels, 'reused_from': reused_from}, indent=2) + '\n')
    reader.save(directory / 'digit-templates.npz')
    return reader, {'template_counts': counts, 'ocr_images': len(unknown), 'reused_from': reused_from,
                    'missing_digits': [digit for digit, n in counts.items() if n < 2]}


def resolve_timing(tracker, combo, display_delay_ms):
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
    return {'notes': notes, 'combo_events': combo.events, 'matches': matches,
            'unsupported_intervals': tracker.unsupported_intervals,
            'coverage': {'visible_note_heads': sum(n['status'] == 'estimated' for n in notes),
                         'timed_note_heads': len(matches),
                         'matched_combo_updates': len({m['combo_event'] for m in matches}),
                         'observed_combo_updates': sum(e['delta'] > 0 for e in combo.events)},
            'excluded_notes': dict(Counter(n['reason'] for n in notes if n['status'] == 'excluded'))}


def refresh_counter_observations(cached, output):
    """Decode only the small counter region; preserve all note observations."""
    from itertools import zip_longest
    digits = DigitReader.load(output / 'evidence/digit-templates.npz')
    trace = output / 'frames.jsonl'
    base = output / 'frames.base.jsonl'
    if not base.is_file():
        baseline = trace
        # Older refinement output did not keep a baseline sidecar. Recover its
        # immutable pre-refinement trace from the retained atomic-build backup.
        if cached.get('frame_observation_version',2) >= 3:
            number = cached['segment_number']
            for previous in sorted(output.parent.glob(f'segment-{number:03}.previous-*/analysis.json')):
                saved = json.loads(previous.read_text())
                if (saved.get('frame_observation_version',2) == 2
                        and all(saved.get(key)==cached.get(key) for key in
                                ('media','start_seconds','end_seconds','analysis_width','layout'))):
                    baseline = previous.parent / 'frames.jsonl'
                    break
        shutil.copyfile(baseline,base)
    frames = [json.loads(line) for line in base.open()]
    prior,following = [],[None]*len(frames)
    known_before = known_after = None
    for frame in frames:
        prior.append(known_before)
        if frame['combo'] is not None:
            known_before = frame['combo'],frame['playback_seconds']
    for i in reversed(range(len(frames))):
        following[i] = known_after
        if frames[i]['combo'] is not None:
            known_after = frames[i]['combo'],frames[i]['playback_seconds']
    combo,known,count = ComboTracker(),0,0
    updated = output / 'frames.counter-update.jsonl'
    crops = decode_frames(cached['media'],cached['start_seconds'],cached['end_seconds'],
                          cached['game_roi'],cached['analysis_width'],region=cached['layout']['combo_roi'])
    with updated.open('w') as target:
        for i,(frame,decoded) in enumerate(zip_longest(frames,crops)):
            if frame is None or decoded is None:
                raise ValueError('Counter refresh frame count differs from saved native observations')
            pts,seconds,crop = decoded
            if abs(frame['source_pts_seconds']-pts)>1e-6 or abs(frame['playback_seconds']-seconds)>1e-6:
                raise ValueError('Counter refresh PTS differs from saved note observations')
            value,confidence = frame['combo'],frame['combo_confidence']
            mode = frame.get('combo_read_mode','unreadable')
            if value is None and prior[i] is not None and following[i] is not None:
                before,before_time = prior[i];after,after_time = following[i]
                if 0<=after-before<=10 and after_time-before_time<=.25:
                    candidate,score = digits.read(crop,expected=before)
                    if candidate is not None and before<=candidate<=after:
                        value,confidence,mode = candidate,score,digits.last_mode
                        frame['combo_recovered'] = True
            combo.update(seconds,value)
            frame.update(combo=value,combo_confidence=confidence,combo_read_mode=mode)
            target.write(json.dumps(frame)+'\n')
            known += value is not None;count += 1
    updated.replace(trace)
    return {'combo_readable_fraction':known/count,'refreshed_counter_only':True}


def refit_saved(cached, previous, output, segment, display_delay_ms):
    """Rerun trajectories and row alignment using identical source observations."""
    shutil.copytree(previous, output)
    from .storage import relocate_evidence
    relocate_evidence(output,output,source=previous)
    cached=json.loads((output/'analysis.json').read_text())
    refreshed = {}
    if cached.get('frame_observation_version',2) < FRAME_OBSERVATION_VERSION:
        print('Refreshing counter crops; preserving saved note observations, no OCR.',flush=True)
        refreshed = refresh_counter_observations(cached,output)
    tracker = NoteTracker(cached['layout'], cached['analysis_width'], cached['analysis_height'])
    combo, count, last = ComboTracker(), 0, None
    for line in (output / 'frames.jsonl').open():
        frame = json.loads(line)
        try:
            if (not math.isfinite(frame['source_pts_seconds']) or not math.isfinite(frame['playback_seconds'])
                    or not isinstance(frame['notes'],list)
                    or frame['combo'] is not None and (type(frame['combo']) is not int or frame['combo']<0)
                    or any(type(note['lane']) is not int or not 0<=note['lane']<len(cached['layout']['lanes'])
                           or not all(isinstance(note[key],(int,float)) and math.isfinite(note[key]) and 0<=note[key]<=1 for key in ('x','y'))
                           for note in frame['notes'])):
                raise ValueError('Unsupported saved native observation format')
        except (KeyError,TypeError) as error:
            raise ValueError('Unsupported saved native observation format') from error
        seconds = frame['playback_seconds']
        if last is not None and seconds <= last:
            raise ValueError('Saved observation timestamps are not increasing')
        last = seconds; count += 1
        tracker.hold_candidate = frame.get('possible_hold_or_dense_stack', False)
        tracker.update(seconds, frame['notes']); combo.update(seconds, frame['combo'])
    if count != cached['frame_count']:
        raise ValueError('Saved native-frame observations are incomplete')
    result = {**cached, **refreshed, **resolve_timing(tracker, combo, display_delay_ms),
              'play_analysis_version': VERSION, 'frame_observation_version': FRAME_OBSERVATION_VERSION,
              'native_frame_format':NATIVE_FRAME_FORMAT,
              'song':segment.get('song'),'chart':segment.get('chart'),
              'participant_slots':sorted(segment.get('players',{})),
              'display_delay_correction_ms': display_delay_ms, 'reused_native_observations': True,
              'result_reference': result_reference(segment, cached.get('player'))}
    print('Refitting saved note observations; no OCR.', flush=True)
    return result


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
        layout = validate_layout(layout) if layout is not None else recover_layout(record, roi, segment, preview, rgb, calibration, player)
    except ValueError as error:
        raise ValueError(f'{error}. Calibration frame: {preview.resolve()}') from error
    (output / 'layout.json').write_text(json.dumps(layout, indent=2) + '\n')
    print('Learning combo digit templates (at most 32 small OCR images)...', flush=True)
    (output / 'evidence').mkdir(exist_ok=True)
    digits, bootstrap = bootstrap_digits(record, roi, start, end, layout, output / 'evidence', width=width)
    combo, tracker, times = ComboTracker(), None, []
    observed, known, previous_mask, previous_read = 0, 0, None, (None, 0.0)
    last_adapted = None
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
                expected = combo.stable if combo.last_seen is not None and playback-combo.last_seen <= .15 else None
                previous_read = digits.read(crop, expected=expected, recover=False)
                previous_mask = signature
            value, confidence = previous_read
            combo.update(playback, value)
            if value is not None and value == combo.stable and value != last_adapted and confidence >= .88:
                digits.train(crop, value, source=pts)
                last_adapted = value
            times.append(playback); observed += 1; known += value is not None
            trace.write(json.dumps({'source_pts_seconds': pts, 'playback_seconds': playback,
                                    'notes': notes, 'possible_hold_or_dense_stack': tracker.hold_candidate, 'combo': value, 'combo_confidence': confidence, 'combo_read_mode': digits.last_mode}) + '\n')
            if observed % 300 == 0:
                print(f'  {observed} native frames, {playback-start:.1f}/{end-start:.1f}s, combo readable {known/observed:.0%}', flush=True)
    if not times:
        raise ValueError('No native gameplay frames decoded')
    digits.save(output / 'evidence/digit-templates.npz')
    refinement = {}
    if known:
        refinement = refresh_counter_observations(
            {'media': record, 'start_seconds': start, 'end_seconds': end, 'game_roi': list(roi),
             'analysis_width': width, 'layout': layout, 'frame_observation_version': 2}, output)
        combo = ComboTracker()
        for line in (output / 'frames.jsonl').open():
            frame = json.loads(line)
            combo.update(frame['playback_seconds'],frame['combo'])
        known = round(refinement['combo_readable_fraction']*observed)
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
            **refinement,
            'display_delay_correction_ms': display_delay_ms,
            'frame_observation_version': FRAME_OBSERVATION_VERSION,
            'native_frame_format':NATIVE_FRAME_FORMAT,
            **resolve_timing(tracker, combo, display_delay_ms),
            'result_reference': result_reference(segment, player),
            'limitations': ['Combo display updates are a proxy, not measured physical switch input.',
                            'Display/input latency is unknown unless externally calibrated.',
                            'Chart reconstruction covers visible supported-color note heads, not an authoritative chart file.',
                            'Coverage is partial. Result judgments include hold ticks and are not a visible note-head count.',
                            'Chords share one judged-row bracket; skipped counter values retain an aggregate interval.',
                            'Holds, rolls, unresolved counter jumps, ambiguous associations and nonlinear trajectories are excluded.',
                            'No missed press is inferred from a combo reset or an unreadable counter.']}


def observation_settings_match(cached, document, segment, start, end, options):
    chart=segment.get('chart') or ''
    lanes=10 if re.match(r'^(?:HD|D)\d',chart) else 5 if re.match(r'^(?:S\d|VERY HARD )',chart) else None
    return (cached.get('media')==document.get('media') and cached.get('start_seconds')==start
            and cached.get('end_seconds')==end and cached.get('game_roi')==document.get('game_roi')
            and cached.get('analysis_width')==options.get('width',650)
            and cached.get('player')==options.get('player')
            and cached.get('participant_slots',[])==sorted(segment.get('players',{}))
            and (lanes is None or len(cached.get('layout',{}).get('lanes',[]))==lanes)
            and (options.get('layout') is None or cached.get('layout')==options['layout']))


def cache_header(path):
    """Read acquisition metadata without loading every saved note trajectory."""
    parts=[]
    with path.open() as stream:
        for line in stream:
            if line.startswith('  "notes":'):
                return json.loads(''.join(parts).rstrip().rstrip(',')+'}')
            parts.append(line)
    return json.loads(''.join(parts))


def find_saved_observations(root, final, document, segment, start, end, options):
    # Backups are immutable snapshots, so another segment can reuse them safely
    # while the numbered presentation directories are being updated.
    paths=[p for p in root.glob('segment-*.previous-*/analysis.json') if p.parent!=final]
    for path in sorted(paths,key=lambda p:p.stat().st_mtime_ns,reverse=True):
        try:
            cached=cache_header(path)
            if (observation_settings_match(cached,document,segment,start,end,options)
                    and (path.parent/'frames.jsonl').is_file()
                    and cached.get('native_frame_format',NATIVE_FRAME_FORMAT)==NATIVE_FRAME_FORMAT):
                cached=json.loads(path.read_text())
                if (observation_settings_match(cached,document,segment,start,end,options)
                        and cached.get('native_frame_format',NATIVE_FRAME_FORMAT)==NATIVE_FRAME_FORMAT
                        and all(key in cached for key in ('layout','analysis_height','frame_count'))):
                    return cached,path.parent
        except (OSError,ValueError):
            continue
    return None


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
        can_refit = False
        donor=final
        if previous.is_file() and not force:
            cached = json.loads(previous.read_text())
            stat = Path(document['media']['path']).stat()
            same_source = ((stat.st_size, stat.st_mtime_ns) == (cached['media']['size_bytes'], cached['media']['mtime_ns'])
                           and cached['media'] == document['media'])
            same_settings = observation_settings_match(cached,document,segments[segment_number-1],expected_start,expected_end,options)
            can_refit = (same_source and same_settings
                         and cached.get('native_frame_format',NATIVE_FRAME_FORMAT)==NATIVE_FRAME_FORMAT
                         and all(key in cached for key in ('layout','analysis_height','frame_count'))
                         and (final / 'frames.jsonl').is_file())
            if (same_source and same_settings and cached.get('play_analysis_version') == VERSION
                    and cached.get('song')==segments[segment_number-1].get('song')
                    and cached.get('chart')==segments[segment_number-1].get('chart')
                    and cached.get('display_delay_correction_ms',0) == options.get('display_delay_ms',0)
                    and cached.get('result_reference') == result_reference(segments[segment_number-1],options.get('player'))
                    and judgment_cache_current(cached,root,final)):
                from .play_report import write_report
                from .play_holds import augment_holds
                previous_holds = cached.get('hold_analysis')
                cached = augment_holds(cached, final)
                write_report(cached, final / 'report.html', final)
                if cached.get('hold_analysis') != previous_holds:
                    updated = final / 'analysis.holds-build.json'
                    updated.write_text(json.dumps(cached, ensure_ascii=False, indent=2) + '\n')
                    updated.replace(previous)
                print('Reusing saved note/judgment analysis and compatible long-note evidence; no OCR.')
                print(final / 'report.html')
                return final / 'report.html'
        if not force and not can_refit and document.get('media'):
            saved=find_saved_observations(root,final,document,segments[segment_number-1],expected_start,expected_end,options)
            if saved:
                cached,donor=saved
                stat=Path(document['media']['path']).stat()
                can_refit=(stat.st_size,stat.st_mtime_ns)==(cached['media']['size_bytes'],cached['media']['mtime_ns'])
        pending = root / f'segment-{segment_number:03}.build-{uuid.uuid4().hex[:8]}'
        if can_refit:
            result = refit_saved(cached, donor, pending, segments[segment_number-1], options.get('display_delay_ms',0))
        else:
            result = analyze_play(document, segments[segment_number-1], pending, **options)
        result = augment_judgments(result,pending)
        from .play_holds import augment_holds
        result = augment_holds(result,pending)
        stat = Path(document['media']['path']).stat()
        if (stat.st_size,stat.st_mtime_ns) != (result['media']['size_bytes'],result['media']['mtime_ns']):
            raise ValueError('Source changed during play analysis')
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


def run_all(source, **options):
    directory = LOCAL_DATA / source_id(source)
    analysis = directory / 'analysis/analysis.json'
    if not analysis.is_file():
        raise ValueError('Run just auto SOURCE first')
    document = json.loads(analysis.read_text())
    failed = []
    for number in range(1, len(document['segments'])+1):
        print(f'Analyzing play {number}/{len(document["segments"])}...', flush=True)
        try:
            run(source, number, **options)
        except (ValueError, OSError, cv2.error) as error:
            failed.append(number)
            print(f'Play {number} failed: {error}', flush=True)
    root = directory / 'play'; root.mkdir(exist_ok=True)
    from .play_report import write_index
    index = write_index(document, root)
    print(index)
    if failed:
        raise ValueError(f'Failed plays: {failed}; see completed reports at {index}')
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--force', action='store_true', help='Rebuild play evidence instead of reusing a matching cache')
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--segment', type=int, default=1)
    selection.add_argument('--all', action='store_true', help='Analyze every saved play and write an HTML index')
    parser.add_argument('--player', choices=('p1', 'p2'))
    parser.add_argument('--layout', type=Path)
    parser.add_argument('--start', type=float, help='Absolute local playback seconds inside the segment')
    parser.add_argument('--duration', type=float)
    parser.add_argument('--width', type=int, default=650)
    parser.add_argument('--display-delay-ms', type=float, default=0)
    args = parser.parse_args()
    if args.all and (args.start is not None or args.duration is not None):
        parser.error('--all cannot be combined with --start or --duration')
    if not 320 <= args.width <= 1300:
        parser.error('--width must be 320..1300')
    if any(value is not None and (not math.isfinite(value) or value < 0) for value in (args.start, args.duration)):
        parser.error('Start/duration must be finite and nonnegative')
    if not math.isfinite(args.display_delay_ms) or abs(args.display_delay_ms) > 500:
        parser.error('--display-delay-ms must be finite and between -500 and 500')
    try:
        options = dict(force=args.force, player=args.player,
                       layout=json.loads(args.layout.read_text()) if args.layout else None,
                       start=args.start, duration=args.duration, width=args.width, display_delay_ms=args.display_delay_ms)
        if args.all:
            run_all(args.source, **options)
        else:
            run(args.source, args.segment, **options)
    except (ValueError, OSError, cv2.error) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
