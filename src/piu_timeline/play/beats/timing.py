"""Fit natural UCS subdivisions with explicit ambiguity and failure states."""
from hashlib import sha256
import json
import subprocess
from pathlib import Path
from piu_timeline.derived import CONTRACTS, call

FORMAT=CONTRACTS['timing']


def reference(data, directory):
    from piu_timeline.charts.data import default_repository, resolve_code
    from piu_timeline.charts.gimmicks import known_origin
    directory=Path(directory);repo=default_repository();registration=directory/'chart-registration.json'
    saved=json.loads(registration.read_text()) if registration.is_file() else {}
    if saved.get('repository'):repo=Path(saved['repository'])
    code=saved.get('index') or (resolve_code(repo,data.get('song')) if (repo/'catalog.json').is_file() else None)
    from piu_timeline.charts.reference import retained,beat_reference
    retained_reference=retained(data,directory,repo,code)
    if retained_reference is not None:return beat_reference(retained_reference,repo,code)
    chart=Path(saved['chart']) if saved.get('chart') else repo/'charts'/str(code)/str(data.get('chart'))/'phoenix/chart.ucs'
    metadata=chart.with_name('metadata.json');timing=repo/'timing'/f'{code}.ucs'
    if not code or not metadata.is_file() or not timing.is_file():
        return {'status':'unavailable','reason':'official_timing_or_chart_identity_missing'}
    meta=json.loads(metadata.read_text());origin=known_origin(data,directory,meta)
    explicit=saved.get('alignment',{})
    if explicit.get('method')=='explicit_song_start' and saved.get('alignment_media')==data.get('media'):
        origin=explicit['song_start_seconds']
    if origin is None:return {'status':'unavailable','reason':'verified_song_alignment_missing','ucs_index':code,
                              'metadata_path':str(metadata),'timing':str(timing),'sha256':sha256(timing.read_bytes()).hexdigest()}
    alignment=explicit if explicit.get('method')=='explicit_song_start' and saved.get('alignment_media')==data.get('media') else meta.get('alignment',{})
    uncertainty=alignment.get('uncertainty_seconds',0)
    cached=directory/'chart-policy-alignment.json'
    if cached.is_file():
        saved_alignment=json.loads(cached.read_text())
        if saved_alignment.get('contract',{}).get('media')==data.get('media') and saved_alignment.get('alignment',{}).get('song_start_seconds')==origin:
            alignment=saved_alignment['alignment']
            uncertainty=saved_alignment['alignment'].get('uncertainty_seconds',uncertainty)
    catalogue=repo/'catalog.json'
    entries=json.loads(catalogue.read_text()).get('songs',[]) if catalogue.is_file() else []
    bpm=next((entry.get('bpm') for entry in entries if entry['index']==code),None)
    return {'status':'available','ucs_index':code,'constant_tempo_bpm':bpm,'timing':str(timing),'sha256':sha256(timing.read_bytes()).hexdigest(),
            'alignment_method':alignment.get('method'),
            'song_start_seconds':origin,'alignment_uncertainty_seconds':uncertainty}


def current(data,directory):
    return data.get('beat_timing',{}).get('contract')=={'format':FORMAT,'reference':reference(data,directory)}


def prepare_reference(data,directory):
    """Prepare audio-only alignment before beat inference, without policy gates.

    Reference/current checks remain read-only. Failed preparation is retained
    as a diagnostic on this build, not retried by a cache-current check.
    """
    ref=reference(data,directory)
    if ref.get('reason')=='official_timing_or_chart_identity_missing':
        from piu_timeline.charts.reference import prepare
        try:
            prepare(data,Path(directory))
        except (OSError,ValueError,KeyError,subprocess.SubprocessError)as error:
            return {'status':'failed','reason':str(error)}
        return {'status':'prepared','method':'official_song_reference'}
    if ref.get('reason')!='verified_song_alignment_missing':return None
    from piu_timeline.charts.audio import prepare_alignment
    try:
        prepare_alignment(data,Path(directory),json.loads(Path(ref['metadata_path']).read_text()),ref['ucs_index'])
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        return {'status':'failed','reason':str(error)}
    return {'status':'prepared','method':'reference_audio_translation'}


def validate_physical(data,directory):
    """Consume saved coordinate/physical artifacts; control flow carries no arrays."""
    call('timingFiles.native',str(Path(directory).resolve()))
    return data


def prepare_input(data,directory):
    """External reference preparation owns I/O; beat inference receives file references."""
    preparation=prepare_reference(data,directory)
    from piu_timeline.play.observations.artifacts import save_input
    save_input(Path(directory)/'beat-reference.json',{'schema':1,'reference':reference(data,directory),'preparation':preparation})
    call('beatFiles.prepare',str(Path(directory).resolve()))
    return data


def apply(data,directory):
    """Calculate from persisted dependencies, then load the downstream read model once."""
    from piu_timeline.play.stages import read_view
    call('beatFiles.calculate',str(Path(directory).resolve()))
    reference=call('beatFiles.view',str(Path(directory).resolve()))
    return {**data,**read_view(reference,Path(directory))}


def reassociate(data, display_delay_ms, directory=None):
    """Associate once the final timing view is available, including native-only results."""
    from types import SimpleNamespace
    from piu_timeline.play.associations import associate_counters
    from piu_timeline.play.frames import TIME_EPSILON
    events=[{**e,'status':'candidate' if 1<=e['delta']<=10 and e['upper_seconds']-e['lower_seconds']<=.1+TIME_EPSILON else 'excluded'}
            for e in data['combo_events']]
    return associate_counters(data,SimpleNamespace(events=events,observations=data.get('counter_observations',[])),display_delay_ms,directory)
