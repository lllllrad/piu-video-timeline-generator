"""Bounded review collects diverse cases, drains workers and preserves warnings."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline.tools.replay import Replay
from piu_timeline.tools.warning_batch import WarningBatch


class WarningBatchTest(unittest.TestCase):
    def fixture(self, root, segment=1):
        directory=root/'.local/data/video/play'/f'segment-{segment:03}'
        directory.mkdir(parents=True)
        items=[{'reason':'missing_input','note':i,'lane':0} for i in range(5)]
        items.append({'reason':'type_conflict','note':8,'lane':1})
        path=directory/'recognition-warnings.json';path.write_text(json.dumps({'warnings':items}))
        return directory,path

    def test_diverse_queue_is_bounded_without_mutating_or_recounting_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory,path=self.fixture(Path(temporary));original=path.read_bytes()
            batch=WarningBatch(3);batch.collect(directory,'video',1)
            self.assertTrue(batch.full)
            self.assertEqual([i['warning']['reason'] for i in batch.items],['missing_input','type_conflict','missing_input'])
            batch.collect(directory,'video',1)
            self.assertEqual(len(batch.items),3)
            self.assertEqual(path.read_bytes(),original)
            batch=WarningBatch(20);batch.collect(directory,'video',1);batch.collect(directory,'video',1)
            self.assertEqual(len(batch.items),6)
            self.assertFalse(batch.full)

    def test_already_current_play_can_stop_the_batch_without_launching_more(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);self.fixture(root)
            runner=Replay(root,root/'run',jobs=2,warning_limit=3)
            with patch('piu_timeline.tools.replay.discover',return_value=[('video',1),('video',2)]),patch('piu_timeline.tools.replay.current',return_value=True),patch.object(runner,'refresh') as refresh:
                self.assertFalse(runner.cycle())
            refresh.assert_not_called()
            progress=json.loads((root/'run/progress.json').read_text())
            self.assertEqual(progress['state'],'warning_limit_reached')
            self.assertEqual(len(progress['plays']),1)
            self.assertEqual(progress['warning_batch']['collected'],3)

    def test_active_children_finish_but_no_new_child_starts_after_the_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for i in (1,2):self.fixture(root,i)
            runner=Replay(root,root/'run',jobs=2,warning_limit=3)
            completed=[]
            def refresh(source,number,*args):
                completed.append(number)
                return {'status':'current'}
            with patch('piu_timeline.tools.replay.discover',return_value=[('video',i) for i in range(1,8)]),patch('piu_timeline.tools.replay.current',return_value=False),patch.object(runner,'refresh',side_effect=refresh):
                self.assertFalse(runner.cycle())
            self.assertEqual(sorted(completed),[1,2])
            self.assertTrue(all(r['status']=='current' for r in runner.records.values()))
            self.assertEqual(len(runner.warning_batch.items),3)

    def test_unreadable_warning_artifact_is_a_failure_instead_of_a_clean_batch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);runner=Replay(root,root/'run',warning_limit=3)
            with patch('piu_timeline.tools.replay.discover',return_value=[('video',1)]),patch('piu_timeline.tools.replay.current',return_value=True):
                self.assertTrue(runner.cycle())
            self.assertFalse(runner.warning_batch.full)
            self.assertEqual(runner.records['video/001']['status'],'failed')

    def test_reviewed_cases_remain_warnings_but_next_batch_collects_additional_cases(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);directory,path=self.fixture(root);original=path.read_bytes()
            first=WarningBatch(3);first.collect(directory,'video',1)
            reviewed=root/'reviewed.json';reviewed.write_text(json.dumps(first.document()))
            runner=Replay(root,root/'next',warning_limit=2,reviewed_batches=[reviewed])
            with patch('piu_timeline.tools.replay.discover',return_value=[('video',1)]),patch('piu_timeline.tools.replay.current',return_value=True):
                self.assertFalse(runner.cycle())
            self.assertEqual(runner.warning_batch.document()['previously_reviewed_cases'],3)
            self.assertEqual(len(runner.warning_batch.items),2)
            self.assertTrue(set(i['id'] for i in first.items).isdisjoint(i['id'] for i in runner.warning_batch.items))
            self.assertEqual(path.read_bytes(),original)

    def test_unaccounted_exclusions_are_queued_and_shared_warnings_are_not_duplicated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);directory,path=self.fixture(root)
            shared=json.loads(path.read_text())['warnings'][0]
            extra={'reason':'unverified_duplicate_component','note':10,'lane':1}
            excluded=directory/'excluded-trajectories.json'
            excluded.write_text(json.dumps({'warnings':[shared,extra]}));original=excluded.read_bytes()
            batch=WarningBatch(20);batch.collect(directory,'video',1)
            self.assertEqual(len(batch.items),7)
            self.assertEqual(sum(i['warning']==shared for i in batch.items),1)
            self.assertEqual(next(i for i in batch.items if i['warning']==extra)['artifact'],excluded.name)
            self.assertEqual(excluded.read_bytes(),original)
