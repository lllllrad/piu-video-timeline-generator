"""Native spacing can prove chart timing without pretending to measure a clock."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline.play.beats.coordinates import prepare
from piu_timeline.play.beats.recovery import recover,choose_row
from piu_timeline.play.beats.timing import apply
from piu_timeline.play.spacing_checks import spacing_failures
from tests.play.beats.test_coordinates import fixture
from tests.play.beats.test_spatial_phase import scenario as spacing_scenario


def scenario(failed=(4,)):
    data=fixture();data['analysis_width']=400
    data['layout']['lanes']=[{'x':.1+.1*i}for i in range(3)]
    for i,note in enumerate(data['notes']):
        note.update(prediction_uncertainty_seconds=.001,beat_reconstruction={'status':'restored'})
        if i not in failed:continue
        previous={'status':'failed','reason':'insufficient_or_inconsistent_shared_motion',
                  'unaccepted_previous_estimate':{'target_seconds':note['target_seconds']-.02}}
        note.update(status='excluded',reason='shared_timing_reconstruction_failed',
                    target_seconds=None,timing_reconstruction=previous)
        note.pop('motion_clock',None);note.pop('motion_target_phase',None)
    data['timing_reconstruction']={'status':'failed','failed_notes':len(failed),'restored_notes':9-len(failed),
        'warnings':[{'note':i,'reason':'shared_timing_reconstruction_failed'}for i in failed]}
    return data


class NativeTimingRecoveryTest(unittest.TestCase):
    def test_adding_a_head_cannot_hide_a_previous_pair_by_changing_adjacency(self):
        notes,motion,_=spacing_scenario()
        motion['coordinate_registration']['chunks'][0]['head_offsets'][1]['offset_pixels']+=8
        self.assertTrue(spacing_failures(notes,40,motion))
        first=notes[0]
        notes.append({'status':'estimated','lane':2,'points':[(t,y+30)for t,y in first['points']],
                      'target_seconds':1.25,'motion_target_phase':300,
                      'motion_clock':{'origin':0,'velocity':240,'intercept':0}})
        self.assertTrue(any(w['peer_notes']==[0,1]for w in spacing_failures(notes,40,motion,baseline_indices={0,1})))

    def test_failed_clock_is_replaced_by_independent_native_proof_with_original_positions(self):
        data=scenario();original=deepcopy(data);support=prepare(data,40,include_failed=True)
        results=recover(data['notes'],support,[(0,4,120)],0,0,.01)
        note=data['notes'][4];proof=results[4]
        self.assertEqual(note['status'],'estimated')
        self.assertEqual(note['target_seconds'],1.5)
        self.assertEqual(note['points'],original['notes'][4]['points'])
        self.assertNotIn('motion_clock',note)
        self.assertEqual(note['timing_reconstruction']['previous_motion_attempt'],original['notes'][4]['timing_reconstruction'])
        self.assertNotIn(4,[r['note']for r in proof['models'][0]['model']['references']])
        self.assertGreater(note['prediction_uncertainty_seconds'],.01)
        self.assertEqual(proof['models'][0]['head']['source_pts_range'],[80.5,80.68])
        # A recovered target must still pass actual inter-head spacing checks.
        self.assertEqual(spacing_failures(data['notes'],40,data['scroll_motion'],support),[])
        note['target_seconds']+=.06
        self.assertTrue(any(4 in w['peer_notes']for w in spacing_failures(data['notes'],40,data['scroll_motion'],support)))

    def test_recovered_neighbors_are_not_reused_as_references(self):
        data=scenario((4,5));support=prepare(data,40,include_failed=True)
        results=recover(data['notes'],support,[(0,4,120)],0,0,0)
        self.assertEqual({i for i,p in results.items()if p['status']=='restored'},{4,5})
        for proof in results.values():
            for model in proof['models']:
                self.assertTrue({4,5}.isdisjoint(r['note']for r in model['model']['references']))

    def test_insufficient_unregistered_or_inconsistent_geometry_does_not_restore(self):
        for case in ('few_references','unmeasured','bad_reference','unbracketed','no_phase','tempo_boundary'):
            data=scenario();note=data['notes'][4]
            if case=='few_references':
                for i in (0,1,2,3):data['head_registration']['notes'][i]['status']='unresolved'
            elif case=='unmeasured':data['head_registration']['notes'][4]['status']='unresolved'
            elif case=='bad_reference':
                data['notes'][2]['points']=[(t,y+10)for t,y in data['notes'][2]['points']]
                data['scroll_motion']['coordinate_registration']['chunks'][0]['head_offsets'][2]['offset_pixels']+=10
            elif case=='unbracketed':
                data['notes'][4]['points']=[(t,y-180)for t,y in note['points']]
                data['scroll_motion']['coordinate_registration']['chunks'][0]['head_offsets'][4]['offset_pixels']-=180
            sections=[(0,1.51,120),(1.51,4,240)]if case=='tempo_boundary'else[(0,4,120)]
            support=prepare(data,40,include_failed=True)
            recover(data['notes'],support,sections,0,None if case=='no_phase'else 0,0)
            with self.subTest(case=case):
                self.assertEqual(note['status'],'excluded')
                self.assertIsNone(note['target_seconds'])

    def test_ambiguous_or_contradictory_models_fail_without_selecting_a_finer_row(self):
        refs=[{'target_seconds':1+i*.125}for i in range(8)]
        models=[{'range':[1.37,1.63],'model':{'references':refs}}]
        result=choose_row(models,[(0,4,120)],0,0)
        self.assertEqual(result['reason'],'ambiguous_native_coordinate_rows')
        models.append({'range':[1.8,1.9],'model':{'references':refs}})
        self.assertEqual(choose_row(models,[(0,4,120)],0,0)['reason'],'incompatible_native_coordinate_models')

    def test_application_retires_only_the_proven_clock_failure_and_keeps_other_warnings(self):
        data=scenario();data['timing_reconstruction']['warnings'].append({'note':4,'reason':'shared_motion_observation_conflict'})
        original=deepcopy(data)
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);timing=root/'timing.ucs'
            timing.write_text(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'*32)
            reference={'status':'available','timing':str(timing),'song_start_seconds':0,'alignment_uncertainty_seconds':0}
            with patch('piu_timeline.play.beats.timing.reference',return_value=reference):result=apply(data,root)
        self.assertEqual(result['notes'][4]['target_seconds'],1.5)
        self.assertEqual(result['timing_reconstruction']['warnings'],[{'note':4,'reason':'shared_motion_observation_conflict'}])
        self.assertEqual(result['timing_reconstruction']['status'],'failed')
        self.assertTrue(result['beat_timing']['native_coordinate_recovery'])
        self.assertEqual(data,original)
