"""Common, source-timestamped access to the four visual evidence channels."""
from collections import Counter
from itertools import zip_longest
import json

from piu_timeline.play.processing import PROCESSING_FORMAT, observe_processing, processing_support, processing_conflicts

from piu_timeline.play.note_types import TYPE_FORMAT, observe_types, observe_appearance

CHANNEL_FORMAT = {'schema': 1, 'revision': 7, 'processing': PROCESSING_FORMAT, 'note_types': TYPE_FORMAT}


def receptor_evidence(data):
    """One input-effect source for taps, holds, candidates and review."""
    channel = data.get('visual_channels', {}).get('receptors')
    return channel['events'] if channel is not None else data.get('hold_analysis', {}).get('receptor_runs', [])


def processing_evidence(data):
    return data.get('visual_channels', {}).get('processing', {}).get('notes', [])


def read_frames(path):
    with path.open() as stream:
        for line in stream:
            yield json.loads(line)


def collect(data, directory, frames):
    """Retain unassigned observations and raw trace references, not only matches."""
    native_path = directory/'frames.jsonl'
    native = list(read_frames(native_path))
    if len(native) != len(frames):
        raise ValueError('Visual channels have different native frame counts')
    timestamps = {}
    for raw, effect in zip(native, frames, strict=True):
        if any(abs(raw[key]-effect[key])>1e-6 for key in ('source_pts_seconds', 'playback_seconds')):
            raise ValueError('Visual channel source timestamps differ')
        timestamps[raw['playback_seconds']] = raw['source_pts_seconds']
    def popup_events(key, prefix):
        result = []
        for i, event in enumerate(data.get(key, [])):
            lo, hi = event['lower_seconds'], event['upper_seconds']
            result.append({**event, 'id': prefix+str(i),
                           'source_pts_seconds': [timestamps.get(lo), timestamps.get(hi)]})
        return result
    judgment_trace = directory/'judgments.jsonl'
    word_counts, words = Counter(), []
    if judgment_trace.is_file():
        for raw, word in zip_longest(native, read_frames(judgment_trace)):
            if raw is None or word is None or any(abs(raw[k]-word[k])>1e-6 for k in ('source_pts_seconds','playback_seconds')):
                raise ValueError('Judgment channel differs from native frame timeline')
            words.append(word)
            word_counts[word.get('label') or ('blank' if word.get('blank') else 'unknown')] += 1
    baseline_path = directory/'frames.base.jsonl'
    baseline = list(read_frames(baseline_path)) if baseline_path.is_file() else native
    if len(baseline) != len(native) or any(
            any(abs(a[k]-b[k]) > 1e-6 for k in ('source_pts_seconds', 'playback_seconds'))
            for a,b in zip(native, baseline, strict=True)):
        raise ValueError('Counter baseline differs from native frame timeline')
    pixel_path = directory/'processing-features.npz'
    if pixel_path.is_file():
        import numpy as np
        with np.load(pixel_path, allow_pickle=False) as pixels:
            if len(pixels['times']) != len(native) or any(
                    abs(raw['playback_seconds']-time)>1e-6 or abs(raw['source_pts_seconds']-pts)>1e-6
                    for raw,time,pts in zip(native,pixels['times'],pixels['pts'], strict=True)):
                raise ValueError('Processing channel differs from native frame timeline')
    motion = [{'id': 'motion:'+str(i), 'note': i, 'lane': note['lane'], 'status': note['status'],
               'reason': note.get('reason'), 'observations': len(note.get('points', [])),
               'target_seconds': note.get('target_seconds'), 'trace': 'analysis.json#/notes/'+str(i)}
              for i, note in enumerate(data.get('notes', []))]
    effects = [{**run, 'id': 'receptor:'+str(i)} for i, run in enumerate(data.get('hold_analysis', {}).get('receptor_runs', []))]
    from piu_timeline.play.receptors import onset_overlaps
    processing = observe_processing(data, directory/'processing-features.npz')
    processing['body_fields'] = ['lane','top','bottom','top_visible','tail_visible','long','stripe_support']
    processing['body_observations'] = [[[body.get(key) for key in processing['body_fields']]
                                       for body in frame.get('bodies', [])] for frame in frames]
    for event in processing['notes']:
        event['id'] = 'processing:'+str(event['note'])
    if not words:
        words = [{} for _ in native]
    from piu_timeline.play.appearance import acquire
    from piu_timeline.play.object_roles import filter_frames
    interpreted=filter_frames(data,frames,bodies=True)
    if data.get('skin_detector'):
        from piu_timeline.play.skins.observations import observe
        types = observe(data, native)
    else:
        appearance = acquire(data,directory,native)
        types = observe_appearance(data,appearance,interpreted) if appearance else observe_types(data,pixel_path,interpreted)
    return {'format': CHANNEL_FORMAT,
            'layers': layer_manifest(directory),
            'timeline': {'frames': [[f['playback_seconds'],f['source_pts_seconds']] for f in native]},
            'popup': {'available': bool(native), 'judgment_available': judgment_trace.is_file(), 'combo_trace': 'frames.jsonl',
                      'counter_pixel_trace': 'counter-pixels.npz' if (directory/'counter-pixels.npz').is_file() else None,
                      'judgment_trace': 'judgments.jsonl', 'frames': len(native),
                      'combo_readable_frames': sum(f.get('combo') is not None for f in native),
                      'judgment_frame_counts': dict(word_counts),
                      'baseline_trace': 'frames.base.jsonl' if baseline_path.is_file() else 'frames.jsonl',
                      'observation_fields': ['combo','combo_confidence','judgment','judgment_confidence','blank',
                                             'combo_read_mode','combo_recovered','baseline_combo','baseline_combo_confidence'],
                      'observations': [[f.get('combo'),f.get('combo_confidence'),w.get('label'),w.get('confidence'),w.get('blank'),
                                        f.get('combo_read_mode'),f.get('combo_recovered',False),b.get('combo'),b.get('combo_confidence')]
                                       for f,w,b in zip(native,words,baseline, strict=True)],
                      'combo_events': popup_events('combo_events', 'combo:'),
                      'judgment_events': popup_events('judgment_events', 'judgment:')},
            'receptors': {'available': bool(frames), 'trace': 'hold-frames.jsonl', 'frames': len(frames),
                          'unknown_lane_frames': sum(s is None for f in frames for s in f['receptor_lit']),
                          'observation_fields': ['lane_states','lane_white_fractions','common_flash'],
                          'observations': [[f['receptor_lit'],f.get('receptor_white_fraction'),f.get('common_receptor_flash',False)] for f in frames],
                          'events': effects, 'onsets': sum(onset_overlaps(r, r['start_seconds'], r['end_seconds']) for r in effects)},
            'motion': {'available': True, 'trace': 'frames.jsonl', 'frames': len(native),
                       'detections': sum(len(f.get('notes', [])) for f in native), 'tracks': motion,
                       'observation_fields': ['lane','normalized_x','normalized_y','quality'],
                       'observations': [[[n['lane'],n['x'],n['y'],n.get('quality')] for n in f.get('notes', [])] for f in native]},
            'processing': processing, 'note_types': types}


