"""Image endpoints need one uniquely covered body, never a second tap."""
from copy import deepcopy
import unittest

from piu_timeline.play.skins.holds import reconstruct_images as reconstruct
from piu_timeline.play.skins.observations import observe, tail_roles


REFERENCES={'hold_start':[[0,35]],'hold_end':[[0,35]],'hold_body':[[0,30]]}
CAP_REFERENCES={'hold_start':[[0,20]],'hold_end':[[15,35]],'hold_body':[]}


def reconstruct_images(data,receptors,native,warnings,*,references=REFERENCES):
    return reconstruct(data,receptors,native,warnings,references=references,cap_references=CAP_REFERENCES)['holds']


def scenario():
    layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1,'color':'blue'}for i in range(5)]}
    data={'analysis_width':200,'analysis_height':300,'start_seconds':0,'end_seconds':2,
          'game_roi':[0,0,200,300],'layout':layout,'skin_detector':{'contract':{'schema':1}},'notes':[]}
    native,receptors=[],[]
    for i in range(10):
        t=i*.02;y=100-100*t
        observations=[]
        for role,anchor,bounds in [('hold_start',y,[10,y-10,30,y+25]),
                                   ('hold_end',y+60,[10,y+35,30,y+70]),
                                   ('hold_body',y+35,[16,y+20,24,y+50])]:
            observations.append({'lane':0,'x':.1,'y':anchor/300,'role':role,'template':role,
                                 'skin':'synthetic','region_errors':{'cap':0.,'connection':0.},'bounds_pixels':bounds})
        native.append({'playback_seconds':t,'source_pts_seconds':t+30,'skin_observations':observations})
        receptors.append({'playback_seconds':t,'source_pts_seconds':t+30,'receptor_lit':[None]*5})
    for offset,target in [(0,.85),(60,1.45)]:
        data['notes'].append({'lane':0,'status':'estimated','points':[[i*.02,100-2*i+offset]for i in range(10)],
                              'target_seconds':target,'prediction_uncertainty_seconds':.01,
                              'velocity_pixels_per_second':-100})
    return data,native,receptors


