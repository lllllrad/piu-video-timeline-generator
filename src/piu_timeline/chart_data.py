"""Create editable, explicitly unverified chart drafts from official timing and video evidence."""
import argparse
from collections import Counter
import fcntl
from fractions import Fraction
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import unicodedata
import uuid

import numpy as np

from . import ucs
from .chart_audio import align
from .official_ucs import Client, ROOT, index, write_json, atomic_write


def default_repository():
    return Path(os.environ.get('PIU_CHART_DATA_DIR', str(ROOT.parent / 'piu-chart-data'))).expanduser()


def title_key(title):
    return ''.join(char for char in unicodedata.normalize('NFKC', title).casefold() if char.isalnum())


def initialize(repository, client=None):
    repository = Path(repository)
    catalogue_path = repository / 'catalog.json'
    catalogue = json.loads(catalogue_path.read_text()) if catalogue_path.is_file() else (client or Client()).catalogue()
    repository.mkdir(parents=True, exist_ok=True)
    with (repository / '.chart-data.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for name, content in {
            'README.md': '# PIU chart data\n\n'
                'Official UCS files provide timing only. `timing/` preserves those blank templates; '
                '`charts/<UCS code>/<mode and level>/<revision>/chart.ucs` contains editable notes. '
                'Chart metadata records source observations, audio alignment and unresolved placements.\n\n'
                'Automatically generated charts are **unreviewed drafts**, not verified chart truth. '
                'Edit UCS rows directly: `.` empty, `X` tap, `M` hold head, `H` hold body, `W` hold tail. '
                'Single has five columns; Double has ten. Review the metadata and change its '
                '`review_status` to `reviewed` only after independent verification. '
                'Automatic registration never replaces an existing chart directory. '
                'Use a new revision directory for game chart updates.\n\n'
                'Use metadata `regions` for song-relative processing methods and scoped automatic-check exceptions. '
                'Every region requires a reason. The root `schema.json` documents editable fields.\n\n'
                'Reference audio, recordings, caches and generated HTML belong outside this repository.\n',
            '.gitignore': '.chart-data.lock\n*.build-*\n*.mp3\n*.mp4\n*.mkv\n*.zip\ncache/\n',
            'aliases.json': '{}\n',
        }.items():
            if not (repository / name).exists():
                atomic_write(repository / name, content.encode())
        if not (repository / 'schema.json').exists():
            atomic_write(repository / 'schema.json', (ROOT / 'schemas/chart-metadata.schema.json').read_bytes())
        if not (repository / 'catalog.json').exists():
            write_json(repository / 'catalog.json', catalogue)
        if not (repository / '.git').exists():
            subprocess.run(['git', 'init', '-q', str(repository)], check=True)
    return repository


def catalogue(repository):
    return json.loads((repository / 'catalog.json').read_text())


def resolve_code(repository, song, explicit=None):
    songs = catalogue(repository)['songs']
    if explicit:
        code = index(explicit)
        if code not in {item['index'] for item in songs}:
            raise ValueError(f'{code} is absent from the saved official catalogue; refresh it first')
        return code
    key = title_key(song or '')
    if not key:
        return None
    aliases = json.loads((repository / 'aliases.json').read_text())
    candidates = {item['index'] for item in songs if title_key(item['title']) == key}
    if key in aliases:
        candidates.add(aliases[key]['index'])
    return next(iter(candidates)) if len(candidates) == 1 else None


def remember_alias(repository, title, code):
    key = title_key(title or '')
    if not key:
        return
    code = resolve_code(repository, title, code)
    existing = resolve_code(repository, title)
    aliases = json.loads((repository / 'aliases.json').read_text())
    if existing not in (None, code) or key in aliases and aliases[key]['index'] != code:
        raise ValueError('Song alias conflicts with an existing UCS identity')
    aliases[key] = {'title': title, 'index': code, 'basis': 'explicit_assignment'}
    write_json(repository / 'aliases.json', aliases)


