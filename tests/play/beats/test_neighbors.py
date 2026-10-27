"""Measure boundaries do not erase independently observed spatial references."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline.play.beats.phase import fit_phase
from piu_timeline.play.beats.timing import apply
from tests.play.beats.test_coordinates import fixture
from tests.play.beats.test_domains import scenario as local_scenario
from piu_timeline.play.beats.coordinates import prepare


def scenario():
    targets=[1.5,1.625,1.75,1.875,2,2.125,2.25,2.375]
    heads={i:{'offset':500*t,'lane':i%3,'native_note':i,
              'source_pts_range':[80,80.2]}for i,t in enumerate(targets)}
    groups=[]
    for indices in (list(range(4)),list(range(4,8))):
        groups.append({'notes':indices,'targets':[targets[i]for i in indices],
                       'errors':[.13 if i==3 else .001 for i in indices],
                       'bpm':120,'origin':0,'native_coordinates':[
                           {'chunk':1,'heads':{j:heads[i]for j,i in enumerate(indices)},
                            'neighbor_heads':{i:h for i,h in heads.items()if i not in indices}}]})
    return groups


class NeighborReferenceTest(unittest.TestCase):
    def test_incompatible_neighbors_cannot_erase_an_existing_local_coordinate_constraint(self):
        data=local_scenario();heads=prepare(data,40)['chunks'][0]
        group={'notes':list(range(9)),'targets':[n['target_seconds']for n in data['notes']],
               'errors':[n['prediction_uncertainty_seconds']for n in data['notes']],
               'bpm':120,'origin':1,'native_coordinates':[{'chunk':0,'heads':heads,
                   'neighbor_heads':{9:{'offset':1000,'lane':0,'native_note':9}}}]}
        neighbor={'notes':[9],'targets':[2.125],'errors':[.001],'bpm':120,'origin':1}
        result=fit_phase([group,neighbor],0)
        self.assertEqual(result['fits'][0]['status'],'restored')
        self.assertEqual(result['fits'][0]['targets'][4],1.5)

    def test_application_preserves_both_lanes_of_an_ambiguous_chord_at_a_measure_end(self):
        data=fixture();data['analysis_width']=400
        data['layout']['lanes']=[{'x':.1+.1*i}for i in range(3)]
        targets=[1.5,1.625,1.75,1.875,1.875,2,2.125,2.25,2.375]
        offsets=data['scroll_motion']['coordinate_registration']['chunks'][0]['head_offsets']
        for i,(note,target)in enumerate(zip(data['notes'],targets,strict=True)):
            note.update(target_seconds=target,prediction_uncertainty_seconds=.13 if i in(3,4)else .001,
                        motion_target_phase=240*target,motion_clock={'origin':0,'velocity':240,'intercept':0})
            note['points']=[(t,40+240*(target-t))for t,_ in note['points']]
            offsets[i]['offset_pixels']=40+240*target
        original=deepcopy(data)
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);timing=root/'timing.ucs'
            timing.write_text(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'*32)
            reference={'status':'available','timing':str(timing),'song_start_seconds':0,'alignment_uncertainty_seconds':0}
            with patch('piu_timeline.play.beats.timing.reference',return_value=reference):result=apply(data,root)
        self.assertEqual(result['beat_timing']['status'],'restored')
        self.assertEqual([n['target_seconds']for n in result['notes']],targets)
        self.assertTrue(all(n['status']=='estimated'for n in result['notes']))
        self.assertEqual(data,original)

    def test_unique_next_measure_rows_resolve_the_last_head_without_changing_source_data(self):
        groups=scenario();original=deepcopy(groups)
        result=fit_phase(groups,0)
        fit=result['fits'][0]
        self.assertEqual(fit['status'],'restored')
        self.assertEqual(fit['targets'],[1.5,1.625,1.75,1.875])
        proof=fit['native_coordinate_constraints'][0]
        refs=proof['model']['references']
        self.assertNotIn(3,[r['note']for r in refs])
        self.assertTrue(any(r['note']>=4 for r in refs))
        self.assertEqual(refs[0]['source_pts_range'],[80,80.2])
        self.assertEqual(groups,original)

    def test_unmeasured_other_tempo_ambiguous_and_contradictory_neighbors_cannot_resolve(self):
        for case in ('unmeasured','other_tempo','ambiguous','contradictory','unbracketed'):
            groups=scenario()
            if case=='unmeasured':groups[0]['native_coordinates'][0]['neighbor_heads']={}
            elif case=='other_tempo':groups[1]['bpm']=240
            elif case=='ambiguous':groups[1]['errors']=[.13]*4
            elif case=='contradictory':groups[0]['native_coordinates'][0]['neighbor_heads'][5]['offset']+=8
            else:
                groups[0]['native_coordinates'][0]['heads'][3]['offset']=1250
                groups[0]['targets'][3]=2.5
            result=fit_phase(groups,0)
            with self.subTest(case=case):
                fit=result['fits'][0]
                self.assertNotEqual(fit['status'],'restored')
                if fit['status']=='partial':self.assertIsNone(fit['targets'][3])
