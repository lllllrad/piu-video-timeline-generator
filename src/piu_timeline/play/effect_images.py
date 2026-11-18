"""Acquire source-bound receptor RGB; TypeScript owns image interpretation and links."""
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4

from piu_timeline import ROOT
from piu_timeline.play.frames import decode_frames


def select(data, reference=None, clear=False):
    if clear:
        data.pop('effect_reference', None)
    elif reference is not None:
        data['effect_reference'] = str(Path(reference).resolve())
    return data


def signature(path):
    path = Path(path)
    return [path.stat().st_size, path.stat().st_mtime_ns] if path.is_file() else None


def verify(data, path, *, geometry=True):
    reference = json.loads(path.read_text())
    if reference.get('schema') != 2:
        raise ValueError('Effect reference requires schema 2; regenerate RGB references')
    manifest_path = Path(reference['input'])
    if sha256(manifest_path.read_bytes()).hexdigest() != reference['capture_sha256']:
        raise ValueError('Effect reference capture changed')
    for name,digest in reference.get('implementation_sha256',{}).items():
        if name not in ('cli.ts','model.ts','io.ts','bank.ts','regions.ts','temporal.ts') or sha256((ROOT/'src/piu_timeline/derived/effect_references'/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Effect reference model changed; regenerate references')
    manifest = json.loads(manifest_path.read_text())
    match = re.search(r'segment-(\d+)', Path(manifest['segment']).name)
    if not match or int(match[1]) != data['segment_number']:
        raise ValueError('Effect reference belongs to another segment; skin compatibility is unverified')
    source = Path(data['media']['path'])
    stat = source.stat()
    expected = {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}
    if (Path(reference['source']).resolve() != source.resolve() or reference['source_identity'] != expected
            or manifest['source_identity'] != expected
            or (stat.st_size, stat.st_mtime_ns) != (data['media']['size_bytes'], data['media']['mtime_ns'])):
        raise ValueError('Effect reference/source recording identity differs')
    if not geometry:
        return reference
    if manifest.get('game_roi') is not None:
        if manifest['game_roi'] != data['game_roi'] or manifest['layout'] != data['layout']:
            raise ValueError('Effect reference game ROI or receptor layout differs')
    else:
        # Legacy experimental captures had no ROI field. Verify actual source RGB,
        # rather than guessing compatibility from a skin name or video identity.
        event = next((e for e in manifest['events'] if e['frames']), None)
        if event is None:
            raise ValueError('Effect reference has no original RGB frame')
        frame = event['frames'][0]
        x = round(data['layout']['lanes'][event['lane']]['x']*650)
        height = round(650*data['game_roi'][3]/data['game_roi'][2])
        y = round(data['layout']['receptor_y']*height)
        if frame['crop'] != [x-23, y-23, 47, 47]:
            raise ValueError('Effect reference receptor geometry differs')
        decoded = list(decode_frames(data['media'], frame['time'], frame['time']+.02, data['game_roi'], 650))
        exact = next((rgb for pts, time, rgb in decoded if abs(pts-frame['pts']) < 1e-6 and abs(time-frame['time']) < 1e-6), None)
        with (manifest_path.parent/'pixels.rgb').open('rb') as stream:
            stream.seek(frame['offset']*47*47*3)
            original = stream.read(47*47*3)
        if exact is None or exact[y-23:y+24, x-23:x+24].tobytes() != original:
            raise ValueError('Legacy effect reference pixels do not match this game ROI')
    return reference


def augment(data, directory):
    path = data.get('effect_reference')
    if not path:
        data.pop('effect_images', None)
        data.get('visual_channels', {}).pop('effect_images', None)
        for note in data.get('notes',[]):note.pop('effect_image_candidates',None)
        for match in data.get('matches',[]):match.pop('effect_image_corroboration',None)
        return None
    path = Path(path).resolve()
    verify(data, path)
    from piu_timeline.play.observations.artifacts import producer
    note_input = 'visual-channels.json' if (directory/'visual-channels.json').is_file() else 'frames.jsonl'
    acquisition = {'media': data['media'], 'game_roi': data['game_roi'], 'layout': data['layout'],
                   'traces': {name: signature(directory/name) for name in (note_input, 'hold-frames.jsonl')},
                   'producer': producer('tools/effect_capture.py', 'play/frames.py')}
    target = directory/'effect-images'
    target.mkdir(exist_ok=True)
    capture = target/'acquisition'
    key_path = target/'acquisition-key.json'
    saved = json.loads(key_path.read_text()) if key_path.is_file() else None
    if saved != acquisition or not (capture/'capture.json').is_file():
        from piu_timeline.tools.effect_capture import capture as acquire
        pending = target/('.acquisition-'+uuid4().hex)
        try:
            print('Acquiring RGB for all receptor light candidates; no OCR.', flush=True)
            acquire(directory, pending, None, data=data)
            if capture.exists():
                shutil.rmtree(capture)
            pending.rename(capture)
            key_path.write_text(json.dumps(acquisition, sort_keys=True)+'\n')
        finally:
            if pending.exists():
                shutil.rmtree(pending)
    request = link_input(data)
    request_path = target/'play-input.json'
    request_path.write_text(json.dumps(request, ensure_ascii=False)+'\n')
    print('Matching play RGB against source-bound effect references.', flush=True)
    try:
        subprocess.run(['node', str(ROOT/'src/piu_timeline/derived/effect_references/play.ts'),
                    str(path), str(capture/'capture.json'), str(request_path), str(target)],
                       check=True, cwd=ROOT)
    except subprocess.CalledProcessError as error:
        raise ValueError('Effect image analysis failed; original play timings remain unchanged') from error
    summary = json.loads((target/'summary.json').read_text())
    relations = json.loads((target/'associations.json').read_text())['associations']
    data['effect_images'] = summary
    data.setdefault('visual_channels', {})['effect_images'] = {**summary, 'available': True}
    from piu_timeline.play.channels import layer_manifest
    data['visual_channels']['layers']=layer_manifest(directory)
    candidates, corroboration = {}, {}
    for relation in relations:
        for index in {c['note'] for c in relation['candidates']}:
            candidates.setdefault(index, []).append(relation['event'])
        if relation['status'] == 'unique_tap_image_candidate':
            index = relation['candidates'][0]['note']
            corroboration.setdefault(index, []).append(relation['event'])
    for i, note in enumerate(data.get('notes', [])):
        note['effect_image_candidates'] = candidates.get(i, [])
    for match in data.get('matches', []):
        match['effect_image_corroboration'] = corroboration.get(match['note'], [])
    return summary


def link_input(data):
    """Pass association fields only; native image evidence stays in acquisition."""
    def fields(record, names):
        return {key: record[key] for key in names if key in record}
    notes = []
    for note in data.get('notes', []):
        value = fields(note, ('lane', 'note_type', 'visible_start_seconds', 'visible_end_seconds'))
        points = note.get('points') or []
        if points:
            value['points'] = [points[0], points[-1]]
        notes.append(value)
    holds = data.get('hold_analysis') or {}
    return {'notes': notes,
            'judgment_events': [fields(event, ('lower_seconds', 'upper_seconds', 'label'))
                                for event in data.get('judgment_events', [])],
            'hold_analysis': {'holds': [fields(hold, ('lane', 'start_range', 'end_range'))
                                        for hold in holds.get('holds', [])],
                              'unresolved_tracks': [fields(track, ('lane', 'visible_start_seconds', 'end_range'))
                                                    for track in holds.get('unresolved_tracks', [])]},
            'visual_channels': {'processing': {'notes': [fields(note, ('note', 'status')) for note in
                                 data.get('visual_channels', {}).get('processing', {}).get('notes', [])]}}}
