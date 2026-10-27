"""Exact boundary roles apply only to verified frames of their own recording."""
from copy import deepcopy
import tempfile
from pathlib import Path
import unittest

from piu_timeline.charts.gimmicks import validate_candidates
from piu_timeline.play.object_boundaries import prepare
from piu_timeline.play.object_roles import ownership
from tests.play.test_object_roles import effect


def fixture():
    data={'media':{'size_bytes':123,'mtime_ns':456},'segment_number':2,'player':None}
    frames=[{'playback_seconds':t,'source_pts_seconds':100+t}for t in (.095,.105,.2)]
    e=effect();e['evidence']=[{'source_id':'recording','segment_number':2,'player':None,'media_size_bytes':123,'media_mtime_ns':456,
                             'object_role_frames':[{'role':role,**frame}for role,frame in
                                                   zip(('ordinary_candidate','decorative_art'),frames[:2])]}]
    return data,frames,e


class ObjectBoundaryTest(unittest.TestCase):
    def test_verified_frames_resolve_time_ambiguity_without_resolving_partial_geometry(self):
        data,frames,e=fixture();original=deepcopy((data,frames,e))
        with tempfile.TemporaryDirectory()as tmp:
            directory=Path(tmp)/'recording/play/segment-002'
            prepared=prepare(data,directory,e,frames)
        self.assertEqual((data,frames,e),original)
        bounds=[.3,.3,.5,.7]
        self.assertEqual(ownership(bounds,.095,[e]),([],['cards']))
        self.assertEqual(ownership(bounds,.095,[prepared]),([],[]))
        self.assertEqual(ownership(bounds,.105,[prepared]),(['cards'],[]))
        self.assertEqual(ownership([.2,.3,.4,.7],.105,[prepared]),([],['cards']))
        self.assertEqual([r['source_pts_seconds']for r in prepared['source_frame_roles']],[100.095,100.105])
        self.assertEqual([r['native_frame']for r in prepared['source_frame_roles']],[0,1])
        self.assertEqual(ownership(bounds,.1,[prepared]),([],['cards']))

    def test_different_recording_or_play_keeps_the_ordinary_uncertainty(self):
        data,frames,e=fixture()
        with tempfile.TemporaryDirectory()as tmp:
            other=prepare(data,Path(tmp)/'other/play/segment-002',e,frames)
            self.assertEqual(other['source_frame_roles'],[])
            self.assertEqual(ownership([.3,.3,.5,.7],.105,[other]),([],['cards']))
            data['segment_number']=3
            self.assertEqual(prepare(data,Path(tmp)/'recording/play/segment-003',e,frames)['source_frame_roles'],[])
            data.update(segment_number=2,player='P2')
            self.assertEqual(prepare(data,Path(tmp)/'recording/play/segment-002',e,frames)['source_frame_roles'],[])

    def test_changed_media_missing_or_duplicate_frame_and_interior_annotation_fail_explicitly(self):
        for case in ('media','pts','playback','duplicate_annotation','duplicate_native','interior'):
            with self.subTest(case=case),tempfile.TemporaryDirectory()as tmp:
                data,frames,e=fixture();annotations=e['evidence'][0]['object_role_frames']
                if case=='media':data['media']['mtime_ns']+=1
                elif case=='pts':annotations[0]['source_pts_seconds']+=.001
                elif case=='playback':annotations[0]['playback_seconds']+=.001
                elif case=='duplicate_annotation':annotations.append(dict(annotations[0]))
                elif case=='duplicate_native':frames.append(dict(frames[0]))
                else:annotations[0].update(frames[2])
                with self.assertRaises(ValueError):prepare(data,Path(tmp)/'recording/play/segment-002',e,frames)

    def test_invalid_annotation_role_clock_or_recording_identity_is_rejected(self):
        data,frames,e=fixture()
        self.assertEqual(len(validate_candidates({'gimmick_candidates':[e]})),1)
        for key,value in [('role','confirmed_input'),('playback_seconds',True),
                          ('source_pts_seconds',float('nan'))]:
            candidate=deepcopy(e);candidate['evidence'][0]['object_role_frames'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_candidates({'gimmick_candidates':[candidate]})
        for key in ('source_id','media_size_bytes','segment_number','player'):
            candidate=deepcopy(e);candidate['evidence'][0].pop(key)
            with self.subTest(key=key),self.assertRaises(ValueError):validate_candidates({'gimmick_candidates':[candidate]})
