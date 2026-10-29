"""Native spacing can resolve a broad domain without adding a possible beat row."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline.play.beats.coordinates import prepare
from piu_timeline.play.beats.timing import apply, fit_grid
from tests.play.beats.test_coordinates import fixture


def scenario():
    data=fixture();data['analysis_width']=400
    data['layout']['lanes']=[{'x':.1+.1*i}for i in range(3)]
    for i,note in enumerate(data['notes']):note['prediction_uncertainty_seconds']=.13 if i==4 else .001
    return data


class NativeRowDomainTest(unittest.TestCase):
    def test_actual_registered_positions_resolve_an_ambiguous_row_and_keep_native_provenance(self):
        data=scenario();original=deepcopy(data)
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);timing=root/'timing.ucs'
            timing.write_text(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'*32)
            reference={'status':'available','timing':str(timing),'song_start_seconds':1,'alignment_uncertainty_seconds':0}
            with patch('piu_timeline.play.beats.timing.reference',return_value=reference):
                result=apply(data,root)
        self.assertEqual(result['beat_timing']['status'],'restored')
        self.assertTrue(all(n['status']=='estimated'for n in result['notes']))
        group=result['beat_timing']['groups'][0]
        self.assertEqual(group['split'],4)
        proof=next(p for p in group['native_coordinate_constraints']if p['index']==4)
        self.assertEqual(proof['index'],4)
        self.assertEqual(proof['original_domain'],[3,5])
        self.assertEqual(proof['allowed_domain'],[4,4])
        self.assertNotIn(4,[r['note']for r in proof['model']['references']])
        self.assertEqual(proof['model']['references'][0]['source_pts_range'],[80.5,80.68])
        self.assertEqual(result['notes'][4]['video_target_range'],[1.37,1.63])
        self.assertEqual(data,original)

    def test_insufficient_contradictory_or_unbracketed_geometry_cannot_resolve_a_row(self):
        for case in ('four_references','unmeasured_head','bad_reference','extrapolation','fine_ambiguous'):
            data=scenario()
            if case=='four_references':
                for r in data['head_registration']['notes'][5:]:r.update(status='unresolved',coordinate_method='unverified')
            elif case=='unmeasured_head':data['head_registration']['notes'][4].update(status='unresolved',coordinate_method='unverified')
            elif case=='bad_reference':
                data['notes'][2]['points']=[(t,y+12)for t,y in data['notes'][2]['points']]
                data['scroll_motion']['coordinate_registration']['chunks'][0]['head_offsets'][2]['offset_pixels']+=12
            elif case=='extrapolation':
                data['notes'][4]['prediction_uncertainty_seconds']=.001
                data['notes'][0]['prediction_uncertainty_seconds']=.13
            support=prepare(data,40)
            blocks=[{'chunk':number,'lane_spacing_pixels':support['lane_spacing_pixels'],'heads':heads}for number,heads in support['chunks'].items()]
            targets=[n['target_seconds']for n in data['notes']]
            errors=[n['prediction_uncertainty_seconds']for n in data['notes']]
            result=fit_grid(targets,errors,120,1,splits=[192]if case=='fine_ambiguous'else None,
                            native_coordinates=blocks)
            with self.subTest(case=case):
                if case=='bad_reference':
                    self.assertEqual(result['status'],'partial')
                    self.assertEqual(result['reason'],'native_coordinate_domains_incompatible')
                    self.assertIsNone(result['targets'][2])
                    self.assertIsNone(result['targets'][4])
                    continue
                self.assertEqual(result['status'],'partial')
                self.assertIsNone(result['rows'][0 if case=='extrapolation'else 4])
                self.assertIsNone(result['targets'][0 if case=='extrapolation'else 4])
                self.assertEqual(result['reason'],'ambiguous_beat_rows')

    def test_geometry_can_refute_a_coarse_split_without_forcing_its_nearest_row(self):
        data=scenario()
        data['notes'][4]['points']=[(t,y+15)for t,y in data['notes'][4]['points']]
        data['scroll_motion']['coordinate_registration']['chunks'][0]['head_offsets'][4]['offset_pixels']+=15
        support=prepare(data,40)
        blocks=[{'chunk':number,'lane_spacing_pixels':support['lane_spacing_pixels'],'heads':heads}for number,heads in support['chunks'].items()]
        result=fit_grid([n['target_seconds']for n in data['notes']],
                        [n['prediction_uncertainty_seconds']for n in data['notes']],120,1,
                        native_coordinates=blocks)
        self.assertEqual(result['status'],'restored')
        self.assertEqual(result['split'],8)
        self.assertEqual(result['targets'][4],1.5625)

    def test_a_unique_time_row_still_has_to_agree_with_independent_native_positions(self):
        data=scenario();data['notes'][4]['prediction_uncertainty_seconds']=.001
        data['notes'][4]['points']=[(t,y+15)for t,y in data['notes'][4]['points']]
        data['scroll_motion']['coordinate_registration']['chunks'][0]['head_offsets'][4]['offset_pixels']+=15
        support=prepare(data,40)
        result=fit_grid([n['target_seconds']for n in data['notes']],
                        [n['prediction_uncertainty_seconds']for n in data['notes']],120,1,
                        native_coordinates=[{'chunk':c,'lane_spacing_pixels':support['lane_spacing_pixels'],'heads':h}for c,h in support['chunks'].items()])
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['reason'],'native_coordinate_domains_incompatible')
        self.assertIsNone(result['targets'][4])
        self.assertTrue(all(t is not None for i,t in enumerate(result['targets'])if i!=4))
