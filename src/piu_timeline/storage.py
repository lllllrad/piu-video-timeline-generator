"""Relocate nested evidence references when promoting a saved analysis."""
import json
from contextlib import contextmanager
import fcntl


@contextmanager
def history_guard(directory, shared=False):
    """Snapshot selection/copy and pruning coordinate through the same parent lock."""
    with (directory / '.retention.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        yield


def prune_history(directory, previous=None, media=None):
    """Bound saved versions only after success, while the caller owns its writer lock."""
    from piu_timeline.derived import call
    protected=[media['path']]if media and media.get('path')else[]
    with history_guard(directory.parent):
        return call('retention.prune',str(directory.absolute()),
                    str(previous.absolute())if previous and previous.is_dir()else None,protected)


def relocate_evidence(directory, destination, source=None):
    """Promotion must preserve every image/JSON evidence link, including nested OCR."""
    prefix = str((source or directory).resolve()) + "/"
    replacement = str(destination.resolve()) + "/"
    def relocate(value):
        if isinstance(value, str):
            return replacement + value[len(prefix):] if value.startswith(prefix) else value
        if isinstance(value, list):
            return [relocate(item) for item in value]
        if isinstance(value, dict):
            return {key: relocate(item) for key, item in value.items()}
        return value
    for path in directory.rglob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(relocate(value), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_analysis_header(path):
    """Read acquisition metadata without loading every saved note trajectory."""
    parts=[]
    with path.open() as stream:
        for line in stream:
            if line.startswith('  "notes":'):
                return json.loads(''.join(parts).rstrip().rstrip(',')+'}')
            parts.append(line)
    return json.loads(''.join(parts))

