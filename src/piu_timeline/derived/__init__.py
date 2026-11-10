"""Transport only: saved-data algorithms are implemented in adjacent TypeScript modules."""
import atexit
import json
import os
from pathlib import Path
import subprocess
import threading

_ROOT = Path(__file__).parent
CONTRACTS = json.loads((_ROOT / 'contracts.json').read_text())
for _name in ('timing','recovery','transcription'):CONTRACTS[_name]['natural_splits']=CONTRACTS['natural_splits']
CONTRACTS['image_coordinates']['native_cap_registration']=CONTRACTS['native_anchor']
CONTRACTS['shared_motion']['local_clock']=CONTRACTS['local_clock']
CONTRACTS['chords'].update(native_cap_registration=CONTRACTS['native_anchor'],image_coordinates=CONTRACTS['image_coordinates'])
for _name in ('domains','recovery'):CONTRACTS[_name]['measurement_limits']=CONTRACTS['coordinates']
CONTRACTS['native_clock']['render_clock']=CONTRACTS['render_clock']
CONTRACTS['timing'].update(clock_conversion=CONTRACTS['clock_conversion'],render_clock=CONTRACTS['render_clock'],spacing_checks=CONTRACTS['spacing'],
    independent_coordinates=CONTRACTS['coordinates'],native_chords=CONTRACTS['chords'],
    native_row_domains=CONTRACTS['domains'],native_recovery=CONTRACTS['recovery'],
    native_gap_validation=CONTRACTS['native_gap_validation'])
_process = None
_owner = None
_sequence = 0
_lock = threading.Lock()


def _json_default(value):
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f'Unsupported analysis input: {type(value).__name__}')


def evidence_input(data):
    """Only the retained evidence a range/association consumer actually reads."""
    keys=('notes','matches','conflicted_matches','miss_candidates','combo_events','judgment_events',
          'counter_frame_events','display_delay_correction_ms','median_frame_interval_seconds',
          'chart_policy','unsupported_intervals','coverage')
    result={key:data[key]for key in keys if key in data}
    result['hold_analysis']={key:data['hold_analysis'][key]for key in ('holds','receptor_runs','unresolved_tracks')
                             if key in data.get('hold_analysis',{})}
    channels=data.get('visual_channels',{})
    result['visual_channels']={key:{field:channels[key][field]}
                               for key,field in (('receptors','events'),('processing','notes'))if key in channels}
    return result


def recovery_input(data):
    from piu_timeline.play.holds.input_risk import native_body_risk_available
    return {**evidence_input(data),'native_body_risk_available':native_body_risk_available(data)}


def projection_input(data):
    fields=('notes','hold_analysis','skin_detector')
    result={k:data[k]for k in fields if k in data}
    result['visual_channels']={k:v for k,v in data.get('visual_channels',{}).items()if k in ('note_types','timeline')}
    return result


def close():
    global _process
    if _process is not None and _owner == os.getpid():
        _process.stdin.close()
        try:
            _process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _process.terminate()
            _process.wait()
        _process.stdout.close()
    _process = None


atexit.register(close)


def call(operation, *args):
    """Keep one Node worker per acquisition process; errors never select a fallback."""
    global _process, _owner, _sequence
    with _lock:
        if _process is None or _owner != os.getpid() or _process.poll() is not None:
            _process = subprocess.Popen(['node', str(_ROOT / 'runtime.ts')],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1)
            _owner = os.getpid()
        _sequence += 1
        identity = _sequence
        def send(message):
            _process.stdin.write(json.dumps(message, default=_json_default, ensure_ascii=False, allow_nan=False)+'\n')
            _process.stdin.flush()
        send({'protocol':1,'id':identity,'operation':operation,'args':args})
        line = _process.stdout.readline()
        if not line:
            raise RuntimeError(f'TypeScript analysis worker exited during {operation}')
        reply = json.loads(line)
        if reply.get('id') != identity:
            raise RuntimeError('Mismatched TypeScript analysis response')
        if reply['kind'] == 'error':
            raise ValueError(f'{operation}: {reply["error"]}')
        if reply['kind'] != 'result':
            raise RuntimeError('Unexpected TypeScript analysis response kind')
        return reply['value']
