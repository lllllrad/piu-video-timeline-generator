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

from piu_timeline.vision.ocr import ocr_images
from piu_timeline.play.frames import decode_frames, crop_region, TIME_EPSILON
from piu_timeline.play.tracking import NoteTracker, DigitReader, ComboTracker, associate
from piu_timeline.metadata.recognition import capture_game
from piu_timeline.workflow import LOCAL_DATA, source_id
from piu_timeline.play.judgments import augment_judgments, cache_current as judgment_cache_current, observations_current as judgment_observations_current

from piu_timeline.play.layout import (validate_layout, receptor_centers, locate_layout,
                                     combine_receptor_observations, recover_layout)
from piu_timeline.play.fonts import previous_digit_reader, bootstrap_digits

VERSION = 18
TIMING_FORMAT = {'schema':1,'counter_revision':4,'time_epsilon_seconds':TIME_EPSILON}
FRAME_OBSERVATION_VERSION = 4
NATIVE_FRAME_FORMAT = {'schema':1,'notes':'normalized_lane_centers','time':'source_pts_and_playback'}



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


def resolve_timing(tracker, combo, display_delay_ms):
    notes = tracker.finish()
    from piu_timeline.play.counter_refinement import refine_events, refinement_constraints
    original = combo.events
    combo.events = refine_events(original,combo.observations)
    constraints = None
    if len(combo.events) != len(original):
        baseline = associate(notes,[dict(e) for e in original],display_delay=display_delay_ms/1000)
        constraints = refinement_constraints(notes,original,baseline,combo.events)
    candidates = associate(notes,combo.events,display_delay=display_delay_ms/1000,event_note_constraints=constraints)
    matches, deferred = [], []
    for match in candidates:
        if any(match['combo_upper_seconds'] >= interval['start_seconds'] - .1
               and match['combo_lower_seconds'] <= interval['end_seconds'] + .1
               for interval in tracker.unsupported_intervals):
            combo.events[match['combo_event']].update(status='excluded', reason='possible_hold_or_dense_stack')
            deferred.append({**match, 'deferred_reason': 'possible_hold_or_dense_stack'})
        else:
            matches.append(match)
    return {'timing_format': TIMING_FORMAT, 'notes': notes, **({'scroll_motion': tracker.motion.evidence()} if hasattr(tracker, 'motion') else {}),
            'combo_events': combo.events, 'matches': matches, 'deferred_matches': deferred,
            'unsupported_intervals': tracker.unsupported_intervals,
            'coverage': {'visible_note_heads': sum(n['status'] == 'estimated' for n in notes),
                         'timed_note_heads': len(matches),
                         'matched_combo_updates': len({m['combo_event'] for m in matches}),
                         'observed_combo_updates': sum(e['delta'] > 0 for e in combo.events)},
            'excluded_notes': dict(Counter(n['reason'] for n in notes if n['status'] == 'excluded'))}


def refresh_counter_observations(cached, output, replace_font=False):
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
            if replace_font:
                expected = combo.stable if combo.last_seen is not None and seconds-combo.last_seen <= .15 else None
                candidate,score = digits.read(crop,expected=expected)
                frame['combo_before_font_validation'] = frame['combo']
                value,confidence,mode = candidate,score,digits.last_mode
            elif value is None and prior[i] is not None and following[i] is not None:
                before,before_time = prior[i];after,after_time = following[i]
                if 0<=after-before<=10 and after_time-before_time<=.25:
                    candidate,score = digits.read(crop,expected=before)
                    if candidate is not None and before<=candidate<=after:
                        value,confidence,mode = candidate,score,digits.last_mode
                        frame['combo_recovered'] = True
            combo.update(seconds,value,confidence,mode,pts)
            frame.update(combo=value,combo_confidence=confidence,combo_read_mode=mode)
            target.write(json.dumps(frame)+'\n')
            known += value is not None;count += 1
    updated.replace(trace)
    return {'combo_readable_fraction':known/count,'refreshed_counter_only':True}


