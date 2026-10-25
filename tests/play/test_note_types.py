"""Shape, identity and scoped exceptions must retain single-frame conflicts."""
from copy import deepcopy
import unittest
import tempfile
from pathlib import Path

import cv2
import numpy as np

from piu_timeline.play.note_types import shape, project_types, body_type_observations, observe_types
from piu_timeline.play.exclusions import recognition_diagnostics
from piu_timeline.charts.policy import validate_regions


def cap(kind='tap'):
    color=np.zeros((70,23),dtype=bool);white=np.zeros_like(color)
    cv2.rectangle(white.view('uint8'),(2,25),(20,45),1,2)
    color[28:43,5:18]=True
    if kind=='hold':
        color[40:69,8:15]=True
    if kind=='flash':
        white[20:25]=True
    if kind=='clipped':
        white[:]=False
    return color,white,np.ones_like(color)


def evidence(kind,time,note=0):
    return {'kind':kind,'playback_seconds':time,'source_pts_seconds':time+40,
            'source_note':note,'reason':'synthetic_visible_shape'}


class NoteTypeTest(unittest.TestCase):
    def test_complete_cap_stripe_flash_and_incomplete_outline_are_distinct(self):
        for kind,expected in [('tap','tap'),('hold','hold'),('flash','unknown'),('clipped','unknown')]:
            with self.subTest(kind=kind):
                self.assertEqual(shape(*cap(kind),35,20)[0],expected)
        color,white,visible=cap()
        visible[:25]=False
        self.assertEqual(shape(color,white,visible,35,20)[0],'unknown')

    def test_single_body_frame_is_retained_but_processing_remnant_or_hud_is_not(self):
        data={'game_roi':[0,0,325,200],'analysis_height':200,
              'layout':{'receptor_y':.2,'lanes':[{'x':.2+.1*i} for i in range(5)]},
              'notes':[{'lane':2,'status':'estimated','points':[[1,100]]}]}
        frame={'playback_seconds':1,'source_pts_seconds':41,'bodies':[
            {'lane':2,'top':100,'bottom':175,'long':True,'stripe_support':.9,
             'top_visible':True,'tail_visible':True,'edge_convention':'connected_color'}]}
        proof=body_type_observations(data,[frame])[0][0]
        self.assertEqual(proof['kind'],'hold')
        self.assertEqual(proof['source_pts_seconds'],41)
        self.assertEqual(proof['body_bounds'],[100,175])
        data['layout']['combo_roi']=[.3,.5,.2,.1]
        self.assertEqual(body_type_observations(data,[frame]),{})
        data['layout'].pop('combo_roi')
        data['notes'][0]['points']=[[1,60]]
        frame['bodies'][0].update(top=60,bottom=135)
        self.assertEqual(body_type_observations(data,[frame]),{})

    def test_one_native_body_frame_conflicts_with_other_isolated_cap_frames(self):
        from tests.play.test_visual_channels import pixel_play
        from piu_timeline.play.processing import ReceptorPixels
        from piu_timeline.play.holds.features import detect_bodies, feature_contract
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);data,_=pixel_play(directory)
            pixels=ReceptorPixels(data['layout'],325,200);frames=[]
            for i in range(84):
                time=i/60;image=np.full((200,325,3),70,dtype='uint8')
                y=round(60+200*(1-time));x=130
                if time<1 and 15<=y<185:
                    cv2.rectangle(image,(x-14,y-14),(x+14,y+14),(255,255,255),-1)
                    cv2.rectangle(image,(x-11,y-11),(x+11,y+11),(0,130,255),-1)
                    if i==39:
                        cv2.rectangle(image,(x-5,y+10),(x+5,y+60),(0,130,255),-1)
                bodies,_=detect_bodies(image,data['layout'])
                frames.append({'playback_seconds':time,'source_pts_seconds':42+time,'bodies':bodies})
                pixels.observe(image,42+time,time)
            path=directory/'processing-features.npz';pixels.save(path,feature_contract(data))
            record=observe_types(data,path,frames)['notes'][0]
            self.assertEqual(record['status'],'conflict')
            hold_frames={o['source_pts_seconds'] for o in record['observations'] if o['kind']=='hold'}
            self.assertEqual(hold_frames,{42+39/60})
            self.assertTrue(any(o['kind']=='tap' for o in record['observations']))

    def test_one_opposing_frame_survives_many_agreeing_frames_and_does_not_change_native_notes(self):
        notes=[{'status':'estimated','lane':0,'target_seconds':2,'points':[[1,80],[1.5,60]]}]
        observations=[evidence('hold',1+i/60) for i in range(20)]+[evidence('tap',1.5)]
        data={'notes':deepcopy(notes),'visual_channels':{'note_types':{'notes':[{'note':0,'observations':observations}]}}}
        before=deepcopy(data)
        diagnostics=project_types(data,notes,[])
        self.assertEqual(data,before)
        self.assertEqual(notes[0]['type_status'],'conflict')
        self.assertEqual(diagnostics[0]['reason'],'note_type_conflict')
        self.assertEqual(len(diagnostics[0]['type_evidence']),21)
        self.assertEqual(diagnostics[0]['type_evidence'][-1]['source_pts_seconds'],41.5)

    def test_unknown_samples_do_not_refute_hold_and_unproved_heads_stay_unknown(self):
        notes=[{'status':'estimated','lane':0,'target_seconds':2,'points':[]} for _ in range(3)]
        records=[{'note':i,'observations':obs} for i,obs in enumerate(
            ([evidence('hold',1),evidence('unknown',1.1)], [evidence('tap',1)], []))]
        data={'visual_channels':{'note_types':{'notes':records}}}
        diagnostics=project_types(data,notes,[])
        self.assertEqual([n['type_status'] for n in notes],['hold','tap','unknown'])
        self.assertEqual({d['note'] for d in diagnostics},{0,2})

    def test_hold_component_identity_combines_proofs_but_not_same_lane_neighbors(self):
        notes=[{'status':'estimated','lane':0,'target_seconds':2,'points':[],'note_type':'hold'},
               {'status':'excluded','lane':0,'target_seconds':2.2,'points':[]},
               {'status':'estimated','lane':0,'target_seconds':2.3,'points':[]}]
        data={'visual_channels':{'timeline':{'frames':[[1,41],[1.4,41.4]]},'note_types':{'notes':[
            {'note':1,'observations':[evidence('tap',1.3,1)]},
            {'note':2,'observations':[evidence('tap',1.2,2)]}]}}}
        holds=[{'id':0,'display_note':0,'head_note':0,'covered_notes':[0,1],'source_pts_range':[41,41.4]}]
        diagnostics=project_types(data,notes,holds)
        self.assertEqual([notes[i]['type_status'] for i in (0,2)],['conflict','tap'])
        self.assertEqual(len(diagnostics),1)
        proof=diagnostics[0]['type_evidence']
        self.assertEqual({p['kind'] for p in proof},{'tap','hold'})
        self.assertEqual(proof[-1]['source_pts_range'],[41,41.4])
        self.assertEqual(diagnostics[0]['visible_start_seconds'],1)
        self.assertEqual(diagnostics[0]['visible_end_seconds'],1.4)

    def test_isolated_tail_after_hold_contact_is_unknown_instead_of_conflicting_tap(self):
        notes=[{'status':'estimated','lane':0,'target_seconds':1,'points':[],'note_type':'hold'}]
        raw=evidence('tap',1.1)
        data={'visual_channels':{'note_types':{'notes':[{'note':0,'observations':[raw]}]}}}
        hold={'id':0,'display_note':0,'head_note':0,'covered_notes':[0],'start_range':[.99,1.01]}
        self.assertEqual(project_types(data,notes,[hold]),[])
        self.assertEqual(notes[0]['type_status'],'hold')
        self.assertEqual(notes[0]['type_evidence'][0]['kind'],'unknown')
        self.assertEqual(notes[0]['type_evidence'][0]['observed_kind'],'tap')
        self.assertEqual(raw['kind'],'tap')

    def test_only_explicit_type_exception_covering_all_evidence_suppresses_the_warning(self):
        observation={'note':0,'lane':0,'reason':'note_type_conflict',
                     'visible_start_seconds':1,'visible_end_seconds':1.5,
                     'type_evidence':[evidence('hold',1),evidence('tap',1.5)]}
        region={'id':'shape-change','start_seconds':0,'end_seconds':2,'processing':'exclude_timing',
                'check_exceptions':['timing_evidence'],'reason':'Human reviewed transformation',
                'playback_start_seconds':0,'playback_end_seconds':2}
        data={'notes':[],'note_type_diagnostics':[observation],'chart_policy':{'regions':[region]}}
        for checks,end,expected in [(['timing_evidence'],2,1),(['stage_grade_totals'],2,1),(['note_type_unresolved'],2,1),
                                    (['note_type_conflict'],1.2,1),(['note_type_conflict'],1.5,1),(['note_type_conflict'],2,0)]:
            region.update(check_exceptions=checks,playback_end_seconds=end)
            result=recognition_diagnostics(data,{'notes':{}})
            self.assertEqual(len(result['warnings']),expected)
            if not expected:
                self.assertEqual(result['chart_exceptions'][0]['type_evidence'],observation['type_evidence'])
        plain={key:value for key,value in region.items() if not key.startswith('playback_')}
        self.assertEqual(validate_regions({'regions':[plain]})[0]['check_exceptions'],['note_type_conflict'])
