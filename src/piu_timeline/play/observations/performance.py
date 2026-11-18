"""Record inspection substeps without changing source evidence or cache identity."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from time import perf_counter


@contextmanager
def step(directory, name):
    path = directory/'inspection-performance.json'
    state = json.loads(path.read_text()) if path.is_file() else {'schema': 1, 'steps': {}}
    started = perf_counter()
    record = {'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat()}
    state['steps'][name] = record
    def save():
        pending = path.with_suffix('.pending-json')
        pending.write_text(json.dumps(state, indent=2)+'\n')
        pending.replace(path)
    save()
    try:
        yield
    except BaseException as error:
        record.update(status='failed', error=type(error).__name__+': '+str(error))
        raise
    else:
        record['status'] = 'complete'
    finally:
        record['elapsed_seconds'] = perf_counter()-started
        # Nested substeps may have updated the same journal.
        current = json.loads(path.read_text())
        current['steps'][name] = record
        state = current
        save()
