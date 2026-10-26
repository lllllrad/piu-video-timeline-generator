"""Estimate speed ratios from saved registered motion; optionally append chart effects."""
import argparse
import json
import math
from pathlib import Path

from piu_timeline import ROOT
from piu_timeline.charts.data import default_repository
from piu_timeline.charts.speed_effects import proposals, record
from piu_timeline.charts.official import write_json
from piu_timeline.play.speed_estimation import estimate


def review(path, write=False):
    metadata=json.loads(path.read_text());source=metadata['source'];repository=path.parents[4]
    directory=ROOT/'.local/data'/source['source_id']/'play'/f"segment-{source['segment_number']:03}"
    data=json.loads((directory/'analysis.json').read_text())
    alignment=metadata['alignment']
    if (data['segment_number']!=source['segment_number'] or alignment.get('rate',1)!=1
            or not math.isfinite(alignment['song_start_seconds'])
            or not 0<=alignment.get('uncertainty_seconds',0)<=.1):
        raise ValueError('Verified translation alignment with bounded uncertainty is required')
    media=data['media'];stat=Path(media['path']).stat()
    if ((stat.st_size,stat.st_mtime_ns)!=(media['size_bytes'],media['mtime_ns'])
            or (source['media_size_bytes'],source['media_mtime_ns'])!=(media['size_bytes'],media['mtime_ns'])):
        raise ValueError('Source identity changed; cannot reuse song alignment')
    measured=estimate(data)
    candidates=proposals(measured,metadata,repository/'timing'/f"{metadata['identity']['ucs_index']}.ucs",source)
    changed=record(repository,path,candidates) if write and candidates else False
    return {'metadata':str(path),'source':source['source_id'],'segment':source['segment_number'],
            'measurements':measured,'candidates':candidates,'changed':changed}


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
    for path in sorted(args.repo.glob('charts/*/*/phoenix/metadata.json')):
        metadata=json.loads(path.read_text())
        if args.sources and metadata.get('source',{}).get('source_id') not in args.sources:continue
        if args.charts and metadata.get('identity',{}).get('chart') not in args.charts:continue
        try:
            result=review(path,args.write)
            print(f"{metadata['song']['title']} {metadata['identity']['chart']}: {len(result['candidates'])} qualified speed changes, {len(result['measurements']['transitions'])} measured proposals",flush=True)
        except (OSError,ValueError,KeyError) as error:
            result={'metadata':str(path),'error':str(error)}
            print(f'{path}: FAILED: {error}',flush=True)
        records.append(result)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    write_json(args.output,{'records':records,'counts':{'charts':len(records),'failed':sum('error' in r for r in records),
                                                     'changed':sum(r.get('changed',False) for r in records)}})
    if any('error' in r for r in records):raise SystemExit(1)


if __name__=='__main__':main()