def refit_saved(cached, previous, output, segment, display_delay_ms):
    """Rerun trajectories and row alignment using identical source observations."""
    shutil.copytree(previous, output)
    from piu_timeline.storage import relocate_evidence
    relocate_evidence(output,output,source=previous)
    cached=json.loads((output/'analysis.json').read_text())
    refreshed = {}
    from piu_timeline.play.fonts import refresh_reader
    replaced_font = refresh_reader(cached, output, LOCAL_DATA)
    if replaced_font or cached.get('frame_observation_version',2) < FRAME_OBSERVATION_VERSION:
        print('Refreshing counter crops; preserving saved note observations, no OCR.',flush=True)
        refreshed = refresh_counter_observations(cached,output,replace_font=replaced_font)
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
        tracker.update(seconds, frame['notes'], frame['source_pts_seconds']); combo.update(seconds,frame['combo'],frame.get('combo_confidence'),
                          frame.get('combo_read_mode'),frame['source_pts_seconds'])
    if count != cached['frame_count']:
        raise ValueError('Saved native-frame observations are incomplete')
    result = {**cached, **refreshed, **resolve_timing(tracker, combo, display_delay_ms),
              'play_analysis_version': VERSION, 'frame_observation_version': FRAME_OBSERVATION_VERSION,
              'native_frame_format':NATIVE_FRAME_FORMAT,
              'song':segment.get('song'),'chart':segment.get('chart'),
              'chart_identity':segment.get('chart_identity'),
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
            tracker.update(playback, notes, pts)
            crop = crop_region(image, layout['combo_roi'])
            # Full-resolution examples are resized to the decoded crop before
            # template learning below; glyph normalization removes text scale.
            signature = crop.tobytes()
            if signature != previous_mask:
                expected = combo.stable if combo.last_seen is not None and playback-combo.last_seen <= .15 else None
                previous_read = digits.read(crop, expected=expected, recover=False)
                previous_mask = signature
            value, confidence = previous_read
            combo.update(playback,value,confidence,digits.last_mode,pts)
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
            combo.update(frame['playback_seconds'],frame['combo'],frame.get('combo_confidence'),
                         frame.get('combo_read_mode'),frame['source_pts_seconds'])
        known = round(refinement['combo_readable_fraction']*observed)
    after = source.stat()
    if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
        raise ValueError('Source changed during play analysis')
    interval = float(np.median(np.diff(times))) if len(times) > 1 else None
    return {'schema_version': 1, 'play_analysis_version': VERSION, 'media': record,
            'participant_slots': sorted(segment.get('players',{})), 'song': segment.get('song'), 'chart': segment.get('chart'), 'player': player,
            'chart_identity': segment.get('chart_identity'),
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
    from piu_timeline.play.fonts import cache_current as digit_cache_current
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
                    and cached.get('timing_format') == TIMING_FORMAT
                    and cached.get('song')==segments[segment_number-1].get('song')
                    and cached.get('chart')==segments[segment_number-1].get('chart')
                    and cached.get('chart_identity')==segments[segment_number-1].get('chart_identity')
                    and cached.get('display_delay_correction_ms',0) == options.get('display_delay_ms',0)
                    and cached.get('result_reference') == result_reference(segments[segment_number-1],options.get('player'))
                    and digit_cache_current(cached,final,LOCAL_DATA)
                    and ((judgments_current := judgment_cache_current(cached,root,final))
                         or judgment_observations_current(cached,root,final))):
                from piu_timeline.play.report import write_report
                from piu_timeline.play.holds.analysis import augment_holds
                previous_judgments = cached.get('judgment_cache')
                if not judgments_current:
                    cached = augment_judgments(cached,final)
                previous_holds = cached.get('hold_analysis')
                previous_channels = cached.get('visual_channels')
                cached = augment_holds(cached, final)
                write_report(cached, final / 'report.html', final)
                if (cached.get('judgment_cache') != previous_judgments or cached.get('hold_analysis') != previous_holds
                        or cached.get('visual_channels') != previous_channels):
                    updated = final / 'analysis.refresh-build.json'
                    updated.write_text(json.dumps(cached, ensure_ascii=False, indent=2) + '\n')
                    updated.replace(previous)
                print('Reusing saved note trajectories and compatible word/long-note evidence; no OCR.')
                from piu_timeline.charts.data import auto_register
                auto_register(cached, final)
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
        from piu_timeline.play.holds.analysis import augment_holds
        result = augment_holds(result,pending)
        stat = Path(document['media']['path']).stat()
        if (stat.st_size,stat.st_mtime_ns) != (result['media']['size_bytes'],result['media']['mtime_ns']):
            raise ValueError('Source changed during play analysis')
        result['segment_number'] = segment_number
        (pending / 'analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        from piu_timeline.play.report import write_report
        write_report(result, pending / 'report.html', final)
        from piu_timeline.storage import relocate_evidence
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
        from piu_timeline.charts.data import auto_register
        auto_register(result, final)
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
    from piu_timeline.play.report import write_index
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
