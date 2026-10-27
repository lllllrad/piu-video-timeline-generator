"""Apply a selected RGB image bank while preserving source counter observations."""
import json
from pathlib import Path
import shutil
from itertools import zip_longest

from piu_timeline.play.frames import decode_frames
from piu_timeline.play.skins.bank import load_bank, ROLES
from piu_timeline.play.skins.detector import SkinDetector, FORMAT


def detector_contract(path):
    return None if path is None else {'bank': load_bank(path)['contract'], 'detector': FORMAT}


def detector_metadata(path, bank=None):
    bank = bank or load_bank(path)
    represented = {(t['lane_kind'], t['role']) for t in bank['templates']}
    return {'contract': {'bank': bank['contract'], 'detector': FORMAT},
            'bank_path': str(Path(path).resolve()), 'registration_reviewed': False,
            'reference_images': len(bank['templates']),
            'missing_template_roles': [{'lane_kind': lane, 'role': role}
                                       for lane in range(5) for role in ROLES if (lane, role) not in represented]}


def selected_bank(directory, segment, explicit=None):
    if explicit is not None:
        return str(Path(explicit).resolve())
    path = directory / 'note-skins.json'
    if not path.is_file():
        return None
    document = json.loads(path.read_text())
    if document.get('schema') != 1:
        raise ValueError('Unsupported source note-skin selection schema')
    matches = [p for p in document['profiles'] if segment in p['segments']]
    if len(matches) > 1:
        raise ValueError('More than one note skin is selected for this play')
    if not matches:
        return None
    return str((path.parent / matches[0]['bank']).resolve())


def refresh(data, output, path):
    """A detector change rescans RGB, never reuses old contour detections as input."""
    bank = load_bank(path)
    detector = SkinDetector(bank, data['layout'], data['analysis_width'], data['analysis_height'])
    before = Path(data['media']['path']).stat()
    if (before.st_size, before.st_mtime_ns) != (data['media']['size_bytes'], data['media']['mtime_ns']):
        raise ValueError('Skin replay source no longer matches its acquisition identity')
    trace = output / 'frames.jsonl'
    backup = output / 'frames.outline.jsonl'
    if not backup.exists():
        shutil.copy2(trace, backup)
    target = output / 'frames.skin-build.jsonl'
    decoded = decode_frames(data['media'], data['start_seconds'], data['end_seconds'],
                            data['game_roi'], data['analysis_width'])
    count = 0
    with trace.open() as source, target.open('w') as stream:
        for line, frame in zip_longest(source, decoded):
            if line is None or frame is None:
                raise ValueError('Skin image replay differs from native frame count')
            native = json.loads(line)
            pts, time, rgb = frame
            if abs(pts - native['source_pts_seconds']) > 1e-6 or abs(time - native['playback_seconds']) > 1e-6:
                raise ValueError('Skin image replay differs from original PTS')
            observations = detector.detect(rgb)
            native.update(notes=[o for o in observations if o['role'] != 'hold_body'],
                          skin_observations=observations,
                          possible_hold_or_dense_stack=any(o['role'] == 'hold_body' for o in observations))
            stream.write(json.dumps(native) + '\n')
            count += 1
            if count % 600 == 0:
                print(f'  Skin image replay: {time-data["start_seconds"]:.1f}s', flush=True)
    after = Path(data['media']['path']).stat()
    if count != data['frame_count'] or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Source identity or native frame count changed during skin replay')
    target.replace(trace)
    shutil.copy2(trace, output / 'frames.base.jsonl')
    return detector_metadata(path, bank)
