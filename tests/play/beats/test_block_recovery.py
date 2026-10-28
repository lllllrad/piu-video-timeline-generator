"""A complete native block can supply sparse local timing without dropping outliers."""
from copy import deepcopy
import unittest

from piu_timeline.play.beats.coordinates import prepare
from piu_timeline.play.beats.recovery import recover
from tests.play.beats.test_recovery import scenario


def sparse():
    data=scenario();data['analysis_height']=1600;data['layout']['receptor_y']=40/1600
    targets=[3.,3.125,3.25,3.375,4.5,5.5,5.625,5.75,5.875]
    for i,(note,target)in enumerate(zip(data['notes'],targets)):
        note['points']=[(t,40+240*(target-t))for t,_ in note['points']]
        note['beat_reconstruction']={'status':'restored','group_index':0}
        note['video_target_range']=[target-.001,target+.001]
        if i==4:note['timing_reconstruction']['unaccepted_previous_estimate']['target_seconds']=4.48
        else:note.update(target_seconds=target,motion_target_phase=240*target)
        data['scroll_motion']['coordinate_registration']['chunks'][0]['head_offsets'][i]['offset_pixels']=40+240*target
    groups=[{'notes':list(range(9)),'unconstrained_row_domains':[[round(t*8)]*2 for t in targets]}]
    return data,groups


class NativeBlockRecoveryTest(unittest.TestCase):
    def test_sparse_local_references_use_all_independent_rows_in_the_same_native_block(self):
        data,groups=sparse();before=deepcopy(data);support=prepare(data,40,True)
        result=recover(data['notes'],support,[(0,8,120)],0,0,0,groups,spacing=40,motion=data['scroll_motion'])
        self.assertEqual(data['notes'][4]['target_seconds'],4.5)
        self.assertEqual(result[4]['reference_scope'],'complete_native_block')
        refs=result[4]['models'][0]['model']['references']
        self.assertEqual({r['note']for r in refs},set(range(9))-{4})
        self.assertTrue(all(abs(r['target_seconds']-4.48)>.75 for r in refs))
        self.assertEqual(data['notes'][4]['points'],before['notes'][4]['points'])

    def test_a_distant_contradictory_reference_cannot_be_dropped_to_rescue_the_model(self):
        data,groups=sparse()
        data['notes'][0]['points']=[(t,y+4)for t,y in data['notes'][0]['points']]
        data['scroll_motion']['coordinate_registration']['chunks'][0]['head_offsets'][0]['offset_pixels']+=4
        before=deepcopy(data)
        result=recover(data['notes'],prepare(data,40,True),[(0,8,120)],0,0,0,groups,spacing=40,motion=data['scroll_motion'])
        self.assertNotIn(4,result)
        self.assertEqual(data,before)

    def test_native_refined_rows_cannot_supply_the_wider_block_fallback(self):
        data,groups=sparse()
        for domain in groups[0]['unconstrained_row_domains']:domain[1]+=1
        before=deepcopy(data)
        result=recover(data['notes'],prepare(data,40,True),[(0,8,120)],0,0,0,groups,
                       spacing=40,motion=data['scroll_motion'])
        self.assertNotIn(4,result)
        self.assertEqual(data,before)

    def test_fallback_is_not_promoted_if_pair_validation_refutes_a_reference(self):
        data,groups=sparse()
        # A 1.2-pixel row mismatch fits the individual head's 1.5-pixel
        # positional bound but exceeds the existing one-pixel pair bound.
        data['notes'][4]['points']=[(t,y+1.2)for t,y in data['notes'][4]['points']]
        data['scroll_motion']['coordinate_registration']['chunks'][0]['head_offsets'][4]['offset_pixels']+=1.2
        before=deepcopy(data)
        result=recover(data['notes'],prepare(data,40,True),[(0,8,120)],0,0,0,groups,
                       spacing=40,motion=data['scroll_motion'])
        self.assertEqual(result[4]['status'],'failed')
        self.assertEqual(result[4]['reason'],'native_block_recovery_failed_pair_validation')
        self.assertEqual(data,before)
