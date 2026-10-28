"""A rejected clock interval must not veto independently proven chart geometry."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline.play.beats.coordinates import prepare
from piu_timeline.play.beats.recovery import recover
from piu_timeline.play.beats.timing import apply
from tests.play.beats.test_coordinates import fixture


def scenario():
    data=fixture();groups=[]
    for ids in ([3,4,5],[0,1,2],[6,7,8]):
        groups.append({'notes':ids,'unconstrained_row_domains':[[8+i,8+i]for i in ids]})
        for i in ids:
            note=data['notes'][i]
            note.update(beat_reconstruction={'status':'restored','group_index':len(groups)-1},
                        video_target_range=[note['target_seconds']-.001,note['target_seconds']+.001])
    data['notes'][4].update(status='excluded',reason='beat_timing_reconstruction_failed',target_seconds=None,
        video_target_range=[1.519,1.522],timing_reconstruction={'status':'restored','method':'source_clock'},
        beat_reconstruction={'status':'failed','reason':'native_coordinate_domains_incompatible','group_index':0})
    return data,groups


class RejectedClockRecoveryTest(unittest.TestCase):
    def test_spacing_and_chord_failures_require_independent_external_rows(self):
        for reason in ('beat_grid_conflicts_with_spatial_spacing','beat_grid_conflicts_with_native_chord'):
            with self.subTest(reason=reason):
                data,groups=scenario();note=data['notes'][4]
                note['reason']=reason;note['beat_reconstruction']['reason']=reason
                support=prepare(data,40,include_failed=True)
                proof=recover(data['notes'],support,[(0,4,120)],0,0,0,groups,[0,0])[4]
                self.assertEqual(note['target_seconds'],1.5)
                self.assertEqual(proof['source_failure'],reason)
                self.assertEqual(proof['excluded_reference_group'],[3,4,5])
                self.assertEqual(note['timing_reconstruction']['rejected_beat_assignment']['reason'],reason)
                data,groups=scenario();note=data['notes'][4]
                note['reason']=reason;note['beat_reconstruction']['reason']=reason
                for group in groups[1:]:
                    group['unconstrained_row_domains']=[[lo,hi+1]for lo,hi in group['unconstrained_row_domains']]
                recover(data['notes'],prepare(data,40,include_failed=True),[(0,4,120)],0,0,0,groups,[0,0])
                self.assertEqual(note['status'],'excluded')

    def test_an_ambiguous_clock_keeps_its_original_bound_and_uses_native_geometry_to_choose(self):
        data,groups=scenario();note=data['notes'][4]
        note['beat_reconstruction']['reason']='ambiguous_beat_rows';note['video_target_range']=[1.37,1.63]
        support=prepare(data,40,include_failed=True)
        result=recover(data['notes'],support,[(0,4,120)],0,0,0,groups,[0,0])
        self.assertEqual(note['target_seconds'],1.5)
        self.assertEqual(result[4]['clock_constraint_range'],[1.37,1.63])

    def test_unique_external_clock_rows_prove_a_target_outside_the_rejected_interval(self):
        data,groups=scenario();original=deepcopy(data);support=prepare(data,40,include_failed=True)
        result=recover(data['notes'],support,[(0,4,120)],0,0,.01,groups,[-.0005,.0005])
        note=data['notes'][4];proof=result[4]
        self.assertEqual(note['target_seconds'],1.5)
        self.assertLess(note['target_seconds'],original['notes'][4]['video_target_range'][0])
        self.assertEqual(note['points'],original['notes'][4]['points'])
        self.assertEqual(note['motion_clock'],original['notes'][4]['motion_clock'])
        self.assertEqual(proof['source_timing']['range'],[1.519,1.522])
        self.assertTrue(proof['source_timing']['independent'])
        self.assertEqual(note['timing_reconstruction']['rejected_beat_assignment'],original['notes'][4]['beat_reconstruction'])
        self.assertEqual(proof['excluded_reference_group'],[3,4,5])
        for model in proof['models']:
            self.assertEqual({r['note']for r in model['model']['references']},{0,1,2,6,7,8})

    def test_refined_phase_unstable_insufficient_or_contradictory_references_do_not_prove_a_target(self):
        for case in ('refined','phase_boundary','insufficient','contradiction','other_failure'):
            data,groups=scenario();phase_range=[-.0005,.0005]
            if case=='refined':
                for g in groups[1:]:g['unconstrained_row_domains']=[[a,b+1]for a,b in g['unconstrained_row_domains']]
            elif case=='phase_boundary':phase_range=[-.002,.002]
            elif case=='insufficient':
                for i in(0,1,2):data['head_registration']['notes'][i]['status']='unresolved'
            elif case=='contradiction':
                data['notes'][0]['points']=[(t,y+10)for t,y in data['notes'][0]['points']]
                data['scroll_motion']['coordinate_registration']['chunks'][0]['head_offsets'][0]['offset_pixels']+=10
            else:data['notes'][4]['beat_reconstruction']['reason']='ambiguous_beat_rows'
            support=prepare(data,40,include_failed=True)
            recover(data['notes'],support,[(0,4,120)],0,0,0,groups,phase_range)
            with self.subTest(case=case):
                self.assertEqual(data['notes'][4]['status'],'excluded')
                self.assertIsNone(data['notes'][4]['target_seconds'])

    def test_full_application_retires_the_rejected_beat_warning_after_independent_validation(self):
        self.check_application(False)

    def test_invalid_external_rows_are_removed_before_freezing_recovery_references(self):
        self.check_application(True)

    def check_application(self,unregistered_neighbor):
        data=fixture();times=[s['time']for s in data['scroll_motion']['samples']]
        targets=[1.25+i*.125 for i in range(32)]
        data['analysis_width']=400;data['analysis_height']=1400
        data['layout']={'receptor_y':40/1400,'lanes':[{'x':.1+.1*i}for i in range(3)]}
        data['notes']=[{'lane':i%3,'status':'estimated','target_seconds':t,
                        'prediction_uncertainty_seconds':.001,
                        'points':[(s,40+240*(t-s))for s in times],
                        'motion_clock':{'origin':0,'velocity':240,'intercept':0},'motion_target_phase':240*t,
                        'timing_reconstruction':{'status':'restored'}}for i,t in enumerate(targets)]
        data['head_registration']['notes']=[{'note':i,'status':'registered','observations':[{'time':t}for t in times]}for i in range(32)]
        data['scroll_motion']['coordinate_registration']['chunks'][0]['head_offsets']=[{'note':i,'offset_pixels':40+240*t}for i,t in enumerate(targets)]
        if unregistered_neighbor:
            data['notes'].append({'lane':2,'status':'estimated','target_seconds':1.25,
                'prediction_uncertainty_seconds':.001,'points':[(t,40+240*(.9-t))for t in times],
                'motion_clock':{'origin':0,'velocity':240,'intercept':0},'motion_target_phase':240*.9,
                'timing_reconstruction':{'status':'restored'}})
            data['head_registration']['notes'].append({'note':32,'status':'unresolved','observations':[{'time':t}for t in times]})
            data['scroll_motion']['coordinate_registration']['chunks'][0]['head_offsets'].append({'note':32,'offset_pixels':40+240*.9})
        data['notes'][12]['target_seconds']+=1/48
        data['timing_reconstruction']={'status':'failed','restored_notes':len(data['notes']),
                                     'warnings':[{'note':12,'reason':'shared_motion_observation_conflict'}]}
        original=deepcopy(data)
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);timing=root/'timing.ucs'
            timing.write_text(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'*64)
            reference={'status':'available','timing':str(timing),'song_start_seconds':0,'alignment_uncertainty_seconds':0}
            with patch('piu_timeline.play.beats.timing.reference',return_value=reference):result=apply(data,root)
        self.assertEqual(result['notes'][12]['target_seconds'],2.75)
        self.assertEqual(result['notes'][12]['fit_method'],'native_beat_coordinate_interpolation')
        if unregistered_neighbor:
            self.assertEqual(result['notes'][0]['status'],'excluded')
            proof=next(p for p in result['beat_timing']['native_coordinate_recovery']if p['note']==12)
            self.assertTrue(all(0 not in[r['note']for r in m['model']['references']]for m in proof['models']))
        else:self.assertEqual(result['beat_timing']['warnings'],[])
        self.assertEqual(result['timing_reconstruction']['warnings'],original['timing_reconstruction']['warnings'])
        self.assertEqual(result['timing_reconstruction']['restored_notes'],len(data['notes']))
        self.assertEqual(data,original)
