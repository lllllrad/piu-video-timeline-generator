"""Partial positive pixels may prove passage, never a press or disappearance."""
from copy import deepcopy
import unittest

from piu_timeline.play.processing import transition
from piu_timeline.play.processing.passage import evidence,after_refresh
from piu_timeline.play.channels import annotate_matches


def samples():
    return [{'time':1.1,'pts':11.1,'y':10.,'state':'present','score':.9},
            {'time':1.117,'pts':11.117,'y':6.,'state':'unknown','score':.8,
             'unknown_reason':'partial_head_present','confirmation_only':True,
             'template_coverage':{'area_fraction':.85,'foreground_fraction':.95}}]


class PassageTest(unittest.TestCase):
    def test_partial_positive_corroborates_passage_with_original_pts(self):
        values=samples();result=transition(values,25,20)
        self.assertEqual(result['status'],'passed_target')
        self.assertEqual(result['passage_evidence']['range'],[1.1,1.117])
        self.assertEqual(result['passage_evidence']['source_pts_seconds'],[11.1,11.117])
        self.assertEqual(result['passage_evidence']['partial_presence'],[False,True])
        self.assertNotIn('range',result)
        self.assertIsNotNone(after_refresh(result,1.017))
        self.assertIsNone(after_refresh(result,1.05))

    def test_occlusion_low_coverage_static_shape_or_capture_gap_is_not_passage(self):
        for case in ('white','area','foreground','score','gap','stationary','reversed'):
            with self.subTest(case=case):
                values=samples();last=values[-1]
                if case=='white':last['unknown_reason']='white_effect'
                elif case in('area','foreground'):last['template_coverage'][case+'_fraction']=.7
                elif case=='score':last['score']=.5
                elif case=='gap':last['time']=1.2
                elif case=='stationary':last['y']=values[0]['y']
                else:last['y']=values[0]['y']+1
                self.assertIsNone(evidence(values,25,20,.8))

    def test_annotation_exposes_ordering_conflict_without_replacing_input(self):
        event={'note':0,**transition(samples(),25,20)}
        match={'note':0,'target_seconds':1.08,'judgment_event':0,'judgment_label':'GOOD',
               'observation_lower_seconds':1.,'observation_upper_seconds':1.017}
        data={'notes':[{'lane':0}],'matches':[match],
              'visual_channels':{'processing':{'notes':[event]},'receptors':{'events':[]}}}
        original=deepcopy(data);annotated=annotate_matches(data)
        self.assertEqual(annotated['matches'],[])
        result=annotated['conflicted_matches'][0]
        self.assertTrue(result['processing_conflict'])
        self.assertEqual(result['processing_passage_after_refresh'],event['passage_evidence'])
        self.assertEqual([result[k]for k in match],[match[k]for k in match])
        self.assertEqual(data,original)
        # Replaying changed observations removes stale interpretation.
        data=annotated;event.update(status='unresolved');event.pop('passage_evidence')
        refreshed=annotate_matches(data)['matches'][0]
        self.assertNotIn('processing_passage_after_refresh',refreshed)
        self.assertNotIn('processing_conflict',refreshed)
