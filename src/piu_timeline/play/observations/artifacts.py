"""Atomic, source-bound native measurement artifacts, independent of consumers."""
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from piu_timeline.play.stages import fingerprint, paths


def files(directory, names):
    return {name: [path.stat().st_size, path.stat().st_mtime_ns] if (path := directory/name).is_file() else None
            for name in names}


def producer(*modules):
    root = Path(__file__).parents[2]
    return {name: sha256((root/name).read_bytes()).hexdigest() for name in modules}


def save_input(path, value):
    temporary = path.with_name(f'.{path.name}.{uuid4().hex}.tmp')
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)+'\n'
    try:
        temporary.write_text(encoded)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def cached(directory, name, inputs, compute):
    """A changed input rebuilds only this producer; damaged output fails explicitly."""
    prefix = str(directory.resolve())+'/'
    key = fingerprint(paths(inputs, prefix, '@segment/'))
    target = directory/'native-stages'/f'{name}.json'
    if target.is_file():
        saved = json.loads(target.read_text())
        if saved.get('schema') != 1 or saved.get('stage') != name:
            raise ValueError(f'Invalid native stage artifact: {name}')
        if fingerprint(saved['output']) != saved.get('output_fingerprint'):
            raise ValueError(f'Corrupt native stage artifact: {name}')
        if saved['input_fingerprint'] == key:
            return paths(saved['output'], '@segment/', prefix)
    output = compute()
    normalized = json.loads(json.dumps(paths(output, prefix, '@segment/'), ensure_ascii=False, allow_nan=False))
    artifact = {'schema': 1, 'stage': name, 'input_fingerprint': key,
                'producer': inputs.get('producer', {}), 'derived': inputs.get('derived'),
                'output_fingerprint': fingerprint(normalized), 'output': normalized}
    target.parent.mkdir(exist_ok=True)
    temporary = target.with_name(f'.{name}.{uuid4().hex}.tmp')
    try:
        temporary.write_text(json.dumps(artifact, ensure_ascii=False, allow_nan=False)+'\n')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return paths(normalized, '@segment/', prefix)


def current(directory, names):
    """Read-only producer/integrity check for maintenance scheduling."""
    for name in names:
        path = directory/'native-stages'/f'{name}.json'
        if not path.is_file():
            return False
        saved = json.loads(path.read_text())
        if saved.get('schema') != 1 or saved.get('stage') != name or fingerprint(saved['output']) != saved.get('output_fingerprint'):
            raise ValueError(f'Corrupt native stage artifact: {name}')
        sources = saved.get('producer', {})
        if not sources or producer(*sources) != sources:
            return False
        if name in ('processing', 'configured-processing'):
            from piu_timeline.play.observations.channel_stages import derived_motion_contract
            if saved.get('derived') != derived_motion_contract():
                return False
    return True
