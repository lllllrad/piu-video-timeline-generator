"""Configured artwork changes derived roles, never original frame observations."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline.play import object_roles as roles
from piu_timeline.charts.gimmicks import validate_candidates


def effect():
    return {'id':'cards','kind':roles.KIND,'review_status':'pending','reason':'Decorative cards in a bounded empty field',
            'note_semantics':'decorative_non_playable','playable_notes_present':False,
            'display_content':'Cards forming a letter',
            'start_seconds':.1,'end_seconds':.3,'playback_start_seconds':.1,'playback_end_seconds':.3,
            'game_image_bounds':[.29,.29,.22,.42],'boundary_uncertainty_seconds':.01}


def geometry():
    return {'analysis_width':200,'analysis_height':200,'game_roi':[0,0,200,200],
            'layout':{'receptor_y':.1,'note_y_max':.95,
                      'lanes':[{'x':.2+i*.2,'color':'red'}for i in range(3)]}}


class ObjectRoleTest(unittest.TestCase):
    def test_whole_non_playable_interval_skips_all_lanes_but_preserves_uncertain_boundaries(self):
        e=effect();e['chart_processing']='skip_non_playable_interval'
        data=geometry();data['object_interpretation']={'effects':[e]}
        frames=[{'playback_seconds':t,'source_pts_seconds':100+t,
                 'notes':[{'lane':0,'x':.2,'y':.8},{'lane':2,'x':.6,'y':.8}],
                 'skin_observations':[{'role':'hold_body'}],
                 'possible_hold_or_dense_stack':True}for t in (.105,.2,.32)]
        original=deepcopy(frames);view=roles.filter_frames(data,frames)
        self.assertEqual(view[0]['notes'],frames[0]['notes'])
        self.assertEqual(view[1]['notes'],[])
        self.assertEqual(view[1]['skin_observations'],[])
        self.assertFalse(view[1]['possible_hold_or_dense_stack'])
        self.assertEqual(view[2]['notes'],frames[2]['notes'])
        self.assertEqual(frames,original)
        body=[{'playback_seconds':.2,'bodies':[{'source_components':[1]}]}]
        self.assertEqual(roles.filter_frames(data,body,bodies=True)[0]['bodies'],[])
        self.assertEqual(roles.ownership([.7,.6,.9,.8],.105,[e]),([],['cards']))
        e['source_frame_roles']=[{'role':'ordinary_candidate','playback_seconds':.105}]
        self.assertEqual(roles.ownership([.7,.6,.9,.8],.105,[e]),([],[]))
        with self.assertRaises(ValueError):
            validate_candidates({'gimmick_candidates':[{**e,'playable_notes_present':True}]})

    def test_non_playable_skip_records_empty_frames_with_original_pts(self):
        e={**effect(),'chart_processing':'skip_non_playable_interval'}
        data=geometry();frames=[{'playback_seconds':t,'source_pts_seconds':100+t,'notes':[],
                                'combo':None}for t in (.12,.14,.16,.18,.2)]
        data.update(frame_count=len(frames),notes=[])
        prepared={**data,'chart_policy':{'status':'applied','alignment':{'uncertainty_seconds':0},
                                       'gimmick_candidates':[e]}}
        with tempfile.TemporaryDirectory()as tmp:
            directory=Path(tmp);trace=directory/'frames.jsonl'
            trace.write_text(''.join(json.dumps(f)+'\n'for f in frames));before=trace.read_bytes()
            with patch.object(roles,'reference',return_value={'format':roles.FORMAT,'candidates':[e]}),\
                    patch('piu_timeline.charts.policy.attach_regions',return_value=prepared):
                result=roles.apply(data,directory)
            self.assertEqual(trace.read_bytes(),before)
        self.assertEqual(result['notes'],[])
        self.assertEqual([r['source_pts_seconds']for r in result['object_interpretation']['skipped_frames']],
                         [r['source_pts_seconds']for r in frames])

    def test_only_certain_time_and_fully_contained_footprint_are_classified(self):
        e=effect();bounds=[.3,.3,.5,.7]
        self.assertEqual(roles.ownership(bounds,.2,[e]),(['cards'],[]))
        for time in (.095,.105,.295,.305):
            self.assertEqual(roles.ownership(bounds,time,[e]),([],['cards']))
        self.assertEqual(roles.ownership(bounds,.32,[e]),([],[]))
        self.assertEqual(roles.ownership([.2,.3,.4,.7],.2,[e]),([],['cards']))
        self.assertEqual(roles.ownership([.6,.3,.8,.7],.2,[e]),([],[]))
        e['alignment_uncertainty_seconds']=.02
        self.assertEqual(roles.ownership(bounds,.12,[e]),([],['cards']))

    def test_replay_splits_art_from_a_playable_prefix_without_mutating_native_trace(self):
        data=geometry();frames=[]
        for time,y in [(i*.02,.9-i*.1)for i in range(4)]+[(.12+i*.02,.5)for i in range(9)]:
            frames.append({'playback_seconds':time,'source_pts_seconds':100+time,
                           'notes':[{'lane':1,'x':.4,'y':y,'quality':.8}], 'combo':None})
        data.update(frame_count=len(frames),notes=[])
        original=deepcopy((data,frames));e=effect()
        prepared={**data,'chart_policy':{'status':'applied','alignment':{'uncertainty_seconds':0},
                                       'gimmick_candidates':[e]}}
        with tempfile.TemporaryDirectory()as tmp:
            directory=Path(tmp);trace=directory/'frames.jsonl'
            trace.write_text(''.join(json.dumps(f)+'\n'for f in frames));before=trace.read_bytes()
            with patch.object(roles,'reference',return_value={'format':roles.FORMAT,'candidates':[e]}),\
                    patch('piu_timeline.charts.policy.attach_regions',return_value=prepared):
                result=roles.apply(data,directory)
            self.assertEqual(trace.read_bytes(),before)
            artifact=json.loads((directory/'object-interpretation.json').read_text())
        self.assertEqual((data,frames),original)
        self.assertEqual(len(artifact['observations']),9)
        self.assertEqual([r['source_pts_seconds']for r in artifact['observations']],
                         [f['source_pts_seconds']for f in frames[4:]])
        retained=[point for note in result['notes']for point in note['points']]
        self.assertEqual(retained,[[f['playback_seconds'],f['notes'][0]['y']*200]for f in frames[:4]])
        self.assertEqual(result['matches'],[])

    def test_boundary_candidates_stay_detected_and_body_roles_preserve_source_components(self):
        data=geometry();data['object_interpretation']={'effects':[effect()]}
        notes=[{'lane':1,'x':.4,'y':.5},{'lane':0,'x':.2,'y':.5}]
        frames=[{'playback_seconds':.105,'notes':notes}, {'playback_seconds':.2,'notes':notes}]
        original=deepcopy(frames);view=roles.filter_frames(data,frames)
        self.assertEqual(view[0]['notes'],notes)
        self.assertEqual(view[1]['notes'],notes[1:])
        self.assertEqual(frames,original)
        bodies=[{'foreground_bounds':[100,100,160,200],'source_components':[3]},
                {'foreground_bounds':[0,100,70,200],'source_components':[4]}]
        # Body caches have their own 325-pixel coordinate system.
        bodyframes=[{'playback_seconds':.2,'bodies':bodies,'source_pts_seconds':100.2}]
        self.assertEqual(roles.filter_frames(data,bodyframes,bodies=True)[0]['bodies'],bodies[1:])
        self.assertEqual(bodyframes[0]['bodies'],bodies)

    def test_metadata_edit_rejected_candidate_and_missing_projection_are_explicit(self):
        e=effect();data=geometry()
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);metadata=root/'metadata.json';metadata.write_text(json.dumps({'gimmick_candidates':[e]}))
            (root/'chart-registration.json').write_text(json.dumps({'chart':str(root/'chart.ucs')}))
            ref=roles.reference(data,root);data['object_interpretation']={'contract':ref}
            self.assertFalse(roles.current(data,root))
            data['object_interpretation'].update(status='applied',effects=[deepcopy(e)])
            (root/'object-interpretation.json').write_text(json.dumps(data['object_interpretation']))
            self.assertTrue(roles.current(data,root))
            e['game_image_bounds'][0]=.28;metadata.write_text(json.dumps({'gimmick_candidates':[e]}))
            self.assertFalse(roles.current(data,root))
            e['review_status']='rejected';metadata.write_text(json.dumps({'gimmick_candidates':[e]}))
            self.assertFalse(roles.current(data,root))
            restored=roles.apply(data,root)
            self.assertEqual(restored['object_interpretation']['effects'],[])
            self.assertTrue(roles.current(restored,root))
        data.pop('object_interpretation')
        e=effect();data['chart_policy']={'gimmick_candidates':[e]}
        self.assertEqual(roles.verify(data)['object_interpretation']['warnings'][0]['reason'],
                         'decorative_art_interpretation_missing')
        data['object_interpretation']={'effects':[deepcopy(e)]}
        self.assertEqual(roles.verify(data)['object_interpretation']['warnings'],[])
        e['playback_end_seconds']+=1
        self.assertTrue(roles.verify(data)['object_interpretation']['warnings'])

    def test_alignment_failure_is_explicit_and_ambiguous_candidates_keep_native_identity(self):
        data=geometry();data.update(frame_count=1,notes=[]);e=effect()
        frame={'playback_seconds':.105,'source_pts_seconds':100.105,'combo':None,
               'notes':[{'lane':1,'x':.4,'y':y}for y in (.45,.55)]}
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);trace=root/'frames.jsonl';trace.write_text(json.dumps(frame)+'\n');before=trace.read_bytes()
            with patch.object(roles,'reference',return_value={'format':roles.FORMAT,'candidates':[e]}):
                with patch('piu_timeline.charts.policy.attach_regions',return_value={
                        **data,'chart_policy':{'status':'invalid','reason':'ambiguous audio alignment'}}):
                    with self.assertRaisesRegex(ValueError,'ambiguous audio alignment'):roles.apply(data,root)
                prepared={**data,'chart_policy':{'status':'applied','alignment':{'uncertainty_seconds':0},
                                                'gimmick_candidates':[e]}}
                with patch('piu_timeline.charts.policy.attach_regions',return_value=prepared):result=roles.apply(data,root)
            self.assertEqual(trace.read_bytes(),before)
        self.assertEqual(result['object_interpretation']['observations'],[])
        self.assertEqual([w['native_detection']for w in result['object_interpretation']['warnings']],[0,1])
        self.assertEqual([w['observation']for w in result['object_interpretation']['warnings']],frame['notes'])

    def test_invalid_decorative_semantics_or_unbounded_region_cannot_hide_objects(self):
        self.assertEqual(validate_candidates({'gimmick_candidates':[effect()]}),[effect()])
        for key,value in [('playable_notes_present',True),('playable_notes_present',None),
                          ('note_semantics','unknown'),('game_image_bounds',[.9,.2,.5,.2]),
                          ('boundary_uncertainty_seconds',.2)]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                validate_candidates({'gimmick_candidates':[{**effect(),key:value}]})