def layer_manifest(directory):
    """Explicit artifact ownership; feature masks are not original RGB frames."""
    artifacts = {
        'pixel_acquisition': ['counter-pixels.npz'],
        'features': ['native-features/manifest.json', 'processing-features.npz',
                     'appearance-features.npz', 'evidence/judgments/features-v3.npz'],
        'frame_observations': ['frames.base.jsonl', 'frames.jsonl', 'judgments.jsonl', 'hold-frames.jsonl'],
        'interpretations': ['object-interpretation.json', 'head-registration.json', 'holds.json', 'visual-channels.json'],
        'associations': ['analysis.json'],
    }
    return {'source': 'analysis.json#/media',
            'artifacts': artifacts,
            'available': {name: (directory/name).is_file() for names in artifacts.values() for name in names},
            'dependencies': {'object_roles':['frames.jsonl','chart-policy.json'],
                             'head_registration':['interpreted_head_trajectory','appearance-features.npz'],
                             'processing': ['native_head_trajectory', 'native-features/manifest.json', 'spatial_masks', 'hold_geometry'],
                             'receptor_onsets': ['white_fractions', 'common_flash_filter'],
                             'matches': ['chart_timing', 'popup_events', 'lane_evidence']},
            'semantics': {'frames.jsonl': 'Counter recognition may include contextual recovery; baseline is separate.',
                          'receptors': 'Visual light states and onsets; physical switch timing is unmeasured.',
                          'processing': 'Visual persistence; independent of chart-time acceptance and HUD matches.',
                          'features': 'Thresholded masks, not lossless source frames; acquisition changes may reread media.'}}


