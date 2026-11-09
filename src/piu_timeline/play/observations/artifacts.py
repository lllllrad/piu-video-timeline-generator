"""Atomic, source-bound native measurement artifacts, independent of consumers."""
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from piu_timeline.play.stages import fingerprint, paths


def files(directory, names):
    return {name: [path.stat().st_size, path.stat().st_mtime_ns] if (path := directory/name).is_file() else None
            for name in names}



_file_identities={}


def file_identities(directory,names):
    """Hash existing serialized bytes without parsing or serializing their values."""
    result={}
    for name in names:
        path=directory/name;before=path.stat()
        key=(str(path.resolve()),str(directory.resolve()),before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)
        if key in _file_identities:
            result[name]=dict(_file_identities[key]);continue
        digest=sha256();size=0;pending=b''
        prefix=json.dumps(str(directory.resolve())+'/',ensure_ascii=False)[:-1].encode();replacement=b'"@segment/'
        with path.open('rb')as stream:
            while True:
                block=stream.read(1024*1024);pending+=block
                cut=max(0,len(pending)-len(prefix)+1)if block else len(pending)
                start=0
                while True:
                    match=pending.find(prefix,start)
                    if match<0 or match>=cut:break
                    part=pending[start:match];digest.update(part);size+=len(part)
                    digest.update(replacement);size+=len(replacement)
                    start=match+len(prefix);cut=max(cut,start)
                part=pending[start:cut];digest.update(part);size+=len(part);pending=pending[cut:]
                if not block:break
        after=path.stat()
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            raise ValueError('Serialized artifact changed while reading')
        result[name]={'size_bytes':size,'sha256':digest.hexdigest()}
        if len(_file_identities)>=128:_file_identities.clear()
        _file_identities[key]=dict(result[name])
    return result

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
        if name=='hold-geometry' and saved.get('derived') is not None:
            from piu_timeline.play.holds.stages import image_geometry_contract
            if saved['derived']!=image_geometry_contract():
                return False
        if name in ('processing', 'configured-processing'):
            from piu_timeline.play.observations.channel_stages import derived_motion_contract
            if saved.get('derived') != derived_motion_contract():
                return False
    return True
