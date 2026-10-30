"""Native detector completeness controls receptor-risk interpretation."""
from copy import deepcopy
import unittest
from piu_timeline.play.aggregates import recover_aggregates
from tests.play.holds.aggregate_fixture import evidence


class NativeRiskAdapterTest(unittest.TestCase):
    def test_unowned_image_tile_summary_is_not_a_continuous_hold_at_the_receptors(self):
        from piu_timeline.play.skins.held import FORMAT
        data=evidence()
        data.update(skin_detector={'contract':{'held_body':FORMAT},'missing_template_roles':[]},unsupported_intervals=[])
        warning={'visible_start_seconds':.1,'visible_end_seconds':2.,
                 'failure_detail':'skin_body_images_without_complete_endpoint_ownership',
                 'image_evidence':[{'role':'hold_body','playback_seconds':t}for t in(.1,2.)]}
        data['hold_analysis']['unresolved_tracks']=[warning]
        original=deepcopy(data)
        matches,recovered=recover_aggregates(data)
        self.assertEqual(recovered,[1]);self.assertEqual(data,original)
        self.assertEqual(matches[1]['aggregate_body_risk_basis'],'native_receptor_body_regions')
        for case in ('active_body','missing_role','old_detector','connected_body','missing_evidence'):
            with self.subTest(case=case):
                changed=deepcopy(data)
                if case=='active_body':changed['unsupported_intervals']=[{'start_seconds':1.,'end_seconds':1.1}]
                elif case=='missing_role':changed['skin_detector']['missing_template_roles']=[{'role':'hold_body'}]
                elif case=='old_detector':changed['skin_detector']['contract']['held_body']={}
                elif case=='connected_body':changed['hold_analysis']['unresolved_tracks'][0]['failure_detail']='unresolved_connected_body'
                else:changed['hold_analysis']['unresolved_tracks'][0].pop('image_evidence')
                self.assertEqual(recover_aggregates(changed)[1],[])
