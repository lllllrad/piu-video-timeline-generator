"""Relocate nested evidence references when promoting a saved analysis."""
import json
import re
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
        manifest=None
        path=directory/'analysis.json'
        try:
            with path.open()as stream:
                before=path.stat()
                document=json.load(stream)
            after=path.stat()
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                raise ValueError('Analysis manifest changed during validation')
            if isinstance(document,dict):
                manifest={'size_bytes':after.st_size,'mtime_ns':after.st_mtime_ns}
            del document
        except (FileNotFoundError,json.JSONDecodeError):
            pass
        return call('retention.prune',str(directory.absolute()),
                    str(previous.absolute())if previous and previous.is_dir()else None,protected,manifest)


def relocate_evidence(directory, destination, source=None):
    """Promotion must preserve every image/JSON evidence link, including nested OCR."""
    prefix = str((source or directory).resolve()) + "/"
    replacement = str(destination.resolve()) + "/"
    if prefix==replacement:return
    # Touch only complete JSON string values beginning with this directory.
    # Large numerical observations must not be parsed and serialized again.
    prefixes={json.dumps(prefix,ensure_ascii=ascii)[:-1]for ascii in (True,False)}
    pattern=re.compile(r'(?<!\\)(?:'+'|'.join(re.escape(p)for p in prefixes)+r')(?:[^"\\]|\\.)*"(?!\s*:)')
    def relocate(match):
        value=json.loads(match.group())
        return json.dumps(replacement+value[len(prefix):],ensure_ascii=False)
    for path in directory.rglob("*.json"):
        text=path.read_text(encoding='utf-8')
        if not any(p in text for p in prefixes):continue
        updated=pattern.sub(relocate,text)
        if updated==text:continue
        temporary=path.with_name(path.name+'.relocate-build')
        try:
            temporary.write_text(updated,encoding='utf-8')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def read_analysis_header(path):
    """Read acquisition metadata without loading every saved note trajectory."""
    parts=[]
    with path.open() as stream:
        for line in stream:
            if line.startswith('  "notes":'):
                return json.loads(''.join(parts).rstrip().rstrip(',')+'}')
            parts.append(line)
    return json.loads(''.join(parts))