class ImageHoldTest(unittest.TestCase):
    def test_failed_beat_row_does_not_erase_a_connected_image_hold_with_native_timing(self):
        data,native,receptors=scenario()
        n=data['notes'][0]
        n.update(status='excluded',reason='beat_timing_reconstruction_failed',target_seconds=None,
                 video_target_range=[.83,.87],timing_reconstruction={'status':'restored'},
                 beat_reconstruction={'status':'failed','reason':'ambiguous_beat_rows'})
        before=deepcopy(data)
        holds=reconstruct_images(data,receptors,native,[])
        self.assertEqual(len(holds),1)
        self.assertEqual(holds[0]['start_range'],[.83,.87])
        self.assertEqual(holds[0]['geometry_native_endpoint_notes'],[0])
        self.assertEqual(holds[0]['chart_timing_status'],'unresolved')
        self.assertEqual(data,before)
        n['timing_reconstruction']['status']='failed'
        warnings=[]
        self.assertEqual(reconstruct_images(data,receptors,native,warnings),[])
        self.assertTrue(warnings)


    def test_independent_registered_endpoint_errors_recover_connected_rounded_caps(self):
        data,native,receptors=scenario()
        errors=[(-.75,.75),(.5,-.5),(-.25,.25),(.75,-.75)]
        records=[{'note':i,'coordinate_method':'native_image_anchors','observations':[]} for i in (0,1)]
        for fi,frame in enumerate(native):
            for i,offset in enumerate(errors[fi%len(errors)]):
                time,y=data['notes'][i]['points'][fi]
                data['notes'][i]['points'][fi][1]=y+offset
                image=frame['skin_observations'][i]
                image['y']=(y+offset)/data['analysis_height']
                image['bounds_pixels'][1]+=offset;image['bounds_pixels'][3]+=offset
                records[i]['observations'].append({'time':time,'source_pts_seconds':frame['source_pts_seconds'],
                    'native_y_pixels':y+offset,'native_cap_coordinate_uncertainty_pixels':1.,
                    'native_cap_reference_template':image['template']})
        # Image connection alone cannot resolve inconsistent endpoint coordinates.
        self.assertEqual(reconstruct_images(data,receptors,native,[]),[])
        data['head_registration']={'notes':records}
        warnings=[];holds=reconstruct_images(data,receptors,native,warnings)
        self.assertEqual(len(holds),1)
        proof=holds[0]['endpoint_extent_evidence']
        self.assertLessEqual(proof['length_range_pixels'][0],60)
        self.assertGreaterEqual(proof['length_range_pixels'][1],60)
        self.assertEqual(proof['source_pts_seconds'],[frame['source_pts_seconds'] for frame in native])
        records[0]['observations'][0].pop('native_cap_coordinate_uncertainty_pixels')
        unregistered=[];self.assertEqual(len(reconstruct_images(data,receptors,native,unregistered)),1)
        self.assertIn('known_hold_endpoint_extent_unregistered_frames',[w.get('failure_detail') for w in unregistered])
        # A true length change remains a contradiction with the same measured errors.
        data['notes'][1]['points'][-1][1]+=8
        records[1]['observations'][-1]['native_y_pixels']+=8
        self.assertEqual(reconstruct_images(data,receptors,native,[]),[])


    def test_start_body_and_end_images_form_one_held_interval_without_color_components(self):
        data,native,receptors=scenario();original=deepcopy((data,native,receptors));warnings=[]
        holds=reconstruct_images(data,receptors,native,warnings)
        self.assertEqual(len(holds),1)
        hold=holds[0]
        self.assertEqual((hold['head_note'],hold['tail_note']),(0,1))
        self.assertEqual(hold['covered_notes'],[0,1])
        self.assertEqual(len(hold['image_connection_evidence']),10)
        self.assertEqual(hold['source_pts_range'],[30,30.18])
        self.assertEqual(warnings,[])
        self.assertEqual((data,native,receptors),original)

    def test_dim_receptor_pulse_needs_independent_image_geometry_and_positive_hud_evidence(self):
        data,native,_=scenario()
        receptors=[{'playback_seconds':i*.02,'source_pts_seconds':30+i*.02,
                    'receptor_lit':[False]*5,'receptor_white_fraction':[.1]*5,
                    'common_receptor_flash':False}for i in range(100)]
        receptors[50]['receptor_white_fraction'][0]=.5
        data['judgment_events']=[{'label':'PERFECT','lower_seconds':.99,'upper_seconds':1.01}]
        holds=reconstruct_images(data,receptors,native,[])
        self.assertEqual(len(holds),1)
        support=holds[0]['input']
        self.assertEqual(support['recognition_envelope'],[1.,1.])
        self.assertEqual(support['segments'][0]['first_source_pts_seconds'],31.)
        self.assertEqual(support['segments'][0]['corroborating_updates'][0]['kind'],'judgment_events')
        self.assertIsNone(support['press_range'])
        for case in ('miss','common_flash','wrong_lane','outside_hold'):
            d,r=deepcopy(data),deepcopy(receptors)
            if case=='miss':d['judgment_events'][0]['label']='MISS'
            elif case=='common_flash':r[50]['common_receptor_flash']=True
            elif case=='wrong_lane':r[50]['receptor_white_fraction']=[.1,.5,.1,.1,.1]
            else:
                r[50]['receptor_white_fraction'][0]=.1;r[25]['receptor_white_fraction'][0]=.5
                d['judgment_events'][0].update(lower_seconds=.49,upper_seconds=.51)
                # Legacy color contact cannot establish an image hold here.
                r[25]['bodies']=[{'lane':0,'top':0,'bottom':300}]
            with self.subTest(case=case):
                self.assertEqual(reconstruct_images(d,r,native,[])[0]['input']['segments'],[])

    def test_unknown_context_keeps_positive_endpoints_without_erasing_real_role_conflicts(self):
        data,native,receptors=scenario()
        for index in (2,6):
            native[index]['skin_observations'][0]['role']='unknown'
            native[index]['skin_observations'][1]['role']='unknown'
        warnings=[]
        holds=reconstruct_images(data,receptors,native,warnings)
        self.assertEqual(len(holds),1)
        evidence=holds[0]['image_connection_evidence']
        self.assertEqual(sum('head_y'in p and 'tail_y'in p for p in evidence),8)
        self.assertEqual(warnings[0]['failure_detail'],
                         'known_hold_image_connection_not_observed_in_clear_frames')
        self.assertEqual(warnings[0]['observed_points'],2)
        # A complete, contradictory image still prevents endpoint ownership.
        native[4]['skin_observations'][0]['role']='hold_end'
        self.assertEqual(reconstruct_images(data,receptors,native,[]),[])

    def test_conflicting_role_or_failed_clock_prevents_complete_hold(self):
        for case in ('tap_conflict','failed_clock'):
            data,native,receptors=scenario()
            if case=='tap_conflict':native[3]['skin_observations'][1]['role']='tap'
            else:data['notes'][0]['status']='excluded'
            warnings=[]
            self.assertEqual(reconstruct_images(data,receptors,native,warnings),[])
            self.assertTrue(warnings)

    def test_missing_body_match_is_a_warning_and_never_supplies_connection_proof(self):
        data,native,receptors=scenario();native[3]['skin_observations'].pop()
        warnings=[];holds=reconstruct_images(data,receptors,native,warnings)
        self.assertEqual(len(holds),1)
        from piu_timeline.play.skins.holds import covered
        at_missing=[p['covered_bounds_pixels']for p in holds[0]['image_connection_evidence']if p['time']==.06]
        self.assertFalse(covered(94,154,at_missing))
        self.assertEqual(warnings[0]['observed_points'],1)
        self.assertTrue(all(p['time']==.06 and p['source_pts']==30.06 for p in warnings[0]['image_evidence']))
        for frame in native:frame['skin_observations']=frame['skin_observations'][:2]
        self.assertEqual(reconstruct_images(data,receptors,native,[]),[])

    def test_canvas_padding_and_internal_uncompared_rows_cannot_bridge_a_hold(self):
        for role,rows in [('hold_body',[[0,8],[22,30]]),('hold_start',[[0,20]])]:
            data,native,receptors=scenario();references={**REFERENCES,role:rows}
            warnings=[]
            self.assertEqual(reconstruct_images(data,receptors,native,warnings,references=references),[])
            self.assertTrue(warnings)

    def test_deduplicated_positive_body_tiles_keep_their_own_compared_image_coverage(self):
        data,native,receptors=scenario();references={**REFERENCES,'hold_body':[[0,8]]}
        for frame in native:
            body=frame['skin_observations'][-1]
            alternative=deepcopy(body);alternative.update(classification_status='full_pattern')
            alternative['bounds_pixels']=[v+7 if i%2 else v for i,v in enumerate(body['bounds_pixels'])]
            body['alternatives']=[alternative]
        self.assertEqual(len(reconstruct_images(data,receptors,native,[],references=references)),1)
        # Unknown or contrary-role alternatives do not supply missing body pixels.
        for case in ('cap_only','tap'):
            changed=deepcopy(native)
            for frame in changed:
                alt=frame['skin_observations'][-1]['alternatives'][0]
                if case=='cap_only':alt['classification_status']='cap_only'
                else:alt['role']='tap'
            self.assertEqual(reconstruct_images(data,receptors,changed,[],references=references),[])

    def test_positive_endpoint_alternatives_keep_their_connection_pixels(self):
        data,native,receptors=scenario()
        references={**REFERENCES,'hold_body':[[0,8]],'extended_start':[[0,48]]}
        for frame in native:
            cap=frame['skin_observations'][0];alternative=deepcopy(cap)
            alternative.update(template='extended_start',classification_status='full_pattern')
            alternative['bounds_pixels'][3]+=13
            cap['alternatives']=[alternative]
        warnings=[]
        self.assertEqual(len(reconstruct_images(data,receptors,native,warnings,references=references)),1)
        self.assertEqual(warnings,[])
        # An unconfirmed connection cannot extend the representative cap.
        for frame in native:
            alt=frame['skin_observations'][0]['alternatives'][0]
            alt.update(role='unknown',classification_status='cap_only')
        self.assertEqual(reconstruct_images(data,receptors,native,[],references=references),[])

    def test_known_endpoint_caps_need_positive_body_images_and_a_complete_role_elsewhere(self):
        data,native,receptors=scenario()
        for frame in native[1:]:
            frame['skin_observations'][1].update(role='unknown',classification_status='cap_only')
        warnings=[];holds=reconstruct_images(data,receptors,native,warnings)
        self.assertEqual(len(holds),1)
        self.assertEqual(len(holds[0]['image_connection_evidence']),10)
        self.assertEqual(warnings,[])
        no_role=deepcopy(native)
        no_role[0]['skin_observations'][1].update(role='unknown',classification_status='cap_only')
        self.assertEqual(reconstruct_images(data,receptors,no_role,[]),[])
        for frame in native[1:]:frame['skin_observations'].pop()
        self.assertEqual(reconstruct_images(data,receptors,native,[]),[])

    def test_one_hold_does_not_claim_unrelated_body_images_in_the_same_lane_and_frame(self):
        data,native,receptors=scenario()
        for frame in native:
            body=deepcopy(frame['skin_observations'][-1]);body['y']+=.4
            body['bounds_pixels']=[body['bounds_pixels'][0],body['bounds_pixels'][1]+120,
                                   body['bounds_pixels'][2],body['bounds_pixels'][3]+120]
            body['alternatives']=[{**deepcopy(body),'classification_status':'full_pattern','marker':'native_only_detail'}]
            frame['skin_observations'].append(body)
        warnings=[];holds=reconstruct_images(data,receptors,native,warnings)
        self.assertEqual(len(holds),1)
        self.assertEqual(len(warnings),1)
        self.assertEqual(warnings[0]['failure_detail'],'skin_body_images_without_complete_endpoint_ownership')
        self.assertEqual(warnings[0]['observed_points'],10)
        self.assertTrue(all(p['y']>.65 for p in warnings[0]['image_evidence']))
        self.assertTrue(all(p['trace']=='frames.jsonl'and 'alternatives'not in p
                            for p in warnings[0]['image_evidence']))
        self.assertEqual(native[0]['skin_observations'][-1]['alternatives'][0]['marker'],'native_only_detail')

    def test_interior_tap_refutes_a_common_frame_proposal_as_well_as_temporal_connections(self):
        data,native,receptors=scenario();image=deepcopy(native[3]['skin_observations'][0])
        image.update(role='tap',template='tap',y=124/300,bounds_pixels=[10,114,30,134])
        native[3]['skin_observations'].append(image)
        data['notes'].append({'lane':0,'points':[[.06,124]],'status':'excluded','target_seconds':None})
        warnings=[]
        self.assertEqual(reconstruct_images(data,receptors,native,warnings),[])
        self.assertTrue(any(w['failure_detail']=='skin_hold_interior_note_conflict'for w in warnings))

    def test_a_tail_image_needs_no_tap_or_input_at_its_cap_and_conflicts_stay_explicit(self):
        data,native,_=scenario();data['visual_channels']={'note_types':observe(data,native)}
        roles=tail_roles(data)
        self.assertEqual([r['tail_note']for r in roles],[1])
        self.assertTrue(roles[0]['image_evidence'])
        native[1]['skin_observations'][1]['role']='unknown'
        data['visual_channels']['note_types']=observe(data,native)
        partial=tail_roles(data)
        self.assertEqual([r['tail_note']for r in partial],[1])
        self.assertEqual(len(partial[0]['image_evidence']),9)
        native[0]['skin_observations'][1]['role']='tap'
        data['visual_channels']['note_types']=observe(data,native)
        self.assertEqual(tail_roles(data),[])
        self.assertEqual(data['visual_channels']['note_types']['notes'][1]['status'],'conflict')
