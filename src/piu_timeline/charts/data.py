"""Create editable, explicitly unverified chart drafts from official timing and video evidence."""
import argparse
from collections import Counter
import fcntl
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

from piu_timeline.charts import ucs
from piu_timeline.charts.audio import align
from piu_timeline.charts.official import Client, ROOT, index, write_json, atomic_write


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
    if key in aliases:
        return
    aliases[key] = {'title': title, 'index': code, 'basis': 'explicit_assignment'}
    write_json(repository / 'aliases.json', aliases)


def canonical_chart(data):
    from piu_timeline.derived import call
    return call('chartDraft.canonicalChart',{'chart':data.get('chart'),'chart_identity':data.get('chart_identity')})


def draft(template,data,alignment,extend_constant_tempo=False,*,input_path=None):
    from dataclasses import asdict
    from piu_timeline.derived import call
    from piu_timeline.play.holds.analysis import chart_projection
    view=chart_projection(data)
    fields=('chart','chart_identity','layout','notes','hold_analysis','beat_timing','end_seconds')
    observations={key:view[key]for key in fields if key in view}
    if input_path is not None:
        write_json(input_path, {'timing_text':template.text(),'chart_observations':observations,
                               'alignment':alignment,'extend_constant_tempo':extend_constant_tempo})
    doc,proof=call('chartDraft.draft',asdict(template),observations,alignment,extend_constant_tempo)
    return ucs.document(doc),proof


def register(data, output, code=None, repository=None, song_start=None, revision='phoenix', client=None, rebuild_draft=False):
    from piu_timeline.play.support import require_chart_geometry
    require_chart_geometry(data)
    repository = Path(repository) if repository is not None else default_repository()
    output = Path(output)
    if not repository.is_dir():
        return {'status': 'disabled', 'reason': 'Initialize a chart repository with just charts init'}
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}', revision):
        raise ValueError('Invalid chart revision')
    if song_start is not None and not math.isfinite(song_start):
        raise ValueError('Explicit song start must be finite')
    chart = canonical_chart(data)
    if chart is None:
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
            existing_document=ucs.parse((target / 'chart.ucs').read_text())
            if not rebuild_draft:
                from piu_timeline.charts.assertions import validate as validate_assertions
                validate_assertions(existing_document,json.loads((target/'metadata.json').read_text()).get('row_assertions',[]))
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
    constant = ucs.constant_tempo(template,bpm)
    document, evidence = draft(template, data, alignment, extend_constant_tempo=constant, input_path=output/'ucs-input.json')
    content = document.text().encode()
    metadata = {'$schema': '../../../../schema.json', 'schema': 1, 'regions': [],
                'identity': {'ucs_index': resolved, 'chart': chart, 'revision': revision},
                'display_chart': data.get('chart'), 'chart_identity_evidence': data.get('chart_identity'),
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
            metadata['gimmick_candidates'] = json.loads(previous[1]).get('gimmick_candidates', [])
        elif previous is not None:
            raise ValueError('Chart was removed while rebuilding; retry explicitly')
        from piu_timeline.charts.assertions import validate as validate_assertions
        validate_assertions(document,metadata.get('row_assertions',[]))
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
    if result['status'] in ('existing','created','rebuilt'):
        from piu_timeline.charts.gimmicks import record_candidates
        try:
            candidates = record_candidates(data,Path(output),result)
            if candidates['changed'] and (Path(output)/'report.html').is_file():
                from piu_timeline.play.presentation import prepare_report
                from piu_timeline.play.report import write_report
                prepared=prepare_report(data,Path(output)/'report.html')
                write_report(prepared,Path(output)/'report.html')
        except (OSError,ValueError,KeyError) as error:
            candidates = {'status':'pending','reason':str(error)}
        result['gimmick_candidates'] = candidates
    if result['status'] != 'disabled':
        print(f'Chart data: {result["status"]}; {result.get("chart", result.get("reason", ""))}', flush=True)
        if result.get('unresolved_note_heads'):
            print(f'Warning: UCS draft has {result["unresolved_note_heads"]} unresolved note placements; inspect its metadata.json.',flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=default_repository())
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init', help='Initialize a separate Git repository and save the official catalogue')
    sub.add_parser('refresh-catalog', help='Refresh the official catalogue, preserving aliases and charts')
    sub.add_parser('refresh-aliases', help='Import official localized titles without replacing existing aliases')
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
        if args.command == 'refresh-aliases':
            from piu_timeline.charts.localized import refresh
            print(json.dumps(refresh(args.repo),ensure_ascii=False)); return
        if args.command == 'validate':
            from piu_timeline.charts.policy import validate_regions
            count = 0
            for path in sorted((args.repo / 'charts').glob('*/*/*/metadata.json')):
                if '.build-' in path.parent.name:
                    continue
                metadata = json.loads(path.read_text())
                validate_regions(metadata)
                from piu_timeline.charts.gimmicks import validate_candidates
                validate_candidates(metadata)
                document=ucs.parse(path.with_name('chart.ucs').read_text())
                from piu_timeline.charts.assertions import validate as validate_assertions
                validate_assertions(document,metadata.get('row_assertions',[]))
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
        from piu_timeline.workflow import LOCAL_DATA, source_id
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
