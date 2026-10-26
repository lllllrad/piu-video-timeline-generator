"""Acquire or refresh local play analyses through the public play command."""
import argparse
from collections import Counter
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import fcntl
import html
import json
import os
from pathlib import Path
import subprocess
import time

from piu_timeline.tools.warning_batch import WarningBatch
from piu_timeline import ROOT
from piu_timeline.play.analysis import VERSION, TIMING_FORMAT
from piu_timeline.play.judgments import cache_current as judgment_current
from piu_timeline.play.holds.analysis import ASSOCIATION_FORMAT, fingerprint
from piu_timeline.play.holds.features import feature_contract


def write_json(path, data):
    pending = path.with_suffix('.build-json')
    pending.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    pending.replace(path)


def busy(path):
    if not path.exists():
        return False
    with path.open() as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(lock, fcntl.LOCK_UN)
    return False


def file_signature(path):
    try:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size, stat.st_ino
    except FileNotFoundError:
        return None


def current(path):
    """Check derived artifact contracts without decoding, OCR or cache writes."""
    if not all(path.with_name(name).is_file() for name in
               ('frames.jsonl', 'report.html', 'recognition-warnings.json', 'timing-ranges.json',
                'timing-reconstruction.json','beat-timing.json')):
        return False
    from piu_timeline.play.continuity import FORMAT as VISIBILITY_FORMAT
    visibility = path.with_name('visibility-diagnostics.json')
    if not visibility.is_file() or json.loads(visibility.read_text()).get('format') != VISIBILITY_FORMAT:
        return False
    data = json.loads(path.read_text())
    from piu_timeline.play.support import visual_support
    support_file=path.with_name('visual-support.json')
    if (json.loads(support_file.read_text()) if support_file.is_file() else None)!=visual_support(data):
        return False
    policy_path = path.with_name('chart-policy.json')
    if policy_path.is_file():
        policy = json.loads(policy_path.read_text())
        from piu_timeline.play.gimmicks import FORMAT as GIMMICK_FORMAT
        if policy.get('gimmick_format') != GIMMICK_FORMAT:
            return False
        metadata = Path(policy.get('metadata_path',''))
        if policy.get('status') == 'applied' and (not metadata.is_file()
                or sha256(metadata.read_bytes()).hexdigest() != policy.get('metadata_sha256')):
            return False
    else:
        registration = path.with_name('chart-registration.json')
        saved = json.loads(registration.read_text()) if registration.is_file() else {}
        if saved.get('chart'):
            metadata_path = Path(saved['chart']).with_name('metadata.json')
            if metadata_path.is_file():
                metadata = json.loads(metadata_path.read_text())
                if metadata.get('regions') or metadata.get('gimmick_candidates'):
                    return False
    from piu_timeline.play.beat_timing import current as beat_current
    if not beat_current(data,path.parent):
        return False
    holds = data.get('hold_analysis', {})
    contract = holds.get('association_contract', {})
    if (data.get('play_analysis_version') != VERSION or data.get('timing_format') != TIMING_FORMAT
            or contract.get('format') != ASSOCIATION_FORMAT):
        return False
    if data.get('media', {}).get('video_streams'):
        from piu_timeline.play.channels import CHANNEL_FORMAT
        if (data.get('visual_channels', {}).get('format') != CHANNEL_FORMAT
                or not all(path.with_name(name).is_file() for name in
                           ('visual-channels.json', 'processing-features.npz'))):
            return False
        if ('appearance-features.npz' in data.get('visual_channels',{}).get('note_types',{}).get('traces',[])
                and not path.with_name('appearance-features.npz').is_file()):
            return False
    media = data['media']; stat = Path(media['path']).stat()
    return ((stat.st_size, stat.st_mtime_ns) == (media['size_bytes'], media['mtime_ns'])
            and holds.get('feature_contract') == feature_contract(data)
            and contract.get('notes') == fingerprint(data.get('notes', []))
            and contract.get('hud_events') == fingerprint({key:data.get(key, [])
                                                          for key in ('combo_events', 'judgment_events')})
            and judgment_current(data, path.parent.parent, path.parent))


