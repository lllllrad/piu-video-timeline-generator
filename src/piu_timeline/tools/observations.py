"""Inventory or acquire reusable independent visual channels across local recordings."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from piu_timeline import ROOT
from piu_timeline.play.layout import fixed_layout, validate_layout
from piu_timeline.play.observations.artifacts import save_input
from piu_timeline.play.observations.bundle import acquire

REQUIRED_SKINS = ('arrow-center-xh-review', 'phoenix-arrow-jsg')


def inventory(root, sources=(), segments=()):
    tasks = []
    for path in sorted(root.glob('*/analysis/analysis.json')):
        source = path.parents[1]
        if sources and source.name not in sources: continue
        document = json.loads(path.read_text())
        for number, segment in enumerate(document['segments'],1):
            if segments and number not in segments: continue
            layout_path=source/'play'/f'segment-{number:03}'/'layout.json'
            try:
                layout=validate_layout(json.loads(layout_path.read_text()))if layout_path.is_file()else fixed_layout(segment)
                if layout is None: raise ValueError('Unknown or simultaneous-player layout requires explicit geometry')
                problem=None
            except (ValueError,KeyError) as error:
                layout=None;problem=str(error)
            tasks.append({'source':source.name,'segment':number,'layout':layout,'problem':problem,
                          'start_seconds':segment['start_seconds'],'end_seconds':segment['end_seconds']})
    # Mandatory real-world skins are exercised first, without excluding any other source.
    return sorted(tasks,key=lambda t:(0 if t['source']=='4MyMJse0L0g' else 1 if t['source']=='JsgHmEUvl5Q' else 2,t['source'],t['segment']))


def required_banks():
    from piu_timeline.play.skins.automatic import candidates
    from piu_timeline.play.skins.bank import load_bank
    result = {}
    for candidate in candidates():
        name=candidate['selection']['skin']
        if name not in REQUIRED_SKINS or not candidate['eligible']:continue
        bank=load_bank(candidate['path'])
        missing=[(kind,role)for kind in range(5)for role in ('tap','hold_start','hold_body','hold_end')
                 if not any(t['lane_kind']==kind and t['role']==role for t in bank['templates'])]
        if missing:raise ValueError('Required skin has incomplete image coverage: '+name+' '+str(missing))
        result[name]={'selection':candidate['selection'],'contract':bank['contract'],'templates':len(bank['templates'])}
    if set(result)!=set(REQUIRED_SKINS):raise ValueError('Required automatic skin banks are not installed: '+str(set(REQUIRED_SKINS)-set(result)))
    return result


def capture_one(root, source, number, jobs=1):
    directory=root/source;document=json.loads((directory/'analysis/analysis.json').read_text())
    tasks=inventory(root,[source],[number])
    if len(tasks)!=1 or tasks[0]['problem']:raise ValueError(tasks[0]['problem']if tasks else 'Unknown segment')
    task=tasks[0];segment=document['segments'][number-1]
    output=directory/'observations'/f'segment-{number:03}';output.parent.mkdir(exist_ok=True)
    with output.with_suffix('.lock').open('a')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        from piu_timeline.play.skins.replay import selected_bank
        from piu_timeline.play.skins.automatic import prepare
        from piu_timeline.play.skins.bank import load_bank
        data={**document,**segment,'layout':task['layout']}
        # Publish all independent pixels before running a fallible detector.
        from piu_timeline.play.observations.bundle import acquire_pixels
        acquire_pixels(data,output)
        bank=None;failure=None
        try:
            path=selected_bank(directory,number)
            if path is None:path=prepare(directory,number,document,{'layout':task['layout']},pixel_directory=output)
            bank=load_bank(path)
        except (ValueError,OSError,KeyError)as error:
            failure=str(error)
        result=acquire(data,output,bank,jobs=jobs)
        if failure:
            # Unsupported note images cannot prevent acquisition of the other three channels.
            save_input(output.parent/f'segment-{number:03}-selection.json',{'status':'unresolved','reason':failure})
        return {'status':'complete'if bank else'partial','frames':result['frame_count'],
                'skin':bank['skin']if bank else None,'selection_failure':failure,'manifest':str(output/'manifest.json')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT/'.local/data')
    parser.add_argument('--sources',nargs='+');parser.add_argument('--segments',type=int,nargs='+')
    parser.add_argument('--acquire',action='store_true',help='Acquire every planned channel; default only inventories')
    parser.add_argument('--jobs',type=int,default=2,help='Concurrent recordings, with divided image-worker budget')
    parser.add_argument('--run-dir',type=Path)
    parser.add_argument('--one',nargs=2,metavar=('SOURCE','SEGMENT'),help=argparse.SUPPRESS)
    args=parser.parse_args()
    if not 1<=args.jobs<=32:parser.error('--jobs must be 1..32')
    if args.one:
        result=capture_one(args.root,args.one[0],int(args.one[1]),int(os.environ.get('PIU_SKIN_JOBS','1')))
        print(json.dumps(result));return 0 if result['status']=='complete'else 2
    tasks=inventory(args.root,args.sources or (),args.segments or ())
    run=args.run_dir or ROOT/'.local/runs'/('observations-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))
    run.mkdir(parents=True,exist_ok=False)
    proof=required_banks()
    save_input(run/'plan.json',{'schema':1,'required_skins':proof,'tasks':tasks,
                              'unregistered_media':[str(p)for p in (ROOT/'.local/etc').glob('*')if p.suffix.lower()in('.mp4','.mkv','.webm')]})
    state={'schema':1,'state':'running'if args.acquire else'inventory','tasks':[{**t,'status':'blocked'if t['problem']else'queued'}for t in tasks]}
    save_input(run/'progress.json',state)
    print(f'{len(tasks)} gameplay windows; inventory: {run}',flush=True)
    if not args.acquire:return 0
    available=len(os.sched_getaffinity(0))if hasattr(os,'sched_getaffinity')else(os.cpu_count()or 1)
    env=os.environ.copy();env['PIU_SKIN_JOBS']=str(min(8,max(1,available//args.jobs)))
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):env[key]='1'
    progress_lock=threading.Lock()
    def execute(index,task):
        if task['problem']:return index,{'status':'blocked','error':task['problem']}
        with progress_lock:
            state['tasks'][index]['status']='running'
            save_input(run/'progress.json',state)
        log=run/f'{task["source"]}-{task["segment"]:03}.log'
        with log.open('w')as stream:
            process=subprocess.run([sys.executable,'-m','piu_timeline.tools.observations','--root',str(args.root),'--one',task['source'],str(task['segment'])],stdout=stream,stderr=subprocess.STDOUT,env=env)
        if process.returncode in (0,2):
            try:result=json.loads(log.read_text().splitlines()[-1])
            except (ValueError,IndexError):result={'status':'failed','error':'Missing capture result'}
        else:result={'status':'failed','exit_code':process.returncode,'log':str(log)}
        return index,result
    with ThreadPoolExecutor(max_workers=args.jobs)as pool:
        futures={pool.submit(execute,i,t):i for i,t in enumerate(tasks)}
        for future in as_completed(futures):
            index,result=future.result()
            with progress_lock:
                state['tasks'][index].update(result)
                save_input(run/'progress.json',state)
            print(tasks[index]['source'],tasks[index]['segment'],result['status'],flush=True)
    state['state']='complete'if all(t['status']=='complete'for t in state['tasks'])else'incomplete'
    save_input(run/'progress.json',state)
    return 0 if state['state']=='complete'else 1


if __name__=='__main__':raise SystemExit(main())
