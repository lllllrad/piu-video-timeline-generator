"""Versioned RGB reference assets in the separate editable data repository."""
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import re
import shutil
import tempfile

from piu_timeline.play.skins.bank import load_bank


STATUSES = ('experimental', 'reviewed', 'unsupported')


def repository_root(repository=None):
    from piu_timeline.charts.data import default_repository
    return Path(repository if repository is not None else default_repository()).resolve()


def component(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9._-]*', value):
        raise ValueError('Skin identities, revisions and source IDs need safe path components')
    return value


def bank_path(repository, skin, revision):
    root = repository_root(repository)
    path = root / 'skins/banks' / component(skin) / component(revision) / 'bank.json'
    if not path.resolve().is_relative_to(root):
        raise ValueError('Skin reference must stay inside the data repository')
    return path


def profile_path(repository, source):
    root = repository_root(repository)
    path = root / 'skins/sources' / (component(source) + '.json')
    if not path.resolve().is_relative_to(root):
        raise ValueError('Skin profile must stay inside the data repository')
    return path


def role_model(path, bank=None):
    """Read a bank-bound interpretation policy independently of image pixels."""
    path=Path(path);configuration=path.with_name('roles.json')
    if not configuration.is_file():return None
    saved=json.loads(configuration.read_text());bank=bank or load_bank(path)
    if saved.get('schema')!=1 or saved.get('bank_contract')!=bank['contract']:
        raise ValueError('Skin role model differs from its image bank')
    profile=saved.get('clearance')
    from piu_timeline.play.skins.clearance import FORMAT
    if profile!={'model':FORMAT['model'],'skin':bank['contract'].get('skin')}:
        raise ValueError('Unsupported skin role model')
    return profile


def validate_bank(path):
    """Check native image geometry and the published revision's content binding."""
    path = Path(path)
    bank = load_bank(path)
    reference = json.loads((path.parent / 'reference.json').read_text())
    if (reference.get('schema') != 1 or reference.get('skin') != bank['skin']
            or path.parent.parent.name != bank['skin']
            or reference.get('revision') != path.parent.name
            or reference.get('status') not in STATUSES
            or reference.get('contract') != bank['contract']):
        raise ValueError(f'Skin revision identity or content changed: {path}')
    role_model(path,bank)
    return reference


def resolve(selection, repository=None):
    if not isinstance(selection, dict) or set(selection) != {'skin', 'revision'}:
        raise ValueError('A repository skin selection requires exactly skin and revision')
    path = bank_path(repository, selection['skin'], selection['revision'])
    reference = validate_bank(path)
    if reference['status'] == 'unsupported':
        raise ValueError('Selected skin revision is marked unsupported')
    return path


@contextmanager
def locked(repository):
    root = repository_root(repository)
    if not (root / '.git').exists():
        raise ValueError('Initialize the separate data repository with just charts init first')
    with (root / '.chart-data.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield root


def publish(source, revision, repository=None, status='experimental', description=''):
    """Copy only referenced images and exact bank bytes; never replace a revision."""
    if status not in STATUSES:
        raise ValueError('Unsupported skin review status')
    source = Path(source).resolve()
    bank = load_bank(source)
    destination = bank_path(repository, bank['skin'], revision)
    with locked(repository):
        if destination.parent.exists():
            existing = validate_bank(destination)
            if (existing['contract'] != bank['contract'] or existing['status'] != status
                    or existing.get('description', '') != description):
                raise ValueError('Skin revision already exists; use a new revision')
            return destination
        destination.parent.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.publish-', dir=destination.parent.parent) as temporary:
            staging = Path(temporary) / bank['skin'] / revision
            staging.mkdir(parents=True)
            document = json.loads(source.read_text())
            for entry in document['templates']:
                relative = Path(entry['image'])
                if relative.is_absolute() or '..' in relative.parts or relative.suffix.lower() != '.png':
                    raise ValueError('Published skin images require relative PNG paths')
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source.parent / relative, target)
            shutil.copyfile(source, staging / 'bank.json')
            if load_bank(staging / 'bank.json')['contract'] != bank['contract']:
                raise ValueError('Skin bank changed during publication')
            reference = {'schema': 1, 'skin': bank['skin'], 'revision': revision,
                         'status': status, 'description': description, 'contract': bank['contract']}
            (staging / 'reference.json').write_text(json.dumps(reference, indent=2) + '\n')
            validate_bank(staging / 'bank.json')
            staging.rename(destination.parent)
    return destination


def select(source, segments, skin, revision, repository=None):
    if not segments or any(type(n) is not int or n < 1 for n in segments):
        raise ValueError('Skin selection needs positive segment numbers')
    selection = {'skin': skin, 'revision': revision}
    path = profile_path(repository, source)
    with locked(repository):
        resolve(selection, repository)
        document = json.loads(path.read_text()) if path.exists() else {'schema': 1, 'profiles': []}
        if document.get('schema') != 1:
            raise ValueError('Unsupported source note-skin selection schema')
        profiles = []
        assigned = set()
        for profile in document['profiles']:
            unchanged = profile['bank'] == selection
            remaining = [n for n in profile['segments'] if unchanged or n not in segments]
            if unchanged:
                assigned.update(remaining)
            if remaining:
                profiles.append({**profile, 'segments': remaining})
        added = sorted(set(segments) - assigned)
        if added:
            profiles.append({'segments': added, 'bank': selection})
        document['profiles'] = profiles
        from piu_timeline.charts.official import write_json
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, document)
    return path


def inventory(repository=None):
    return [validate_bank(path) for path in sorted(repository_root(repository).glob('skins/banks/*/*/bank.json'))]


def validate(repository=None):
    banks = inventory(repository)
    profiles = list(repository_root(repository).glob('skins/sources/*.json'))
    for path in profiles:
        document = json.loads(path.read_text())
        if document.get('schema') != 1:
            raise ValueError(f'Unsupported skin profile schema: {path}')
        seen = set()
        for profile in document['profiles']:
            segments = profile['segments']
            if (not segments or any(type(n) is not int or n < 1 for n in segments)
                    or len(set(segments)) != len(segments) or seen.intersection(segments)):
                raise ValueError(f'Invalid or overlapping skin segments: {path}')
            seen.update(segments)
            resolve(profile['bank'], repository)
    from piu_timeline.play.skins.automatic import candidates
    candidates(repository)
    return {'banks': len(banks), 'sources': len(profiles)}
