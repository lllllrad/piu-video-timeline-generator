"""Human-authored song regions: processing choices and scoped check exceptions."""
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import subprocess

from .official_ucs import write_json


PROCESSING = {'standard', 'exclude_timing', 'hold_state_only'}
CHECKS = {'timing_evidence', 'stage_grade_totals'}


def validate_regions(metadata):
    regions = metadata.get('regions', [])
    if not isinstance(regions, list):
        raise ValueError('Chart regions must be a list')
    result, identifiers = [], set()
    for region in regions:
        if not isinstance(region, dict) or set(region)-{'id', 'start_seconds', 'end_seconds', 'processing', 'check_exceptions', 'reason', 'details'}:
            raise ValueError('Unknown or malformed chart region fields')
        identifier = region.get('id')
        if not isinstance(identifier, str) or not identifier.strip() or identifier in identifiers:
            raise ValueError('Chart region IDs must be nonempty and unique')
        identifiers.add(identifier)
        start, end = region.get('start_seconds'), region.get('end_seconds')
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in (start, end)) or not 0 <= start < end:
            raise ValueError('Chart region requires finite song seconds with 0 <= start < end')
        processing = region.get('processing', 'standard')
        if not isinstance(processing, str) or processing not in PROCESSING:
            raise ValueError(f'Unknown chart region processing: {processing}')
        exceptions = region.get('check_exceptions', [])
        if not isinstance(exceptions, list) or any(not isinstance(check, str) or check not in CHECKS for check in exceptions) or len(set(exceptions)) != len(exceptions):
            raise ValueError('Unknown or duplicate automatic check exceptions')
        if not isinstance(region.get('reason'), str) or not region['reason'].strip():
            raise ValueError('Each chart region requires a reason')
        if 'details' in region and not isinstance(region['details'], str):
            raise ValueError('Chart region details must be text')
        result.append({**region, 'processing': processing, 'check_exceptions': exceptions})
    result.sort(key=lambda region: (region['start_seconds'], region['end_seconds']))
    for ri, region in enumerate(result):
        for other in result[ri+1:]:
            if other['start_seconds'] >= region['end_seconds']:
                break
            if region['processing'] != other['processing'] and 'standard' not in (region['processing'], other['processing']):
                raise ValueError('Overlapping chart regions specify conflicting processing methods')
    return result


def _alignment(data, directory, metadata, code):
    registration = directory / 'chart-registration.json'
    if registration.is_file():
        saved = json.loads(registration.read_text())
        if (saved.get('index') == code and saved.get('alignment', {}).get('method') == 'explicit_song_start'
                and saved.get('alignment_media') == data.get('media')):
            return saved['alignment']
    seed = metadata.get('source', {})
    identity = data.get('media', {})
    if (seed.get('source_id') == directory.parents[1].name
            and seed.get('segment_number') == data.get('segment_number')
            and seed.get('media_size_bytes') == identity.get('size_bytes')
            and seed.get('media_mtime_ns') == identity.get('mtime_ns')
            and (data.get('segment_number') is not None
                 or seed.get('playback_range') == [data['start_seconds'], data['end_seconds']])):
        return metadata['alignment']
    from .official_ucs import Client
    from .chart_audio import align
    _, music, _ = Client().template(code)
    contract = {'media': identity, 'start_seconds': data['start_seconds'], 'end_seconds': data['end_seconds'],
                'ucs_index': code, 'reference_audio_sha256': sha256(music.read_bytes()).hexdigest()}
    cache = directory / 'chart-policy-alignment.json'
    if cache.is_file():
        saved = json.loads(cache.read_text())
        if saved.get('contract') == contract:
            return saved['alignment']
    result = align(data, music)
    write_json(cache, {'contract': contract, 'alignment': result})
    return result


