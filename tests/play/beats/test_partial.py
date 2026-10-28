"""Ambiguous heads stay failed while independent unique rows retain their proof."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline.play.beats.phase import fit_phase
from piu_timeline.play.beats.timing import apply, fit_grid, spacing_supported_notes
from tests.play.beats.test_domains import scenario
from tests.play.beats.test_spatial_phase import scenario as spatial_scenario


class PartialBeatTest(unittest.TestCase):
    def test_unsupported_clock_row_cannot_force_unique_neighbors_onto_an_ambiguous_finer_grid(self):
        targets=[1+i*.125+.02 for i in range(12)]
        errors=[.03]*12
        targets.insert(6,1+.625+1/12);errors.insert(6,.01)
        result=fit_grid(targets,errors,120,1)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['split'],4)
        self.assertEqual(result['unresolved_indices'],[6])
        self.assertIsNone(result['targets'][6])
        self.assertEqual([t for t in result['targets']if t is not None],[1+i*.125 for i in range(12)])
        self.assertGreater(result['row_domains'][6][0],result['row_domains'][6][1])
        self.assertEqual(result['reason'],'no_natural_beat_subdivision')

    def test_common_phase_keeps_unique_rows_without_choosing_an_ambiguous_neighbor(self):
        group={'targets':[10,10.125,10.25,10.375],'errors':[.001,.001,.14,.001],
               'bpm':120,'origin':10}
        original=deepcopy(group)
        result=fit_phase([group],.002)
        self.assertEqual(result['status'],'restored')
        fit=result['fits'][0]
        self.assertEqual(fit['status'],'partial')
        self.assertEqual(fit['split'],4)
        self.assertEqual(fit['rows'],[0,1,None,3])
        self.assertEqual(fit['targets'],[10,10.125,None,10.375])
        self.assertEqual(fit['unresolved_indices'],[2])
        self.assertEqual(group,original)

    def test_application_warns_on_the_ambiguous_head_and_preserves_all_unique_neighbors(self):
        data=scenario();data['head_registration']['notes'][4]['status']='unresolved'
        original=deepcopy(data)
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);timing=root/'timing.ucs'
            timing.write_text(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'*32)
            reference={'status':'available','timing':str(timing),'song_start_seconds':1,'alignment_uncertainty_seconds':0}
            with patch('piu_timeline.play.beats.timing.reference',return_value=reference):
                result=apply(data,root)
        self.assertEqual(result['beat_timing']['status'],'failed')
        self.assertEqual(result['beat_timing']['groups'][0]['status'],'partial')
        self.assertEqual({w['note']for w in result['beat_timing']['warnings']},{4})
        failed=result['notes'][4]
        self.assertEqual(failed['status'],'excluded')
        self.assertEqual(failed['reason'],'beat_timing_reconstruction_failed')
        self.assertIsNone(failed['target_seconds'])
        self.assertEqual(failed['video_target_range'],[1.37,1.63])
        self.assertEqual(failed['beat_reconstruction']['reason'],'ambiguous_beat_rows')
        self.assertTrue(all(n['status']=='estimated'and n['beat_reconstruction']['status']=='restored'
                            for i,n in enumerate(result['notes'])if i!=4))
        self.assertTrue(all(n['beat_reconstruction']['group_index']==0 for n in result['notes']))
        self.assertEqual(data,original)

    def test_partial_assignment_cannot_bypass_independent_spatial_rejection(self):
        notes,motion,_=spatial_scenario()
        notes.append({'status':'estimated','lane':2,'target_seconds':1.25,'points':[]})
        group={'notes':[0,2,1],'targets':[1.007,1.25,1.507],'errors':[.01,.26,.01],'bpm':120,'origin':0}
        fit=fit_grid(group['targets'],group['errors'],120,0)
        self.assertEqual(fit['status'],'partial')
        self.assertEqual(spacing_supported_notes(notes,[group],[fit],40,motion),(0,1))
        motion['coordinate_registration']['chunks'][0]['head_offsets'][1]['offset_pixels']+=6
        self.assertEqual(spacing_supported_notes(notes,[group],[fit],40,motion),())

    def test_partial_groups_with_different_supported_identities_do_not_choose_a_phase(self):
        group={'targets':[1,1.25],'errors':[.02,.3],'bpm':120,'origin':0}
        result=fit_phase([group],.01,consistent_notes=lambda fits:(0,)if fits[0]['targets'][0]<1 else(1,))
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['reason'],'ambiguous_or_unsupported_song_phase')

    def test_conflicting_chord_component_does_not_erase_independent_unique_rows(self):
        proof={'indices':[0,1],'minimum_velocity_pixels_per_second':500.}
        result=fit_grid([1.,1.03125,1.125,1.25],[.001]*4,120,0,
                        splits=[16],native_chords=[proof])
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['targets'],[None,None,1.125,1.25])
        self.assertEqual(result['incompatible_chord_indices'],[0,1])
        self.assertEqual(result['reason'],'native_chord_domains_incompatible')
        # These are direct clock rows, not native-domain guesses; no recorded
        # interval is widened to rescue either inconsistent chord member.
        self.assertEqual(result['unconstrained_row_domains'],[(32,32),(33,33),(36,36),(40,40)])

    def test_application_retains_other_rows_and_warns_on_both_inconsistent_chord_members(self):
        from tests.play.beats.test_chords import fixture
        data=fixture()
        data['notes'].append(deepcopy(data['notes'][2]))
        data['head_registration']['notes'].append(deepcopy(data['head_registration']['notes'][2]))
        for i,(note,target)in enumerate(zip(data['notes'],(1.,1.03125,1.125,1.25))):
            note.update(lane=i,target_seconds=target,prediction_uncertainty_seconds=.001)
            if i>=2:note['points']=[[t,40+500*(target-t)]for t,_ in note['points']]
            data['head_registration']['notes'][i]['note']=i
        before=deepcopy(data)
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);timing=root/'timing.ucs'
            timing.write_text(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'*32)
            ref={'status':'available','timing':str(timing),'song_start_seconds':0,'alignment_uncertainty_seconds':0}
            with patch('piu_timeline.play.beats.timing.reference',return_value=ref):result=apply(data,root)
        self.assertEqual(data,before)
        self.assertEqual([n['target_seconds']for n in result['notes']],[None,None,1.125,1.25])
        self.assertEqual({w['note']for w in result['beat_timing']['warnings']},{0,1})
        self.assertTrue(all(w.get('failure_detail',w['reason'])in
                            ('native_chord_domains_incompatible','beat_grid_conflicts_with_native_chord')
                            for w in result['beat_timing']['warnings']))