def discover(root, sources=(), segments=(), acquire=False):
    data = root/'.local/data'; selected = []
    for source in sorted(data.iterdir()) if data.is_dir() else []:
        if not source.is_dir():
            continue
        if sources and source.name not in sources:
            continue
        if acquire:
            metadata = source/'analysis/analysis.json'
            if not metadata.is_file():
                continue
            try:
                count = len(json.loads(metadata.read_text()).get('segments', []))
            except (OSError, ValueError):
                continue  # A producer may still be promoting this metadata.
            numbers = range(1, count+1)
        else:
            numbers = [int(p.parent.name.removeprefix('segment-'))
                       for p in (source/'play').glob('segment-[0-9][0-9][0-9]/frames.jsonl')
                       if p.with_name('analysis.json').is_file()]
        selected.extend((source.name, number) for number in sorted(numbers) if not segments or number in segments)
    order = {name:i for i,name in enumerate(sources)}
    return sorted(selected, key=lambda item:(order.get(item[0], len(order)), item))


class Replay:
    def __init__(self, root, output, sources=(), segments=(), acquire=False, jobs=1, warning_limit=None, reviewed_batches=()):
        self.root, self.output = Path(root), Path(output)
        self.sources, self.segments, self.acquire = sources, segments, acquire
        if jobs < 1:
            raise ValueError("Replay jobs must be positive")
        self.jobs = jobs
        reviewed=[]
        for path in reviewed_batches:
            items=json.loads(Path(path).read_text())['items']
            if any(not isinstance(item.get('id'),str) or not item['id'] for item in items):
                raise ValueError('Reviewed batches require explicit case identities')
            reviewed.extend(item['id'] for item in items)
        self.warning_batch=WarningBatch(warning_limit,reviewed)
        self.records = {}
        self.output.mkdir(parents=True, exist_ok=True)
        self.started = datetime.now(timezone.utc).isoformat()

    def progress(self, state, active=None):
        records = list(self.records.values())
        active_plays = [f"{r['source']}/{r['segment']:03}" for r in records if r['status']=='running']
        doc = {'jobs':self.jobs, 'active_plays':active_plays, 'started':self.started, 'updated':datetime.now(timezone.utc).isoformat(),
               'state':state, 'active':active or next(iter(active_plays),None), 'counts':dict(Counter(r['status'] for r in records)),
               'play_analysis_version':VERSION, 'hold_association_format':ASSOCIATION_FORMAT,
               'plays':records}
        doc['warning_batch']=self.warning_batch.document()
        write_json(self.output/'warning-batch.json',doc['warning_batch'])
        write_json(self.output/'progress.json', doc)
        rows = ''.join('<tr><td>'+html.escape(r['source'])+'</td><td>'+str(r['segment'])
                       +'</td><td>'+html.escape(r['status'])+'</td><td>'+html.escape(r.get('detail', ''))+'</td></tr>'
                       for r in records)
        page = ('<!doctype html><meta charset="utf-8"><title>Play replay progress</title>'
                '<h1>Play replay progress</h1><p>'+html.escape(state)+'</p><table>'
                '<tr><th>Source</th><th>Segment</th><th>Status</th><th>Details</th></tr>'+rows+'</table>')
        pending = self.output/'index.build-html'; pending.write_text(page); pending.replace(self.output/'index.html')

    def refresh(self, source, number, path, signature):
        """Run one independent child; the coordinator alone writes progress."""
        record = {}
        log = self.output/f'{source}-{number:03}.log'; begin = time.monotonic()
        try:
            with log.open('w') as stream:
                result = subprocess.run(['just', 'play', source, '--segment', str(number)],
                                        cwd=self.root, stdout=stream, stderr=subprocess.STDOUT)
            valid = result.returncode == 0 and current(path)
            record.update(returncode=result.returncode,
                          status='current' if valid else 'queued' if result.returncode == 0 else 'failed',
                          detail='Completed through the public play command.' if valid else 'See '+log.name)
            if result.returncode and 'already being analyzed' in log.read_text():
                record.update(status='busy', detail='Another analyzer acquired the segment lock.')
        except (OSError, ValueError, KeyError) as error:
            record.update(status='failed', detail=str(error))
        record.update(elapsed_seconds=round(time.monotonic()-begin, 2), log=log.name)
        if record['status'] == 'failed':
            record['failed_signature'] = signature
        return record

    def finish(self, pending):
        done, _ = wait(pending, return_when=FIRST_COMPLETED)
        for future in done:
            self.records[pending.pop(future)].update(future.result())
        for record in self.records.values():
            if record['status']=='current':self.collect_warnings(record)
        self.progress('refreshing')

    def collect_warnings(self,record):
        if self.warning_batch.full or self.warning_batch.limit is None:return
        directory=self.root/'.local/data'/record['source']/'play'/f"segment-{record['segment']:03}"
        try:self.warning_batch.collect(directory,record['source'],record['segment'])
        except (OSError,ValueError,KeyError) as error:
            record.update(status='failed',detail='Cannot collect warning batch: '+str(error))

    def cycle(self):
        pending = {}
        with ThreadPoolExecutor(max_workers=self.jobs) as pool:
            for source, number in discover(self.root, self.sources, self.segments, self.acquire):
                if len(pending) >= self.jobs:
                    self.finish(pending)
                if self.warning_batch.full:break
                key = f'{source}/{number:03}'
                directory = self.root/'.local/data'/source/'play'/f'segment-{number:03}'
                path = directory/'analysis.json'
                record = self.records.setdefault(key, {'source':source, 'segment':number})
                # Public play also checks this lock, closing the race after this check.
                if busy(directory.parent/f'.segment-{number:03}.lock'):
                    record.update(status='busy', detail='Deferred: another analyzer owns this segment.'); continue
                signature = [file_signature(p)
                             for p in (path, directory.parent.parent/'analysis/analysis.json')]
                try:
                    if current(path):
                        record.update(status='current', detail='Artifact contracts are current.')
                        self.collect_warnings(record)
                        continue
                except (OSError, ValueError, KeyError) as error:
                    record['detail'] = str(error)
                if record.get('status') == 'failed' and record.get('failed_signature') == signature:
                    continue
                record.update(status='running')
                pending[pool.submit(self.refresh,source,number,path,signature)] = key
                self.progress('refreshing')
            while pending:
                self.finish(pending)
        deferred = any(r['status'] in ('queued', 'busy') for r in self.records.values())
        self.progress('warning_limit_reached' if self.warning_batch.full else 'deferred' if deferred else 'complete')
        return any(r['status'] == 'failed' for r in self.records.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    cores = len(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else os.cpu_count() or 1
    parser.add_argument('--jobs', type=int, default=min(8,max(1,cores//2)),
                        help='Concurrent play processes (default: half the available CPUs, capped at 8)')
    parser.add_argument('--sources', nargs='+')
    parser.add_argument('--segments', nargs='+', type=int)
    parser.add_argument('--acquire', action='store_true', help='Include metadata plays without native observations')
    parser.add_argument('--watch', action='store_true', help='Discover newly completed/promoted plays every 30 seconds')
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--reviewed-batch',type=Path,action='append',default=[],
                        help='Previously inspected warning-batch.json; skip these IDs only in the new review queue')
    parser.add_argument('--warning-limit',type=int,help='Stop scheduling after collecting this many distinct unresolved cases; finish active plays')
    args = parser.parse_args()
    if args.warning_limit is not None and args.warning_limit<1:
        parser.error('--warning-limit must be positive')
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    if args.segments and min(args.segments) < 1:
        parser.error('Segment numbers start at 1')
    destination = args.run_dir or ROOT/'.local/runs'/('play-replay-'+time.strftime('%Y%m%d-%H%M%S'))
    if not destination.resolve().is_relative_to(ROOT/'.local'):
        parser.error('--run-dir must stay under .local/')
    runner = Replay(ROOT, destination, args.sources or (), args.segments or (), args.acquire, args.jobs, args.warning_limit, args.reviewed_batch)
    with (destination/'.runner.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('This replay run directory is already in use')
        while True:
            failed = runner.cycle()
            if runner.warning_batch.full or not args.watch:
                raise SystemExit(int(failed))
            time.sleep(30)


if __name__ == '__main__':
    main()
