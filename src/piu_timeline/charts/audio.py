"""Translation-only reference music alignment; original media is read unchanged."""
import math
import json
from hashlib import sha256
from pathlib import Path
import subprocess

import numpy as np


HOP_SECONDS = .01


def features(path, start=None, duration=None):
    command = ['ffmpeg', '-v', 'error', '-nostdin']
    if start is not None:
        command += ['-ss', str(start)]
    command += ['-i', str(path)]
    if duration is not None:
        command += ['-t', str(duration)]
    command += ['-vn', '-ac', '1', '-ar', '8000', '-f', 'f32le', 'pipe:1']
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    samples = np.frombuffer(result.stdout, dtype='<f4')
    if len(samples) < 8000 * 8:
        raise ValueError('Reference alignment requires at least eight seconds of audio')
    windows = np.lib.stride_tricks.sliding_window_view(samples, 512)[::80]
    spectrum = abs(np.fft.rfft(windows * np.hanning(512))) ** 2
    edges = np.geomspace(80, 3900, 25) / 8000 * 512
    bands = np.array([np.log1p(spectrum[:, int(lo):max(int(lo)+1, int(hi))].mean(axis=1) * 100)
                      for lo, hi in zip(edges[:-1], edges[1:])])
    return (bands - bands.mean(axis=1, keepdims=True)) / (bands.std(axis=1, keepdims=True) + 1e-6)


def align_features(reference, observed):
    """Require independent reference windows to agree, rejecting repeated music."""
    if reference.ndim != 2 or observed.ndim != 2 or reference.shape[0] != observed.shape[0]:
        raise ValueError('Invalid audio features')
    length = min(2500, reference.shape[1] // 4, observed.shape[1] // 3)
    if length < 200:
        raise ValueError('Insufficient audio for independent alignment windows')
    windows = []
    for fraction in (.15, .4, .65):
        start = min(int(reference.shape[1] * fraction), reference.shape[1] - length)
        part = reference[:, start:start+length]
        count = observed.shape[1]
        size = 1 << (count + length - 1).bit_length()
        corr = np.fft.irfft(np.fft.rfft(observed, n=size) * np.conj(np.fft.rfft(part, n=size)), n=size).sum(axis=0)[:count-length+1]
        energy = np.r_[0, np.cumsum((observed ** 2).sum(axis=0))]
        denominator = np.sqrt(np.maximum(0, energy[length:] - energy[:-length]) * (part ** 2).sum())
        scores = corr / np.maximum(denominator, 1e-8)
        best = int(scores.argmax())
        rivals = scores.copy()
        rivals[max(0, best-30):best+31] = -1
        windows.append({'offset_seconds': (best-start)*HOP_SECONDS, 'score': float(scores[best]),
                        'peak_margin': float(scores[best]-rivals.max()), 'reference_start_seconds': start*HOP_SECONDS})
    valid = [window for window in windows if window['score'] >= .55 and window['peak_margin'] >= .08]
    clusters = [[other for other in valid if abs(other['offset_seconds']-window['offset_seconds']) <= .04] for window in valid]
    agreed = max(clusters, key=lambda cluster: (len(cluster), sum(w['score'] for w in cluster)), default=[])
    if len(agreed) < 2 or max(w['offset_seconds'] for w in agreed)-min(w['offset_seconds'] for w in agreed) > .04:
        raise ValueError(f'Reference music alignment is ambiguous: {windows}')
    offset = float(np.median([window['offset_seconds'] for window in agreed]))
    return {'method': 'reference_audio_translation', 'offset_seconds': offset,
            'uncertainty_seconds': max(abs(w['offset_seconds']-offset) for w in agreed)+HOP_SECONDS,
            'windows': windows, 'accepted_windows': len(agreed), 'rate': 1}


def align(data, reference_path):
    start, end = data['start_seconds'], data['end_seconds']
    if not all(math.isfinite(value) for value in (start, end)) or not 8 <= end-start <= 900:
        raise ValueError('Audio alignment needs a bounded 8..900 second gameplay interval')
    source = Path(data['media']['path'])
    before = source.stat()
    expected = data['media']
    if (before.st_size, before.st_mtime_ns) != (expected['size_bytes'], expected['mtime_ns']):
        raise ValueError('Source identity differs from saved play evidence')
    result = align_features(features(reference_path), features(source, start, end-start))
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Source changed during audio alignment')
    result['song_start_seconds'] = start + result['offset_seconds']
    return result


def prepare_alignment(data, directory, metadata, code, client=None):
    """Reuse a verified origin or prepare one source-bound audio translation."""
    from piu_timeline.charts.official import write_json
    directory=Path(directory)
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
    from piu_timeline.charts.official import Client
    from piu_timeline.charts.audio import align
    _, music, _ = (client or Client()).template(code)
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