def draft(template, data, alignment, extend_constant_tempo=False):
    """Place observed heads/holds, keeping collisions and censored ends unresolved."""
    from .play_holds import presentation
    view = presentation(data)
    chart = view.get('chart') or ''
    if not re.fullmatch(r'[SD]\d{1,2}', chart):
        raise ValueError('A recognized Single/Double chart and level are required')
    lanes = 5 if chart.startswith('S') else 10
    if len(view['layout']['lanes']) != lanes:
        raise ValueError('Recognized chart mode conflicts with analyzed lane geometry')
    document = template.expanded(lanes)
    grid = list(document.grid())
    extension = None
    if extend_constant_tempo:
        endpoints = [note['target_seconds']-alignment['song_start_seconds'] for note in view['notes']
                     if note['status'] == 'estimated' and math.isfinite(note['target_seconds'])
                     and note.get('prediction_uncertainty_seconds', .02) <= .08]
        endpoints.extend(sum(hold['end_range'])/2-alignment['song_start_seconds']
                         for hold in view.get('hold_analysis', {}).get('holds', [])
                         if hold['end_range'] and not hold['end_censored'])
        latest = min(max(endpoints, default=0)+.05, data['end_seconds']-alignment['song_start_seconds']+.1)
        settings = {}
        for section in document.sections:
            settings.update(section.directives)
        step = 60/(Fraction(settings['BPM'])*int(settings['Split']))
        original_end = grid[-1][2]
        additional = max(0, math.ceil((Fraction(str(latest))-original_end)/step))
        if additional:
            if additional*step > 900:
                raise ValueError('Timing extension exceeds supported song duration')
            document.sections[-1].rows.extend(['.'*lanes]*additional)
            grid = list(document.grid())
            extension = {'basis': 'constant_tempo_catalogue_and_template', 'additional_rows': additional,
                         'original_last_row_seconds': float(original_end), 'extended_last_row_seconds': float(grid[-1][2]),
                         'review_required': True}
    times = np.array([float(time) for _, _, time in grid])
    if not np.all(np.diff(times) > 0):
        raise ValueError('Overlapping UCS timing sections need manual placement')
    origin = alignment['song_start_seconds']
    if not math.isfinite(origin) or not math.isfinite(alignment['uncertainty_seconds']):
        raise ValueError('Song alignment must be finite')
    holds = {hold['display_note']: hold for hold in view.get('hold_analysis', {}).get('holds', [])}
    pending, proposals = [], []
    def cell(target, uncertainty):
        if not math.isfinite(target) or not math.isfinite(uncertainty) or not 0 <= uncertainty <= .08:
            raise ValueError('Unbounded visible-note timing')
        relative = target - origin
        ri = int(np.searchsorted(times, relative))
        candidates = [i for i in (ri-1, ri) if 0 <= i < len(times)]
        selected = min(candidates, key=lambda i: abs(times[i]-relative))
        residual = float(times[selected]-relative)
        tolerance = uncertainty + alignment['uncertainty_seconds'] + .012
        if relative < times[0]-tolerance or relative > times[-1]+tolerance or abs(residual) > tolerance:
            raise ValueError('Visible note falls outside the official timing grid')
        return selected, residual
    for ni, note in enumerate(view['notes']):
        if note['status'] != 'estimated':
            continue
        try:
            lane = note['lane']
            if not isinstance(lane, int) or not 0 <= lane < lanes:
                raise ValueError('Invalid observed lane')
            start, residual = cell(note['target_seconds'], note.get('prediction_uncertainty_seconds', .02))
            end = start
            hold = holds.get(ni)
            if hold:
                if hold['start_censored'] or hold['end_censored'] or not hold['end_range']:
                    raise ValueError('Hold endpoint is censored')
                end_range = hold['end_range']
                end, _ = cell(sum(end_range)/2, (end_range[1]-end_range[0])/2)
                if end <= start:
                    raise ValueError('Hold endpoints share or reverse a timing row')
            proposals.append({'note': ni, 'lane': lane, 'start': start, 'end': end,
                              'kind': 'hold' if hold else 'tap', 'residual_seconds': residual,
                              'observed_target_range': [note['target_seconds']-note.get('prediction_uncertainty_seconds', .02),
                                                        note['target_seconds']+note.get('prediction_uncertainty_seconds', .02)]})
        except ValueError as error:
            pending.append({'note': ni, 'reason': str(error)})
    occupied = {}
    for pi, proposal in enumerate(proposals):
        for row in range(proposal['start'], proposal['end']+1):
            occupied.setdefault((row, proposal['lane']), []).append(pi)
    conflicts = {pi for owners in occupied.values() if len(owners) > 1 for pi in owners}
    placements = []
    for pi, proposal in enumerate(proposals):
        if pi in conflicts:
            pending.append({'note': proposal['note'], 'reason': 'Conflicting observed notes occupy the same lane and timing row'})
            continue
        for row in range(proposal['start'], proposal['end']+1):
            si, ri, _ = grid[row]
            chars = list(document.sections[si].rows[ri])
            chars[proposal['lane']] = ('X' if proposal['kind'] == 'tap' else
                                       'M' if row == proposal['start'] else 'W' if row == proposal['end'] else 'H')
            document.sections[si].rows[ri] = ''.join(chars)
        si, ri, time = grid[proposal['start']]
        ei, er, end_time = grid[proposal['end']]
        placements.append({**proposal, 'section': si, 'row': ri, 'song_seconds': float(time),
                           'end_section': ei, 'end_row': er, 'end_song_seconds': float(end_time)})
    if not placements:
        raise ValueError('No bounded notes can be placed on the official timing grid')
    return document, {'placements': placements, 'unresolved': pending, 'timing_extension': extension,
                      'summary': {'placed_taps': sum(p['kind'] == 'tap' for p in placements),
                                  'placed_holds': sum(p['kind'] == 'hold' for p in placements),
                                  'unresolved_note_heads': len(pending),
                                  'excluded_observations': dict(Counter(note.get('reason') for note in view['notes'] if note['status'] != 'estimated'))}}


