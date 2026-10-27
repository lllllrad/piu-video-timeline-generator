"""Hold caps are visual boundaries, not additional required tap inputs."""
from copy import deepcopy
import unittest

from piu_timeline.play.holds.analysis import chart_projection, presentation
from piu_timeline.play.holds.state import recognition_segments
from piu_timeline.play.ranges import timing_ranges
from tests.play.test_deferred import evidence


class HoldSemanticsTest(unittest.TestCase):
    def test_failed_head_reconstruction_cannot_project_a_body_without_a_chart_anchor(self):
        source=evidence();hold=source['hold_analysis']['holds'][0]
        source['notes'][0].update(timing_reconstruction={'status':'failed'})
        hold.update(start_censored=True,head_note=None,head_observation_note=0,
                    covered_notes=[],last_body_seconds=10.9)
        original=deepcopy(source)
        view=presentation(source)
        self.assertEqual(view['hold_analysis']['holds'],[])
        rejected=view['hold_analysis']['unresolved_holds']
        self.assertEqual(len(rejected),1)
        self.assertEqual(rejected[0]['projection_failure'],'timing_reconstruction_failed')
        self.assertEqual(view['notes'][rejected[0]['display_note']]['status'],'excluded')
        self.assertEqual(view['coverage']['long_notes'],0)
        self.assertEqual(source,original)
        from piu_timeline.play.exclusions import recognition_diagnostics
        warnings=recognition_diagnostics(view,{'notes':{}})['warnings']
        self.assertTrue(any(w['reason']=='hold_chart_projection_failed'for w in warnings))
        self.assertTrue(any(w['reason']=='hold_start_unresolved'for w in warnings))

    def test_linked_caps_outside_covered_envelope_cannot_become_extra_taps(self):
        source=evidence();hold=source['hold_analysis']['holds'][0]
        hold['covered_notes']=[]
        hold['tail_note']=2
        source['notes'].append({'status':'estimated','lane':0,'target_seconds':11.01,
                                'prediction_uncertainty_seconds':.01})
        source['matches']=[{'note':0,'target_seconds':9.01,'combo_event':0,
                           'observation_lower_seconds':9,'observation_upper_seconds':9.02}]
        original=deepcopy(source)
        chart=chart_projection(source)
        self.assertEqual(len(chart['notes']),3)
        self.assertEqual(chart['notes'][0]['note_type'],'hold')
        self.assertEqual(chart['notes'][2]['status'],'excluded')
        self.assertEqual(chart['hold_analysis']['holds'][0]['covered_notes'],[0,2])
        view=presentation(source)
        self.assertNotIn(0,[m['note']for m in view['matches']])
        self.assertNotIn(2,[m['note']for m in view['matches']])
        self.assertEqual(source,original)

    def test_preheld_lane_counts_without_an_onset_at_the_visual_head(self):
        times=[8.9,8.95,9.,9.05,9.1,9.15,9.2]
        frames=[{'playback_seconds':t,'source_pts_seconds':t+10,'receptor_lit':[True]}for t in times]
        hold={'lane':0,'start_range':[9.,9.01],'end_range':[9.2,9.21],
              'start_censored':False,'last_body_seconds':9.2}
        state=recognition_segments(frames,times,hold,{})
        self.assertEqual(state['recognition_envelope'],[9.,9.2])
        self.assertIsNone(state['press_range'])
        source=evidence();source['hold_analysis']['holds'][0]['input']=state
        view=presentation(source);ranges=timing_ranges(view)
        record=ranges['notes'][0]
        self.assertEqual(record['status'],'hold_state')
        self.assertEqual(record['input_requirement'],'held_state')
        self.assertFalse(record['requires_head_press'])
        self.assertIsNone(record['press_range'])