def attach_regions(data, directory, repository=None):
    """Read current chart annotations on every report build, without stale policy."""
    from .chart_data import default_repository, resolve_code
    directory = Path(directory)
    registration = directory / 'chart-registration.json'
    if repository is None and registration.is_file():
        try:
            saved = json.loads(registration.read_text())
        except (ValueError, OSError):
            saved = {}
        if saved.get('chart'):
            chart_path = Path(saved['chart']).resolve()
            if len(chart_path.parents) >= 5 and chart_path.parents[3].name == 'charts':
                repository = chart_path.parents[4]
    repository = Path(repository) if repository is not None else default_repository()
    if not (repository / 'catalog.json').is_file():
        return data
    try:
        code = resolve_code(repository, data.get('song'))
        if not code or not re.fullmatch(r'CS\d{3,5}', code) or not isinstance(data.get('chart'), str) or not re.fullmatch(r'[SD]\d{1,2}', data['chart']):
            return data
        metadata_path = repository / 'charts' / code / data['chart'] / 'phoenix' / 'metadata.json'
        if registration.is_file():
            saved = json.loads(registration.read_text())
            if (saved.get('index') == code and saved.get('chart')
                    and len(Path(saved['chart']).parents) >= 2
                    and Path(saved['chart']).parents[1].name == data['chart']):
                metadata_path = Path(saved['chart']).with_name('metadata.json')
        if not metadata_path.is_file():
            return data
        metadata = json.loads(metadata_path.read_text())
        regions = validate_regions(metadata)
        if not regions:
            return data
        alignment = _alignment(data, directory, metadata, code)
        origin = alignment['song_start_seconds']
        if not isinstance(origin, (int, float)) or not math.isfinite(origin):
            raise ValueError('Invalid song origin for chart region mapping')
        mapped = [{**region, 'playback_start_seconds': origin+region['start_seconds'],
                   'playback_end_seconds': origin+region['end_seconds']} for region in regions]
        policy = {'status': 'applied', 'metadata_path': str(metadata_path),
                  'metadata_sha256': sha256(metadata_path.read_bytes()).hexdigest(),
                  'alignment': alignment, 'regions': mapped,
                  'stage_grade_totals': 'partial_exemption' if any('stage_grade_totals' in r['check_exceptions'] for r in regions) else 'no_exemption'}
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        policy = {'status': 'invalid', 'reason': str(error), 'regions': []}
    write_json(directory / 'chart-policy.json', policy)
    return {**data, 'chart_policy': policy}


def note_policy(data, note):
    target = note.get('target_seconds')
    if target is None:
        return None
    regions = [region for region in data.get('chart_policy', {}).get('regions', [])
               if region['playback_start_seconds'] <= target < region['playback_end_seconds']]
    if not regions:
        return None
    processing = next((region['processing'] for region in regions if region['processing'] != 'standard'), 'standard')
    return {'regions': [region['id'] for region in regions], 'processing': processing,
            'suppress_timing': processing == 'exclude_timing' or processing == 'hold_state_only' and note.get('note_type') != 'hold',
            'check_exceptions': sorted({check for region in regions for check in region['check_exceptions']}),
            'reasons': [region['reason'] for region in regions]}


def apply_projection(data):
    if not data.get('chart_policy', {}).get('regions'):
        return data
    policies = {ni: note_policy(data, note) for ni, note in enumerate(data['notes']) if note['status'] == 'estimated'}
    excluded = {ni for ni, policy in policies.items() if policy and policy['suppress_timing']}
    if not excluded:
        return data
    matches = [match for match in data['matches'] if match['note'] not in excluded]
    holds = []
    for hold in data.get('hold_analysis', {}).get('holds', []):
        if hold.get('display_note') in excluded:
            hold = {**hold, 'input': {**hold['input'], 'segments': [], 'recognition_envelope': None,
                                     'policy_retained_observations': hold['input']['segments']}}
        holds.append(hold)
    return {**data, 'matches': matches,
            'hold_analysis': {**data.get('hold_analysis', {}), 'holds': holds},
            'coverage': {**data.get('coverage', {}), 'timed_note_heads': len(matches), 'policy_excluded_note_heads': len(excluded)}}
