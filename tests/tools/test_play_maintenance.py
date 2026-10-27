"""Reusable replay and audit tools preserve evidence and defer concurrent writers."""
import fcntl
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from piu_timeline.play.analysis import VERSION, TIMING_FORMAT
from piu_timeline.play.holds.analysis import ASSOCIATION_FORMAT, fingerprint
from piu_timeline.play.holds.features import feature_contract
from piu_timeline.play.associations import FORMAT as ASSOCIATION_VIEW_FORMAT
from piu_timeline.play.judgments import cache_contracts
from piu_timeline.tools.replay import Replay, current, discover
from piu_timeline.tools.audit import review, label_cause


def play(root, source='source', number=1, stale=False):
    directory=root/'.local/data'/source/'play'/f'segment-{number:03}';directory.mkdir(parents=True)
    metadata=directory.parent.parent/'analysis';metadata.mkdir(exist_ok=True)
    (metadata/'analysis.json').write_text(json.dumps({'segments':[{}]*number}))
    media=directory.parent.parent/'recording.mp4';media.write_bytes(b'original recording')
    stat=media.stat()
    data={'timing_format':TIMING_FORMAT,'association_view_format':ASSOCIATION_VIEW_FORMAT,
          'play_analysis_version':0 if stale else VERSION, 'notes':[], 'matches':[],
          'combo_events':[], 'judgment_events':[], 'analysis_width':650,
          'media':{'path':str(media),'size_bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns},
          'start_seconds':0, 'end_seconds':1, 'game_roi':[0,0,1300,730], 'layout':{'lanes':[]}}
    from piu_timeline.play.beats.timing import FORMAT as BEAT_FORMAT, reference
    data['beat_timing']={'contract':{'format':BEAT_FORMAT,'reference':reference(data,directory)}}
    data['judgment_cache']=cache_contracts(data, [])
    data['hold_analysis']={'feature_contract':feature_contract(data), 'association_contract':{
        'format':ASSOCIATION_FORMAT, 'notes':fingerprint([]),
        'hud_events':fingerprint({'combo_events':[], 'judgment_events':[]})}}
    path=directory/'analysis.json';path.write_text(json.dumps(data))
    (directory/'frames.jsonl').write_text('original native observations\n')
    (directory/'report.html').write_text('original report')
    (directory/'recognition-warnings.json').write_text('{"warnings":[]}')
    (directory/'excluded-trajectories.json').write_text('{"counts":{},"warnings":[]}')
    (directory/'timing-ranges.json').write_text('{"notes":{}}')
    (directory/'timing-reconstruction.json').write_text('{}')
    (directory/'beat-timing.json').write_text(json.dumps(data['beat_timing']))
    from piu_timeline.play.continuity import FORMAT
    (directory/'visibility-diagnostics.json').write_text(json.dumps({'format':FORMAT,'warnings':[]}))
    return path, data


class ReplayTest(unittest.TestCase):
    def test_current_requires_matching_contracts_artifacts_and_original_media(self):
        with tempfile.TemporaryDirectory() as temp:
            path,data=play(Path(temp))
            self.assertTrue(current(path))
            data['association_view_format']={};path.write_text(json.dumps(data))
            self.assertFalse(current(path))
            data['association_view_format']=ASSOCIATION_VIEW_FORMAT;path.write_text(json.dumps(data))
            path.with_name('recognition-warnings.json').unlink()
            self.assertFalse(current(path))
            path.with_name('recognition-warnings.json').write_text('{}')
            Path(data['media']['path']).write_bytes(b'changed recording')
            self.assertFalse(current(path))

    def test_new_or_changed_chart_effects_refresh_reports_without_changing_native_data(self):
        from hashlib import sha256
        from piu_timeline.play.gimmicks import FORMAT
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path,_=play(root)
            chart=root/'chart.ucs';chart.write_text('unchanged chart')
            metadata=chart.with_name('metadata.json')
            effect={'id':'ten','kind':'suspected_multi_increment','combo_increment':10,
                    'start_seconds':0,'end_seconds':1,'review_status':'pending','reason':'One refresh per ten ticks'}
            metadata.write_text(json.dumps({'gimmick_candidates':[effect]}))
            native=path.with_name('frames.jsonl').read_bytes()
            path.with_name('chart-registration.json').write_text(json.dumps({'chart':str(chart)}))
            self.assertFalse(current(path))
            policy={'status':'applied','gimmick_format':FORMAT,'metadata_path':str(metadata),
                    'metadata_sha256':sha256(metadata.read_bytes()).hexdigest()}
            path.with_name('chart-policy.json').write_text(json.dumps(policy))
            self.assertTrue(current(path))
            metadata.write_text(json.dumps({'gimmick_candidates':[{**effect,'review_status':'rejected'}]}))
            self.assertFalse(current(path))
            self.assertEqual(path.with_name('frames.jsonl').read_bytes(),native)

    def test_replay_uses_public_command_and_preserves_native_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path,data=play(root,stale=True)
            native=path.with_name('frames.jsonl').read_bytes()
            source=Path(data['media']['path']);before=source.stat()
            def execute(argv,**kwargs):
                self.assertEqual(argv,['just','play','source','--segment','1'])
                self.assertEqual(kwargs['cwd'],root)
                data['play_analysis_version']=VERSION;path.write_text(json.dumps(data))
                return subprocess.CompletedProcess(argv,0)
            runner=Replay(root,root/'.local/runs/replay')
            with patch('piu_timeline.tools.replay.subprocess.run',side_effect=execute) as invoke:
                self.assertFalse(runner.cycle());self.assertFalse(runner.cycle())
                invoke.assert_called_once()
            self.assertEqual(runner.records['source/001']['status'],'current')
            self.assertEqual(path.with_name('frames.jsonl').read_bytes(),native)
            self.assertEqual((source.stat().st_size,source.stat().st_mtime_ns),(before.st_size,before.st_mtime_ns))

    def test_busy_segment_is_deferred_then_discovered_after_promotion(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path,_=play(root,stale=True);runner=Replay(root,root/'.local/runs/replay')
            with (path.parent.parent/'.segment-001.lock').open('w') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                with patch('piu_timeline.tools.replay.subprocess.run',side_effect=AssertionError('concurrent writer')):
                    self.assertFalse(runner.cycle())
                self.assertEqual(runner.records['source/001']['status'],'busy')
            other,_=play(root,'second')
            self.assertEqual(discover(root),[('second',1),('source',1)])
            other.with_name('frames.jsonl').unlink()
            self.assertEqual(discover(root),[('source',1)])
            self.assertEqual(discover(root,acquire=True),[('second',1),('source',1)])

    def test_parallel_replay_fills_bounded_slots_and_isolates_failed_children(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            plays={source:play(root,source,stale=True) for source in ('a','b','c','d')}
            barrier=threading.Barrier(2,timeout=5)
            lock=threading.Lock();active=0;peak=0;seen=[]
            def execute(argv,**kwargs):
                nonlocal active,peak
                source=argv[2]
                with lock:
                    active+=1;peak=max(peak,active);seen.append(source)
                try:
                    barrier.wait()
                    if source=='b':
                        return subprocess.CompletedProcess(argv,1)
                    path,data=plays[source]
                    data['play_analysis_version']=VERSION;path.write_text(json.dumps(data))
                    return subprocess.CompletedProcess(argv,0)
                finally:
                    with lock:active-=1
            runner=Replay(root,root/'.local/runs/replay',jobs=2)
            with patch('piu_timeline.tools.replay.subprocess.run',side_effect=execute):
                self.assertTrue(runner.cycle())
            self.assertEqual(peak,2)
            self.assertEqual(set(seen),set(plays))
            self.assertEqual(runner.records['b/001']['status'],'failed')
            progress=json.loads((runner.output/'progress.json').read_text())
            self.assertEqual(progress['counts'],{'current':3,'failed':1})
            self.assertEqual(progress['active_plays'],[])
            self.assertEqual(progress['jobs'],2)
            for path,_ in plays.values():
                self.assertEqual(path.with_name('frames.jsonl').read_text(),'original native observations\n')
            with patch('piu_timeline.tools.replay.subprocess.run',side_effect=AssertionError('unchanged failures must not retry')):
                self.assertTrue(runner.cycle())

    def test_child_losing_the_segment_lock_is_deferred_without_blocking_other_workers(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);play(root,'a',stale=True);path,data=play(root,'b',stale=True)
            def execute(argv,**kwargs):
                if argv[2]=='a':
                    kwargs['stdout'].write('This play is already being analyzed')
                    return subprocess.CompletedProcess(argv,1)
                data['play_analysis_version']=VERSION;path.write_text(json.dumps(data))
                return subprocess.CompletedProcess(argv,0)
            runner=Replay(root,root/'.local/runs/replay',jobs=2)
            with patch('piu_timeline.tools.replay.subprocess.run',side_effect=execute):
                self.assertFalse(runner.cycle())
            self.assertEqual(runner.records['a/001']['status'],'busy')
            self.assertEqual(runner.records['b/001']['status'],'current')
            self.assertEqual(json.loads((runner.output/'progress.json').read_text())['state'],'deferred')

    def test_failure_does_not_block_other_plays_or_retry_unchanged_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path,_=play(root,'a',stale=True);play(root,'b')
            runner=Replay(root,root/'.local/runs/replay')
            with patch('piu_timeline.tools.replay.subprocess.run',return_value=subprocess.CompletedProcess([],1)) as invoke:
                self.assertTrue(runner.cycle());self.assertTrue(runner.cycle())
                invoke.assert_called_once()
                self.assertEqual(runner.records['b/001']['status'],'current')
                path.write_text(path.read_text()+' ')
                self.assertTrue(runner.cycle());self.assertEqual(invoke.call_count,2)
            progress=json.loads((runner.output/'progress.json').read_text())
            self.assertEqual(progress['counts'],{'failed':1,'current':1})


class AuditTest(unittest.TestCase):
    def test_review_keeps_uncertainty_and_source_mutation_visible_without_rewriting(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path,data=play(root)
            data['song']='<script>untrusted</script>';path.write_text(json.dumps(data))
            warnings={'warnings':[{'note':0,'reason':'timing_evidence_unresolved','lane':0}]}
            path.with_name('recognition-warnings.json').write_text(json.dumps(warnings))
            path.with_name('timing-ranges.json').write_text(json.dumps({'notes':{'0':{
                'status':'possible','reason':'ambiguous_display_association','rejected_candidates':['shared_onset']}}}))
            Path(data['media']['path']).write_bytes(b'changed recording')
            paths=list(path.parent.iterdir());before={p:p.read_bytes() for p in paths if p.is_file()}
            output=root/'.local/reports/review';result=review(root,output)
            self.assertEqual(result['warning_counts'],{'timing_evidence_unresolved':1})
            record=result['plays'][0]
            self.assertFalse(record['source_identity_preserved'])
            self.assertEqual(record['classifications'],{'ambiguous_display_association':1})
            self.assertEqual({p:p.read_bytes() for p in before},before)
            page=(output/'index.html').read_text()
            self.assertNotIn(data['song'],page);self.assertIn('&lt;script&gt;',page)
            path.with_name('recognition-warnings.json').write_text('invalid JSON')
            result=review(root,output)
            self.assertEqual(len(result['errors']),1)
            self.assertFalse(result['plays'])

    def test_aggregate_or_conflicting_words_cannot_be_reported_as_resolved(self):
        match={'combo_event':0}
        events=[{'lower_seconds':1.,'upper_seconds':1.02,'delta':2}]
        frames=[{'playback_seconds':t,'label':label,'confidence':.99}
                for t,label in [(1.02,'PERFECT'),(1.04,'GREAT')]]
        times=[f['playback_seconds'] for f in frames]
        self.assertEqual(label_cause(match,events,frames,times),'aggregate_counter_jump')
        events[0]['delta']=1
        self.assertEqual(label_cause(match,events,frames,times),'conflicting_label_reads')