def augment_channels(data, directory, frames=None):
    """Rebuild associations from retained pixels; invalidate independently of OCR."""
    from piu_timeline.play.holds.analysis import fingerprint
    inputs = ('frames.base.jsonl','frames.jsonl','judgments.jsonl','hold-frames.jsonl','processing-features.npz','appearance-features.npz','counter-pixels.npz','native-features/manifest.json')
    contract = {'format': CHANNEL_FORMAT,
                'analysis': fingerprint({key:data.get(key) for key in
                                         ('media','layout','analysis_height','notes','hold_analysis','combo_events','judgment_events','scroll_motion','object_interpretation')}),
                'traces': {name: [p.stat().st_size, p.stat().st_mtime_ns] if (p:=directory/name).is_file() else None for name in inputs}}
    path = directory/'visual-channels.json'
    if path.is_file():
        saved = json.loads(path.read_text())
        if saved.get('contract') == contract:
            return annotate_matches({**data, 'visual_channels': saved['channels']})
    if frames is None:
        from piu_timeline.play.receptors import observations, reject_common_flashes
        frames = list(read_frames(directory/'hold-frames.jsonl'))
        frames = reject_common_flashes(frames, observations(data, directory, frames))
    channels = collect(data, directory, frames)
    contract['traces'] = {name:[p.stat().st_size,p.stat().st_mtime_ns] if (p:=directory/name).is_file() else None for name in inputs}
    pending = path.with_suffix('.build-json')
    pending.write_text(json.dumps({'contract': contract, 'channels': channels}, ensure_ascii=False)+'\n')
    pending.replace(path)
    return annotate_matches({**data, 'visual_channels': channels})


def annotate_matches(data):
    """Make channel provenance available on every match, including conflicts."""
    if not data.get('visual_channels'):
        return data
    from piu_timeline.play.receptors import onset_overlaps
    guard = 2*(data.get('median_frame_interval_seconds') or .017)
    matches = []
    for original in data.get('matches', []):
        match = dict(original)
        match.pop('processing_conflict', None)
        ni = match['note']
        refs = ['motion:'+str(ni)]
        for key, prefix in (('combo_event','combo:'), ('judgment_event','judgment:')):
            if match.get(key) is not None:
                refs.append(prefix+str(match[key]))
        lo = match.get('observation_lower_seconds', match.get('combo_lower_seconds'))
        hi = match.get('observation_upper_seconds', match.get('combo_upper_seconds'))
        if lo is not None and hi is not None:
            refs += [run.get('id', 'receptor:'+str(i)) for i,run in enumerate(receptor_evidence(data))
                     if run['lane'] == data['notes'][ni]['lane'] and onset_overlaps(run, lo, hi, guard)]
            if processing_support(data, ni, lo, hi, guard):
                refs.append('processing:'+str(ni))
        match['visual_evidence'] = refs
        observed = next((e for e in processing_evidence(data) if e['note'] == ni), None)
        match['processing_status'] = observed['status'] if observed else 'unavailable'
        if observed and observed['status'] == 'disappeared_near_receptor' and lo is not None and hi is not None:
            match['processing_conflict'] = processing_conflicts(data, ni, lo, hi, guard)
        matches.append(match)
    return {**data, 'matches': matches}
