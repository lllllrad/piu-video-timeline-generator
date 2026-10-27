"""Estimate speed ratios from saved registered motion; optionally append chart effects."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path

from piu_timeline import ROOT
from piu_timeline.charts.data import default_repository
from piu_timeline.charts.speed_effects import proposals, record
from piu_timeline.charts.official import write_json
from piu_timeline.play.speed_estimation import estimate


def recording_alignment(data, directory, metadata, path):
    """Read only a verified translation belonging to this exact recording."""
    source=metadata['source'];media=data['media'];code=metadata['identity']['ucs_index']
    if (source['source_id']==directory.parents[1].name and source['segment_number']==data['segment_number']
            and (source['media_size_bytes'],source['media_mtime_ns'])==(media['size_bytes'],media['mtime_ns'])):
        return metadata['alignment']
    registration=directory/'chart-registration.json'
    saved=json.loads(registration.read_text()) if registration.is_file() else {}
    if (saved.get('index')!=code or not saved.get('chart')
            or Path(saved['chart']).with_name('metadata.json').resolve()!=path.resolve()
            or data.get('chart') is not None and metadata['identity'].get('chart') is not None
            and data['chart']!=metadata['identity']['chart']):
        raise ValueError('Recording is not registered to this chart')
    if saved.get('alignment',{}).get('method')=='explicit_song_start' and saved.get('alignment_media')==media:
        return saved['alignment']
    cached=directory/'chart-policy-alignment.json'
    if not cached.is_file():raise ValueError('Verified recording-specific alignment is missing')
    saved=json.loads(cached.read_text());contract=saved.get('contract',{})
    from piu_timeline.charts.official import DEFAULT_CACHE
    reference=DEFAULT_CACHE/f'{code}.mp3'
    if (contract.get('media')!=media or contract.get('start_seconds')!=data['start_seconds']
            or contract.get('end_seconds')!=data['end_seconds'] or contract.get('ucs_index')!=code
            or not reference.is_file() or contract.get('reference_audio_sha256')!=sha256(reference.read_bytes()).hexdigest()):
        raise ValueError('Recording-specific alignment source or reference changed')
    alignment=saved['alignment']
    if alignment.get('method')!='reference_audio_translation' or alignment.get('accepted_windows',0)<2:
        raise ValueError('Independent reference-audio windows are required')
    return alignment


def review(path, write=False, directory=None):
    metadata=json.loads(path.read_text());source=metadata['source'];repository=path.parents[4]
    directory=directory or ROOT/'.local/data'/source['source_id']/'play'/f"segment-{source['segment_number']:03}"
    data=json.loads((directory/'analysis.json').read_text())
    media=data['media'];stat=Path(media['path']).stat()
    if (stat.st_size,stat.st_mtime_ns)!=(media['size_bytes'],media['mtime_ns']):
        raise ValueError('Source identity changed; cannot reuse song alignment')
    if directory.name!=f"segment-{data['segment_number']:03}":raise ValueError('Recording segment identity changed')
    alignment=recording_alignment(data,directory,metadata,path)
    if (alignment.get('rate',1)!=1 or not math.isfinite(alignment['song_start_seconds'])
            or not 0<=alignment.get('uncertainty_seconds',0)<=.1):
        raise ValueError('Verified translation alignment with bounded uncertainty is required')
    source={'source_id':directory.parents[1].name,'segment_number':data['segment_number'],
            'media_size_bytes':media['size_bytes'],'media_mtime_ns':media['mtime_ns']}
    measured=estimate(data)
    candidates=proposals(measured,{**metadata,'alignment':alignment},repository/'timing'/f"{metadata['identity']['ucs_index']}.ucs",source)
    changed=record(repository,path,candidates) if write and candidates else False
    return {'metadata':str(path),'source':source['source_id'],'segment':source['segment_number'],
            'alignment':alignment,'measurements':measured,'candidates':candidates,'changed':changed}


def recordings(repository, sources=(), charts=()):
    """Include alternate registered plays, not only each chart's seed video."""
    selected={};targets=set()
    for path in sorted(repository.glob('charts/*/*/phoenix/metadata.json')):
        metadata=json.loads(path.read_text());source=metadata.get('source',{})
        if charts and metadata.get('identity',{}).get('chart') not in charts:continue
        selected[path.resolve()]=path
        if source and (not sources or source['source_id'] in sources):
            targets.add((path,ROOT/'.local/data'/source['source_id']/'play'/f"segment-{source['segment_number']:03}"))
    for registration in sorted((ROOT/'.local/data').glob('*/play/segment-[0-9][0-9][0-9]/chart-registration.json')):
        if sources and registration.parents[2].name not in sources:continue
        saved=json.loads(registration.read_text())
        path=Path(saved['chart']).with_name('metadata.json').resolve() if saved.get('chart') else None
        if path in selected and registration.with_name('analysis.json').is_file():targets.add((selected[path],registration.parent))
    return sorted(targets)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=default_repository())
    parser.add_argument('--sources',nargs='+')
    parser.add_argument('--charts',nargs='+',help='Optional chart labels, for example S21 D24')
    parser.add_argument('--write',action='store_true',help='Append qualified pending effects to chart metadata')
    parser.add_argument('--output',type=Path,default=ROOT/'.local/reports/chart-motion/report.json')
    args=parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'.local'):
        parser.error('--output must stay under .local/')
    records=[]
    for path,directory in recordings(args.repo,args.sources or (),args.charts or ()):
        metadata=json.loads(path.read_text())
        try:
            result=review(path,args.write,directory)
            print(f"{metadata['song']['title']} {metadata['identity']['chart']} ({result['source']}/{result['segment']}): {len(result['candidates'])} qualified speed changes, {len(result['measurements']['transitions'])} measured proposals",flush=True)
        except (OSError,ValueError,KeyError) as error:
            result={'metadata':str(path),'source':directory.parents[1].name,'segment':directory.name,'error':str(error)}
            print(f'{path}: FAILED: {error}',flush=True)
        records.append(result)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    write_json(args.output,{'records':records,'counts':{'charts':len({r['metadata'] for r in records}),'recordings':len(records),'failed':sum('error' in r for r in records),
                                                     'changed':sum(r.get('changed',False) for r in records)}})
    if any('error' in r for r in records):raise SystemExit(1)


if __name__=='__main__':main()
