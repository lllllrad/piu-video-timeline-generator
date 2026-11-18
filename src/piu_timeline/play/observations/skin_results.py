"""Publish resolved image results; comparison searches are separate native evidence."""
from copy import deepcopy
import gzip
from hashlib import sha256
import json
from pathlib import Path

FORMAT = {'schema': 1, 'positions': 'resolved_before_tracking', 'roles': 'explicit_conflict_or_result'}


def publish(frame, directory, centers):
    """Consume all comparisons once; never send search lists into tracking."""
    from piu_timeline.play.skins.views import role_image
    images = frame['skin_observations']
    notes = [image for image in images if image['role'] != 'hold_body']
    positions = centers.positions(notes)
    payload = {'source_pts_seconds': frame['source_pts_seconds'],
               'playback_seconds': frame['playback_seconds'], 'skin_observations': images}
    encoded = json.dumps(payload, separators=(',', ':'), allow_nan=False).encode()
    digest = sha256(encoded).hexdigest()
    relative = Path('comparison-evidence')/(digest+'.json.gz')
    path = directory/relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        temporary = path.with_suffix('.pending')
        temporary.write_bytes(gzip.compress(encoded, compresslevel=1, mtime=0))
        temporary.replace(path)
    projected = []
    for image in images:
        view = role_image(image)
        roles = view.pop('alternatives', [])
        view['role_results'] = roles
        projected.append(view)
    compact = []
    for image, position in zip(notes, positions, strict=True):
        result = {key: image[key] for key in ('lane', 'x', 'y', 'quality', 'role', 'template',
                                             'classification_status', 'method') if key in image}
        result['position_result'] = position
        result['position_contract'] = centers.bank['contract']
        compact.append(result)
    return {**frame, 'notes': compact, 'skin_observations': projected, 'frame_result_format': FORMAT,
            'comparison_evidence': {'path': relative.as_posix(), 'sha256': digest}}


def restore(frame, directory):
    """Explicit native remeasurement only; ordinary consumers use published results."""
    reference = frame.get('comparison_evidence')
    if reference is None:
        return frame
    root = Path(directory).resolve()
    path = (root/reference['path']).resolve()
    if not path.is_relative_to(root) or path.suffix != '.gz':
        raise ValueError('Comparison evidence must stay within the play directory')
    encoded = gzip.decompress(path.read_bytes())
    if sha256(encoded).hexdigest() != reference['sha256']:
        raise ValueError('Corrupt native comparison evidence')
    payload = json.loads(encoded)
    if any(payload[key] != frame[key] for key in ('source_pts_seconds', 'playback_seconds')):
        raise ValueError('Comparison evidence belongs to another native frame')
    images = payload['skin_observations']
    return {**frame, 'skin_observations': images,
            'notes': [image for image in images if image['role'] != 'hold_body']}


def positions(images, bank):
    """Return independently measured positions, with source-bank identity checked."""
    if not images or not all('position_result' in image for image in images):
        return None
    if any(image.get('position_contract') != bank['contract'] for image in images):
        raise ValueError('Resolved image positions belong to another bank')
    for image in images:
        measured = image['position_result'].get('measurement', {})
        if measured.get('template') != image.get('template') or measured.get('image_anchor') != [image['x'], image['y']]:
            raise ValueError('Resolved image position differs from its published image')
    return [deepcopy(image['position_result']) for image in images]
