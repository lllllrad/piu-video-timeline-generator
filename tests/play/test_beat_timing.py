"""Natural subdivisions describe rhythm; increasing Split cannot hide uncertainty."""
import unittest

from piu_timeline.play.beat_timing import fit_grid


class BeatGridTest(unittest.TestCase):
    def test_regular_quarters_use_smallest_split_and_exact_rows(self):
        result=fit_grid([10.001,10.124,10.251,10.374],[.003]*4,120,10)
        self.assertEqual(result['status'],'restored')
        self.assertEqual(result['split'],4)
        self.assertEqual(result['targets'],[10,10.125,10.25,10.375])

    def test_triplets_and_quarters_share_natural_twelve_way_split(self):
        times=[10,10.125,10+1/6,10+1/3]
        result=fit_grid(times,[.0001]*4,120,10)
        self.assertEqual(result['split'],12)

    def test_uncertain_rows_and_unsupported_positions_fail_explicitly(self):
        ambiguous=fit_grid([10.25],[.26],120,10)
        self.assertEqual(ambiguous['reason'],'ambiguous_beat_rows')
        unsupported=fit_grid([10.137],[.000001],120,10)
        self.assertEqual(unsupported['reason'],'no_natural_beat_subdivision')

    def test_increasing_split_cannot_collapse_distinct_rows(self):
        result=fit_grid([10.01,10.11],[.12,.12],120,10)
        self.assertEqual(result['status'],'failed')

    def test_reference_application_keeps_video_ranges_and_marks_ambiguous_notes_failed(self):
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        from piu_timeline.play.beat_timing import apply
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);timing=root/'timing.ucs'
            timing.write_text(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'*32)
            reference={'status':'available','timing':str(timing),'song_start_seconds':10,'alignment_uncertainty_seconds':0}
            data={'notes':[{'status':'estimated','lane':i,'points':[[9.9,200]],
                            'target_seconds':t,'prediction_uncertainty_seconds':.003}
                            for i,t in enumerate([10.001,10.124,10.251])]}
            with patch('piu_timeline.play.beat_timing.reference',return_value=reference):
                result=apply(data,root)
                self.assertEqual(result['beat_timing']['status'],'restored')
                self.assertEqual([n['target_seconds'] for n in result['notes']],[10,10.125,10.25])
                self.assertAlmostEqual(data['notes'][0]['target_seconds'],10.001)
                self.assertEqual(result['notes'][0]['video_target_range'],[9.998,10.004])
                data['notes'][1]['target_seconds']=10.137;data['notes'][1]['prediction_uncertainty_seconds']=.000001
                result=apply(data,root)
                self.assertEqual(result['beat_timing']['status'],'failed')
                self.assertTrue(result['beat_timing']['warnings'])
                self.assertTrue(all(n['status']=='excluded' and n['target_seconds'] is None for n in result['notes']))

    def test_one_common_phase_is_required_instead_of_moving_each_note_independently(self):
        result=fit_grid([10.01,10.135],[.001,.001],120,10,phase_uncertainty=.02)
        self.assertEqual(result['split'],4)
        self.assertAlmostEqual(sum(result['phase_range'])/2,.01)
        conflict=fit_grid([10.01,10.115],[.001,.001],120,10,splits=[4],phase_uncertainty=.02)
        self.assertEqual(conflict['status'],'failed')

    def test_input_associations_are_rebuilt_from_restored_targets_and_failed_notes_are_not_used(self):
        from piu_timeline.play.beat_timing import reassociate
        data={'notes':[{'lane':0,'status':'estimated','target_seconds':1.,'prediction_uncertainty_seconds':.01}],
              'matches':[{'note':99}], 'beat_timing':{'status':'restored'},
              'timing_reconstruction':{'status':'restored'}, 'unsupported_intervals':[],
              'combo_events':[{'before':10,'after':11,'delta':1,'lower_seconds':.99,'upper_seconds':1.01,
                               'status':'excluded','reason':'ambiguous_note_or_combo_association'}]}
        result=reassociate(data,0)
        self.assertEqual([m['note'] for m in result['matches']],[0])
        self.assertEqual(result['matches'][0]['target_seconds'],1.)
        data['notes'][0].update(status='excluded',target_seconds=None,reason='beat_timing_reconstruction_failed')
        data['beat_timing']['status']='failed'
        self.assertEqual(reassociate(data,0)['matches'],[])

    def test_global_phase_is_chosen_before_greedy_local_subdivisions(self):
        from piu_timeline.play.beat_phase import fit_phase
        groups=[{'targets':[10.001,10.124,10.251],'errors':[.003]*3,'bpm':120,'origin':10},
                {'targets':[12.001,12.124,12.251],'errors':[.003]*3,'bpm':120,'origin':10}]
        result=fit_phase(groups,.02)
        self.assertEqual(result['status'],'restored')
        self.assertTrue(all(f['split']==4 for f in result['fits']))
        self.assertAlmostEqual(result['phase'],0,delta=.003)

    def test_phase_without_supported_groups_is_explicitly_failed(self):
        from piu_timeline.play.beat_phase import fit_phase
        group={'targets':[10.137],'errors':[.000001],'bpm':120,'origin':10}
        result=fit_phase([group],0)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['fits'][0]['reason'],'ambiguous_or_unsupported_song_phase')

    def test_constant_catalogue_tempo_extends_short_template_without_changing_original(self):
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        from piu_timeline.play.beat_timing import apply
        from piu_timeline.charts.ucs import constant_tempo,parse
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);timing=root/'timing.ucs'
            original=':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'*8
            timing.write_text(original)
            data={'notes':[{'status':'estimated','lane':0,'points':[[11,200]],
                          'target_seconds':12.125,'prediction_uncertainty_seconds':.001}]}
            ref={'status':'available','timing':str(timing),'song_start_seconds':10,
                 'alignment_uncertainty_seconds':0,'constant_tempo_bpm':'120'}
            with patch('piu_timeline.play.beat_timing.reference',return_value=ref):
                result=apply(data,root)
                self.assertEqual(result['beat_timing']['status'],'restored')
                self.assertEqual(result['notes'][0]['target_seconds'],12.125)
                self.assertTrue(result['beat_timing']['timing_extension']['review_required'])
                for bpm in ('120~240','121',None):
                    ref['constant_tempo_bpm']=bpm;result=apply(data,root)
                    self.assertEqual(result['beat_timing']['status'],'failed')
                    self.assertEqual(result['beat_timing']['warnings'][0]['failure_detail'],'outside_official_timing_sections')
            self.assertFalse(constant_tempo(parse(original+':BPM=240\n.....\n'),'120'))
            self.assertEqual(timing.read_text(),original)
            self.assertEqual(data['notes'][0]['target_seconds'],12.125)
