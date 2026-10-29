"""Prepare song timing and source audio alignment independently of UCS transcription."""
from hashlib import sha256
import fcntl
import json
from pathlib import Path

from piu_timeline.charts.official import Client,atomic_write,write_json

FORMAT={'schema':1,'method':'official_timing_with_source_audio_translation'}


def source(data):
    return {k:data[k]for k in ('media','start_seconds','end_seconds')}


def retained(data,directory,repository,code):
    """Read-only identity validation; never prepare missing reference media here."""
    path=Path(directory)/'song-reference.json'
    if not path.is_file()or not code:return None
    saved=json.loads(path.read_text());contract=saved.get('contract',{})
    if (contract.get('format')!=FORMAT or contract.get('source')!=source(data)
            or contract.get('ucs_index')!=code or saved.get('repository')!=str(Path(repository).resolve())):return None
    media=Path(data['media']['path'])
    if not media.is_file()or (media.stat().st_size,media.stat().st_mtime_ns)!=(data['media']['size_bytes'],data['media']['mtime_ns']):return None
    timing=Path(repository)/'timing'/f'{code}.ucs';audio=Path(saved['reference_audio'])
    if (not timing.is_file()or not audio.is_file()
            or sha256(timing.read_bytes()).hexdigest()!=contract['timing_sha256']
            or sha256(audio.read_bytes()).hexdigest()!=contract['reference_audio_sha256']):return None
    return saved


def prepare(data,directory,repository=None,client=None,code=None):
    from piu_timeline.charts.data import default_repository,resolve_code
    from piu_timeline.charts.localized import prepare as prepare_names
    from piu_timeline.charts.audio import prepare_alignment
    registration=Path(directory)/'chart-registration.json'
    assigned=json.loads(registration.read_text())if registration.is_file()else{}
    repository=Path(repository)if repository is not None else Path(assigned.get('repository',default_repository()))
    if not(repository/'catalog.json').is_file():raise ValueError('Official song catalogue is unavailable')
    code=resolve_code(repository,data.get('song'),code or assigned.get('index'))
    if code is None:
        prepare_names(repository);code=resolve_code(repository,data.get('song'))
    if code is None:raise ValueError('OCR song title has no unique official identity')
    old=retained(data,directory,repository,code)
    if old is not None:return old
    provider=client or Client();template,music,url=provider.template(code)
    timing=repository/'timing'/f'{code}.ucs';content=template.text().encode()
    with(repository/'.chart-data.lock').open('a')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if timing.is_file()and timing.read_bytes()!=content:
            raise ValueError('Saved official timing differs from the downloaded template; preserve and review it')
        if not timing.is_file():atomic_write(timing,content)
    alignment=prepare_alignment(data,Path(directory),{},code,client=provider)
    result={'contract':{'format':FORMAT,'source':source(data),'ucs_index':code,
                        'timing_sha256':sha256(content).hexdigest(),
                        'reference_audio_sha256':sha256(music.read_bytes()).hexdigest()},
            'repository':str(repository.resolve()),'reference_audio':str(music.resolve()),
            'official_timing_url':url,'alignment':alignment}
    write_json(Path(directory)/'song-reference.json',result)
    return result


def beat_reference(saved,repository,code):
    entries=json.loads((Path(repository)/'catalog.json').read_text())['songs']
    entry=next(e for e in entries if e['index']==code)
    return {'status':'available','ucs_index':code,'constant_tempo_bpm':entry.get('bpm'),
            'timing':str(Path(repository)/'timing'/f'{code}.ucs'),
            'sha256':saved['contract']['timing_sha256'],
            'song_start_seconds':saved['alignment']['song_start_seconds'],
            'alignment_uncertainty_seconds':saved['alignment']['uncertainty_seconds'],
            'reference_artifact':'song-reference.json'}
