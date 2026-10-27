"""Concurrent native positions can intersect beat domains without nearest-row guessing."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline.play.beats.chords import prepare,constrain,conflicts
from piu_timeline.play.beats.timing import fit_grid,apply


def fixture():
    times=[.6+i*.01 for i in range(9)]
    notes=[{'lane':i,'status':'estimated','target_seconds':target,'prediction_uncertainty_seconds':error,
            'points':[[t,40+500*(actual-t)]for t in times]}
           for i,(target,error,actual)in enumerate(((1.001,.006,1.),(1.02,.03,1.),(1.03125,.002,1.03125)))]
    records=[{'note':i,'status':'registered','coordinate_method':'native_cap_measurements','coordinate_uncertainty_pixels':1.,
              'observations':[{'time':t,'source_pts_seconds':50+t}for t in times]}for i in range(3)]
    return {'notes':notes,'head_registration':{'notes':records},'analysis_width':400,'analysis_height':400,
            'layout':{'receptor_y':.1,'lanes':[{'x':.2+.1*i}for i in range(3)]}}


class BeatChordTest(unittest.TestCase):
    def test_native_chord_resolves_one_ambiguous_member_without_moving_the_time_bounds(self):
        data=fixture();before=deepcopy(data);proofs=prepare(data,40)
        self.assertEqual(len(proofs),1)
        self.assertEqual(proofs[0]['peer_notes'],[0,1])
        proof={**proofs[0],'indices':[0,1]}
        ordinary=fit_grid([n['target_seconds']for n in data['notes']],
                          [n['prediction_uncertainty_seconds']for n in data['notes']],120,0)
        self.assertEqual(ordinary['reason'],'ambiguous_beat_rows')
        constrained=fit_grid([n['target_seconds']for n in data['notes']],
                             [n['prediction_uncertainty_seconds']for n in data['notes']],120,0,
                             native_chords=[proof])
        self.assertEqual(constrained['split'],16)
        self.assertEqual(constrained['rows'],[32,32,33])
        self.assertEqual(constrained['unconstrained_row_domains'],[(32,32),(32,33),(33,33)])
        self.assertEqual(data,before)

    def test_two_remaining_joint_rows_and_unresolvable_pixel_spacing_still_fail(self):
        proof={**prepare(fixture(),40)[0],'indices':[0,1]}
        ambiguous=fit_grid([1.015,1.02],[.03,.03],120,0,splits=[16],native_chords=[proof])
        self.assertEqual(ambiguous['reason'],'ambiguous_beat_rows')
        slow={**proof,'minimum_velocity_pixels_per_second':50}
        self.assertEqual(constrain([(32,32),(32,33)],.03125,[slow]),([(32,32),(32,33)],[]))
        incompatible=fit_grid([1.,1.03125],[.001,.001],120,0,splits=[16],native_chords=[proof])
        self.assertEqual(incompatible['reason'],'native_chord_domains_incompatible')

    def test_bad_registration_different_native_frames_or_motion_cannot_establish_a_chord(self):
        for kind in ('gap','short','few','source_pts','unregistered','uncertain','stationary','nonlinear'):
            with self.subTest(kind=kind):
                data=fixture();record=data['head_registration']['notes'][1]
                if kind=='gap':
                    for p in data['notes'][1]['points']:p[1]+=2
                elif kind=='short':
                    for r in data['head_registration']['notes']:r['observations']=r['observations'][:6]
                elif kind=='few':record['observations']=record['observations'][:3]
                elif kind=='source_pts':record['observations'][0]['source_pts_seconds']+=1
                elif kind=='unregistered':record['coordinate_method']='unverified'
                elif kind=='uncertain':record['coordinate_uncertainty_pixels']=2
                elif kind=='stationary':
                    for n in data['notes'][:2]:
                        for p in n['points']:p[1]=200
                else:
                    for n in data['notes'][:2]:n['points'][4][1]+=5
                if kind=='source_pts':
                    with self.assertRaises(ValueError):prepare(data,40)
                else:self.assertEqual(prepare(data,40),[])

    def test_application_uses_measured_geometry_and_keeps_original_recording_ranges(self):
        data=fixture();before=deepcopy(data)
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);timing=root/'timing.ucs'
            timing.write_text(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'*32)
            ref={'status':'available','timing':str(timing),'song_start_seconds':0,'alignment_uncertainty_seconds':0}
            with patch('piu_timeline.play.beats.timing.reference',return_value=ref):result=apply(data,root)
        self.assertEqual(data,before)
        self.assertEqual([n['target_seconds']for n in result['notes']],[1.,1.,1.03125])
        self.assertEqual(result['notes'][1]['video_target_range'],[.99,1.05])
        self.assertEqual(result['beat_timing']['status'],'restored')
        self.assertEqual(result['beat_timing']['groups'][0]['native_chord_constraints'][0]['source_pts_seconds'],
                         [50+t for t,y in data['notes'][0]['points']])

    def test_cross_group_contradiction_remains_explicit_without_changing_native_evidence(self):
        data=fixture();proof=prepare(data,40);data['notes'][1]['target_seconds']=1.1
        original=deepcopy(data)
        warnings=conflicts(data['notes'],proof)
        self.assertEqual({w['note']for w in warnings},{0,1})
        self.assertTrue(all(w['reason']=='beat_grid_conflicts_with_native_chord'for w in warnings))
        self.assertEqual(data,original)