def register(data, output, code=None, repository=None, song_start=None, revision='phoenix', client=None, rebuild_draft=False):
    repository = Path(repository) if repository is not None else default_repository()
    output = Path(output)
    if not repository.is_dir():
        return {'status': 'disabled', 'reason': 'Initialize a chart repository with just charts init'}
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}', revision):
        raise ValueError('Invalid chart revision')
    if song_start is not None and not math.isfinite(song_start):
        raise ValueError('Explicit song start must be finite')
    chart = data.get('chart') or ''
    if not re.fullmatch(r'[SD]\d{1,2}', chart):
        return {'status': 'pending', 'reason': 'Chart mode/level is unresolved'}
    resolved = resolve_code(repository, data.get('song'), code)
    if resolved is None:
        return {'status': 'pending', 'reason': 'Song has no unique official UCS identity; specify --ucs-index'}
    resolved = index(resolved)
    target = repository / 'charts' / resolved / chart / revision
    previous = None
    def existing_result():
        result = {'status': 'existing', 'chart': str(target / 'chart.ucs'), 'index': resolved,
                  'revision': revision, 'chart_mode': chart, 'repository': str(repository.resolve())}
        if song_start is not None:
            result['alignment'] = {'method': 'explicit_song_start', 'song_start_seconds': song_start, 'uncertainty_seconds': 0, 'rate': 1}
        return result
    with (repository / '.chart-data.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if code:
            remember_alias(repository, data.get('song'), resolved)
        if target.exists():
            if not (target / 'chart.ucs').is_file() or not (target / 'metadata.json').is_file():
                raise ValueError(f'Existing chart directory is incomplete; inspect {target}')
            ucs.parse((target / 'chart.ucs').read_text())
            if not rebuild_draft:
                return existing_result()
            old_chart = (target / 'chart.ucs').read_bytes()
            old_metadata = (target / 'metadata.json').read_bytes()
            old = json.loads(old_metadata)
            if old.get('review_status') != 'unreviewed_draft' or old.get('generated_ucs_sha256') != sha256(old_chart).hexdigest():
                raise ValueError('Cannot rebuild a reviewed or manually edited chart; create a new revision')
            previous = (old_chart, old_metadata)
    provider = client or Client()
    template, music, url = provider.template(resolved)
    if song_start is not None:
        alignment = {'method': 'explicit_song_start', 'song_start_seconds': song_start, 'uncertainty_seconds': 0, 'rate': 1}
    else:
        alignment = align(data, music)
    code_entry = next(item for item in catalogue(repository)['songs'] if item['index'] == resolved)
    bpm = code_entry.get('bpm', '')
    constant = (re.fullmatch(r'\d+(?:\.\d+)?', bpm) is not None
                and {Fraction(value) for section in template.sections for key, value in section.directives if key == 'BPM'} == {Fraction(bpm)})
    document, evidence = draft(template, data, alignment, extend_constant_tempo=constant)
    content = document.text().encode()
    metadata = {'$schema': '../../../../schema.json', 'schema': 1, 'regions': [],
                'identity': {'ucs_index': resolved, 'chart': chart, 'revision': revision},
                'song': code_entry, 'review_status': 'unreviewed_draft', 'generated_ucs_sha256': sha256(content).hexdigest(),
                'timing_source': {'url': url, 'ucs_sha256': sha256(template.text().encode()).hexdigest()},
                'source': {'source_id': output.parents[1].name, 'segment_number': data.get('segment_number'),
                           'media_size_bytes': data['media']['size_bytes'], 'media_mtime_ns': data['media']['mtime_ns'],
                           'playback_range': [data['start_seconds'], data['end_seconds']],
                           'analysis_sha256': sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()},
                'alignment': alignment, **evidence,
                'limitations': ['Notes come from video geometry, independently of successful input or judgment association.',
                                'Unobserved notes are not filled from the blank official template.',
                                'This source-derived draft must not validate its own source observations.']}
    with (repository / '.chart-data.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.exists():
            if previous is None:
                return existing_result()
            if previous != ((target/'chart.ucs').read_bytes(), (target/'metadata.json').read_bytes()):
                raise ValueError('Chart changed while rebuilding; preserve the newer files')
            # Preserve user-added metadata fields when explicitly rebuilding an
            # untouched unreviewed UCS draft. Automatic runs never rebuild.
            metadata = {**json.loads(previous[1]), **metadata}
            metadata['regions'] = json.loads(previous[1]).get('regions', [])
        elif previous is not None:
            raise ValueError('Chart was removed while rebuilding; retry explicitly')
        timing = repository / 'timing' / f'{resolved}.ucs'
        if not timing.exists():
            atomic_write(timing, template.text().encode())
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.build-' + uuid.uuid4().hex)
        try:
            temporary.mkdir()
            (temporary / 'chart.ucs').write_bytes(content)
            write_json(temporary / 'metadata.json', metadata)
            backup = target.with_name(target.name + '.build-previous-' + uuid.uuid4().hex)
            if previous is not None:
                target.rename(backup)
            try:
                temporary.rename(target)
            except OSError:
                if previous is not None:
                    backup.rename(target)
                raise
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return {'status': 'rebuilt' if previous is not None else 'created', 'chart': str(target / 'chart.ucs'), 'index': resolved,
            'alignment': alignment, 'revision': revision, 'chart_mode': chart, 'repository': str(repository.resolve()), **evidence['summary']}


def auto_register(data, output, **options):
    """A failed optional download cannot invalidate successful native analysis."""
    registration = Path(output) / 'chart-registration.json'
    try:
        previous = json.loads(registration.read_text()) if registration.is_file() else {}
    except (ValueError, OSError):
        previous = {}
    try:
        if 'repository' not in options and previous.get('repository'):
            selected = Path(previous['repository'])
            if (selected / 'catalog.json').is_file():
                options['repository'] = selected
        selected = Path(options.get('repository') or default_repository())
        if ('revision' not in options and previous.get('revision') and previous.get('chart_mode') == data.get('chart')
                and (selected / 'catalog.json').is_file()
                and resolve_code(selected, data.get('song')) == previous.get('index')):
            options['revision'] = previous['revision']
        result = register(data, output, **options)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        result = {'status': 'pending', 'reason': str(error)}
    if result.get('alignment', {}).get('method') == 'explicit_song_start':
        result['alignment_media'] = data.get('media')
    elif result['status'] == 'existing' and registration.is_file():
        if (previous.get('index') == result.get('index') and previous.get('alignment_media') == data.get('media')
                and previous.get('alignment', {}).get('method') == 'explicit_song_start'):
            result.update(alignment=previous['alignment'], alignment_media=previous['alignment_media'])
    write_json(registration, result)
    if result['status'] != 'disabled':
        print(f'Chart data: {result["status"]}; {result.get("chart", result.get("reason", ""))}', flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=default_repository())
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init', help='Initialize a separate Git repository and save the official catalogue')
    sub.add_parser('refresh-catalog', help='Refresh the official catalogue, preserving aliases and charts')
    sub.add_parser('validate', help='Validate all current UCS files and human-authored region policies')
    listing = sub.add_parser('list', help='Find official UCS codes by title or code')
    listing.add_argument('query', nargs='?', default='')
    alias = sub.add_parser('alias', help='Explicitly associate a video song title with an official code')
    alias.add_argument('title'); alias.add_argument('ucs_index')
    add = sub.add_parser('add', help='Register a draft from an already analyzed play')
    add.add_argument('source'); add.add_argument('--segment', type=int, default=1)
    add.add_argument('--ucs-index'); add.add_argument('--song-start', type=float)
    add.add_argument('--revision', default='phoenix')
    add.add_argument('--rebuild-draft', action='store_true', help='Explicitly rebuild only an untouched, unreviewed UCS draft; preserve a backup')
    sub.add_parser('sync', help='Register missing charts from all completed local play analyses')
    args = parser.parse_args()
    try:
        if args.command == 'init':
            print(initialize(args.repo)); return
        if args.command == 'refresh-catalog':
            write_json(args.repo / 'catalog.json', Client().catalogue(refresh=True)); return
        if args.command == 'validate':
            from .chart_policy import validate_regions
            count = 0
            for path in sorted((args.repo / 'charts').glob('*/*/*/metadata.json')):
                if '.build-' in path.parent.name:
                    continue
                validate_regions(json.loads(path.read_text()))
                ucs.parse(path.with_name('chart.ucs').read_text())
                count += 1
            print(f'Validated {count} charts and their region policies'); return
        if args.command == 'list':
            for song in catalogue(args.repo)['songs']:
                if args.query.casefold() in (song['index']+' '+song['title']+' '+song.get('artist', '')).casefold():
                    print(f'{song["index"]}\t{song["title"]}\t{song.get("artist", "")}')
            return
        if args.command == 'alias':
            with (args.repo / '.chart-data.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                remember_alias(args.repo, args.title, args.ucs_index)
            return
        from .workflow import LOCAL_DATA, source_id
        if args.command == 'add':
            if args.segment < 1:
                raise ValueError('Segment number must be positive')
            paths = [LOCAL_DATA / source_id(args.source) / 'play' / f'segment-{args.segment:03}' / 'analysis.json']
        else:
            paths = sorted(LOCAL_DATA.glob('*/play/segment-[0-9][0-9][0-9]/analysis.json'))
        counts = Counter()
        for path in paths:
            options = {'repository': args.repo}
            if args.command == 'add':
                options.update(code=args.ucs_index, song_start=args.song_start, revision=args.revision, rebuild_draft=args.rebuild_draft)
            result = auto_register(json.loads(path.read_text()), path.parent, **options)
            counts[result['status']] += 1
        print(json.dumps(dict(counts)))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
