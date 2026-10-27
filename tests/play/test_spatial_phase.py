"""A common beat phase must also explain observed inter-head geometry."""
from copy import deepcopy
import unittest

from piu_timeline.play.beat_phase import fit_phase
from piu_timeline.play.beat_timing import spacing_supported_notes


def scenario():
    times=[.4+i/60 for i in range(8)]
    notes=[{'status':'estimated','lane':i,'points':[(t,180+60*i-240*(t-.4))for t in times],
            'target_seconds':target,'motion_target_phase':target*velocity,
            'motion_clock':{'origin':0,'velocity':velocity,'intercept':0}}
           for i,(target,velocity)in enumerate(((1.007,120),(1.507,240)))]
    motion={'samples':[{'time':t,'chunk':0}for t in times],
            'coordinate_registration':{'chunks':[{'chunk':0,'status':'fitted','head_offsets':[
                {'note':0,'offset_pixels':220},{'note':1,'offset_pixels':280}]}]}}
    groups=[{'notes':[0,1],'targets':[1.007,1.507],'errors':[.01,.01],'bpm':120,'origin':0}]
    return notes,motion,groups


class SpatialPhaseTest(unittest.TestCase):
    def test_native_gap_constrains_otherwise_identical_beat_candidates(self):
        notes,motion,groups=scenario();original=deepcopy((notes,motion,groups))
        timing_only=fit_phase(groups,.01)
        validate=lambda fits:spacing_supported_notes(notes,groups,fits,40,motion)
        constrained=fit_phase(groups,.01,consistent_notes=validate)
        self.assertEqual(constrained['status'],'restored')
        self.assertEqual(constrained['consistent_notes'],[0,1])
        self.assertGreater(constrained['phase_range'][0],timing_only['phase_range'][0])
        self.assertEqual(validate(constrained['fits']),(0,1))
        self.assertTrue(any(t['consistent_targets']<t['restored_targets']for t in constrained['phase_trials']))
        self.assertEqual((notes,motion,groups),original)

    def test_no_common_phase_can_hide_a_real_pixel_spacing_conflict(self):
        notes,motion,groups=scenario()
        motion['coordinate_registration']['chunks'][0]['head_offsets'][1]['offset_pixels']+=6
        result=fit_phase(groups,.01,consistent_notes=lambda fits:spacing_supported_notes(notes,groups,fits,40,motion))
        self.assertEqual(result['status'],'failed')
        self.assertTrue(all(fit['status']=='failed'for fit in result['fits']))
        self.assertTrue(all(t['consistent_targets']==0 for t in result['phase_trials']))

    def test_equal_scores_with_different_supported_identities_remain_ambiguous(self):
        group={'targets':[1.],'errors':[.02],'bpm':120,'origin':0}
        result=fit_phase([group],.01,consistent_notes=lambda fits:(0,)if fits[0]['targets'][0]<1 else(1,))
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['reason'],'ambiguous_or_unsupported_song_phase')
