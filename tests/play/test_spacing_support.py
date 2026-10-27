"""All simultaneous native observations can validate a selected neighbor gap."""
from copy import deepcopy
import unittest

from piu_timeline.play.spacing_checks import registered_gap,spacing_failures


def scenario():
    times=[i/60 for i in range(12)]
    notes=[{'status':'estimated','lane':i,'points':[(t,offset-100*t)for t in points],
            'target_seconds':target,'fit_method':'shared_scroll_clock',
            'motion_target_phase':target*100,'motion_clock':{'origin':0,'velocity':100,'intercept':0}}
           for i,(offset,target,points)in enumerate(((200,1,times),(260,1.6,times),(230,1.3,times[2:10])))]
    motion={'samples':[{'time':t,'chunk':1 if 2<=i<10 else 0}for i,t in enumerate(times)],
            'coordinate_registration':{'chunks':[{'chunk':1,'status':'fitted','head_offsets':[
                {'note':i,'offset_pixels':offset}for i,offset in enumerate((200,260,230))]}]}}
    return notes,motion


class SpacingSupportTest(unittest.TestCase):
    def test_source_time_window_does_not_depend_on_trajectory_storage_order(self):
        notes,motion=scenario();notes=notes[:2]
        notes.insert(0,{'status':'estimated','lane':3,'points':[(.1,100),(7/60,98)]})
        for i,sample in enumerate(motion['samples']):sample['chunk']=1 if i<6 else 0
        motion['coordinate_registration']['chunks'][0]['head_offsets']=[
            {'note':1,'offset_pixels':200},{'note':2,'offset_pixels':260}]
        self.assertEqual(spacing_failures(notes,40,motion),[])

    def test_intervening_third_head_does_not_erase_common_pair_registration(self):
        notes,motion=scenario();before=deepcopy((notes,motion))
        # The pair is adjacent only outside the fitted middle window. Both
        # identities are still observed throughout that fitted window.
        self.assertEqual(spacing_failures(notes,40,motion),[])
        self.assertEqual((notes,motion),before)
        motion['coordinate_registration']['chunks'][0]['head_offsets'][1]['offset_pixels']+=6
        conflicts=spacing_failures(notes,40,motion)
        pair=[w for w in conflicts if w['peer_notes']==[0,1]]
        self.assertEqual(len(pair),2)
        self.assertEqual(pair[0]['reason'],'shared_spacing_reconstruction_conflict')
        self.assertEqual(pair[0]['observed_gap_pixels'],60)
        self.assertEqual(pair[0]['reconstructed_gap_pixels'],66)

    def test_short_or_missing_pair_registration_remains_a_failure(self):
        notes,motion=scenario()
        for index,sample in enumerate(motion['samples']):sample['chunk']=1 if 2<=index<5 else 0
        failures=spacing_failures(notes,40,motion)
        self.assertTrue(any(w['peer_notes']==[0,1]and w['reason']=='shared_spacing_model_unavailable'for w in failures))
        motion['coordinate_registration']['chunks']=[]
        self.assertTrue(spacing_failures(notes,40,motion))

    def test_coobservations_outside_the_validated_interval_cannot_supply_support(self):
        notes,_=scenario();frames={t:1 for t,_ in notes[0]['points']}
        offsets={(1,0):200,(1,1):260}
        samples=[(0.,60),(1/60,60)]
        self.assertIsNone(registered_gap(notes[0],notes[1],samples,offsets,frames,0,1))
        samples=[(.05,60),(.15,60)]
        # Pair registration must contain both identities, not just one.
        self.assertIsNone(registered_gap(notes[0],notes[1],samples,{(1,0):200},frames,0,1))
