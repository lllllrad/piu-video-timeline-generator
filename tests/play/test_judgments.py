import unittest
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import cv2
import numpy as np
from piu_timeline.play.judgments import JudgmentReader, JudgmentTracker, feature_map, merge_judgments, augment_judgments, collect_features, LABELS, VERSION, cache_contracts, template_document, TEMPLATE_FORMAT


def observation(label='PERFECT',width=100,height=20,blank=False):
    return {'label':label,'confidence':.99 if label else 0,'box':[5,5,width,height] if label else None,'blank':blank}


def reappearing_word_capture(fps=60,clear_seconds=.15,hidden_frames=2):
    """Native reads of a word, a clear interval, occlusion and the same word."""
    clear_frames=round(clear_seconds*fps)
    frames=[]
    for i in range(2+clear_frames+hidden_frames+3):
        clear=2<=i<2+clear_frames;hidden=2+clear_frames<=i<2+clear_frames+hidden_frames
        frames.append({'playback_seconds':i/fps,'source_pts_seconds':80+i/fps,
                       **observation(None if clear or hidden else 'PERFECT',blank=clear)})
    return frames,[(1+clear_frames)/fps,(2+clear_frames+hidden_frames)/fps]


class JudgmentTest(unittest.TestCase):
    def combo_data(self,times,brackets):
        return {'notes':[{'lane':0,'status':'estimated','target_seconds':t} for t in times],
                'combo_events':[{'before':i+4,'after':i+5,'delta':1,'status':'matched',
                                 'lower_seconds':lo,'upper_seconds':hi} for i,(lo,hi) in enumerate(brackets)],
                'matches':[{'note':i,'combo_event':i,'target_seconds':t,
                            'combo_lower_seconds':lo,'combo_upper_seconds':hi,
                            'raw_offset_lower_ms':1000*(lo-t),'raw_offset_upper_ms':1000*(hi-t)}
                           for i,(t,(lo,hi)) in enumerate(zip(times,brackets))],
                'coverage':{}}

    def test_synchronized_refresh_uses_counter_instead_of_nearest_fitted_note(self):
        # GOOD is closer to the predicted crossing, but the counter updates
        # with PERFECT. Independent nearest-time association used to attach GOOD.
        data=self.combo_data([1.04],[(1.067,1.083)])
        events=[{'label':'GOOD','lower_seconds':1.033,'upper_seconds':1.05},
                {'label':'PERFECT','lower_seconds':1.067,'upper_seconds':1.083}]
        result=merge_judgments(data,events)
        match=result['matches'][0]
        self.assertEqual(match['judgment_label'],'PERFECT')
        self.assertEqual(match['judgment_label_source'],'synchronized_refresh')
        self.assertEqual(match['observation_upper_seconds'],1.083)
        self.assertEqual(len(result['matches']),1)

    def test_each_observed_word_can_label_its_own_row_inside_an_aggregate_counter(self):
        data=self.combo_data([1.,1.08],[(.99,1.09),(.99,1.09)])
        data['combo_events']=[{'before':10,'after':12,'delta':2,'status':'matched',
                               'lower_seconds':.99,'upper_seconds':1.09}]
        for match in data['matches']:match['combo_event']=0
        words=[{'label':'GREAT','lower_seconds':.99,'upper_seconds':1.01},
               {'label':'PERFECT','lower_seconds':1.07,'upper_seconds':1.09}]
        result=merge_judgments(data,words)
        self.assertEqual([m['judgment_label'] for m in result['matches']],['GREAT','PERFECT'])
        self.assertEqual([m['judgment_event'] for m in result['matches']],[0,1])
        self.assertTrue(all(m['observation_lower_seconds']==.99 and m['observation_upper_seconds']==1.09
                            for m in result['matches']))

    def test_one_word_is_not_spread_over_aggregate_rows_or_given_to_foreign_rows(self):
        data=self.combo_data([1.,1.08],[(.99,1.09),(.99,1.09)])
        data['combo_events']=[{'before':10,'after':12,'delta':2,'status':'matched',
                               'lower_seconds':.99,'upper_seconds':1.09}]
        for match in data['matches']:match['combo_event']=0
        result=merge_judgments(data,[{'label':'PERFECT','lower_seconds':1.07,'upper_seconds':1.09}])
        self.assertNotIn('judgment_label',result['matches'][0])
        self.assertEqual(result['matches'][1]['judgment_label'],'PERFECT')
        data['notes'].append({'lane':2,'status':'estimated','target_seconds':1.04})
        foreign=merge_judgments(data,[{'label':'GREAT','lower_seconds':1.035,'upper_seconds':1.045}])
        self.assertEqual(len(foreign['matches']),2)
        self.assertTrue(all(m['note']!=2 for m in foreign['matches']))

    def test_counter_anchor_removes_a_competing_neighbor_from_alignment(self):
        data=self.combo_data([1.00],[(.99,1.01)])
        data['notes'].append({'lane':0,'status':'estimated','target_seconds':1.045})
        events=[{'label':'PERFECT','lower_seconds':.99,'upper_seconds':1.01},
                {'label':'GREAT','lower_seconds':1.025,'upper_seconds':1.035}]
        result=merge_judgments(data,events)
        self.assertEqual([(m['note'],m['judgment_label']) for m in result['matches']],[(0,'PERFECT'),(1,'GREAT')])

    def test_counter_frames_supply_label_without_inventing_a_word_refresh(self):
        data=self.combo_data([1.],[(.99,1.01)])
        frames=[{'source_pts_seconds':t+5,'playback_seconds':t,**observation('PERFECT')} for t in (1.01,1.027,1.044)]
        result=merge_judgments(data,[],frames)
        match=result['matches'][0]
        self.assertEqual(match['judgment_label'],'PERFECT')
        self.assertIsNone(match['judgment_event'])
        self.assertEqual(result['judgment_events'],[])
        self.assertEqual(match['judgment_label_source'],'post_combo_frames')
        self.assertEqual([f['source_pts_seconds'] for f in match['judgment_observations']],[f['source_pts_seconds'] for f in frames])
        self.assertEqual(match['observation_upper_seconds'],1.01)
        self.assertEqual(result['coverage']['combo_frame_labeled_note_heads'],1)
        expected=deepcopy(result['matches'])
        again=merge_judgments(result,[],frames)
        self.assertEqual(again['matches'],expected)

    def test_counter_label_proof_survives_until_a_deferred_row_is_recovered(self):
        from piu_timeline.play.holds.analysis import presentation
        data=self.combo_data([1.],[(.99,1.01)])
        deferred=deepcopy(data['matches'][0]);data['matches']=[]
        frames=[{'source_pts_seconds':t+5,'playback_seconds':t,**observation('GREAT')}
                for t in (1.01,1.027,1.044)]
        result=merge_judgments(data,[],frames)
        self.assertFalse(result['matches'])
        result.update(deferred_matches=[deferred],hold_analysis={'holds':[], 'receptor_runs':[
            {'lane':0,'lit':True,'frames':3,'previous_seconds':.98,
             'start_seconds':1.01,'end_seconds':1.05}]})
        before=deepcopy(result)
        view=presentation(result)
        self.assertEqual(result,before)
        self.assertEqual(len(view['matches']),1)
        match=view['matches'][0]
        self.assertEqual(match['judgment_label'],'GREAT')
        self.assertEqual(match['evidence_source'],'combo+lane_onset+judgment')
        self.assertEqual(match['judgment_label_source'],'post_combo_frames')
        self.assertEqual(match['judgment_observations'],[{key:frame[key] for key in
                         ('source_pts_seconds','playback_seconds','label','confidence')} for frame in frames])
        self.assertIsNone(match['judgment_event'])
        self.assertEqual(view['judgment_events'],[])
        self.assertEqual(match['observation_upper_seconds'],1.01)
        # No saved proof may survive a replay with no word observations.
        replay=merge_judgments(result,[],[])
        self.assertEqual(replay['counter_judgment_labels'],{})

    def test_equally_close_refreshes_do_not_force_a_counter_anchor(self):
        data=self.combo_data([1.02],[(1.,1.02)])
        events=[{'label':'GOOD','lower_seconds':.99,'upper_seconds':1.01},
                {'label':'PERFECT','lower_seconds':1.01,'upper_seconds':1.03}]
        result=merge_judgments(data,events)
        self.assertFalse(any('anchor_combo_event' in e for e in result['judgment_events']))
        self.assertNotIn('judgment_label',result['matches'][0])

    def test_exact_100ms_counter_bracket_keeps_grade_and_original_source_times(self):
        for extra,expected in [(0,True),(.00001,False)]:
            data=self.combo_data([1000.1],[(1000,1000.1+extra)])
            frames=[{'playback_seconds':time,'source_pts_seconds':time+42,**observation('GREAT')}
                    for time in (1000.1+extra,1000.117+extra,1000.134+extra)]
            result=merge_judgments(data,[],frames)
            self.assertEqual(bool(result['matches'][0].get('judgment_label')),expected)
            self.assertEqual(result['matches'][0]['observation_upper_seconds'],1000.1+extra)
            if expected:
                self.assertEqual(result['matches'][0]['judgment_observations'][0]['source_pts_seconds'],1042.1)

    def test_counter_frames_reject_conflicting_words_miss_and_aggregate_rows(self):
        for labels,delta in [(('PERFECT','GREAT','GREAT'),1),(('MISS',)*3,1),(('PERFECT',)*3,2)]:
            with self.subTest(labels=labels,delta=delta):
                data=self.combo_data([1.],[(.99,1.01)])
                data['combo_events'][0]['delta']=delta
                frames=[{'source_pts_seconds':t+5,'playback_seconds':t,**observation(label)}
                        for t,label in zip((1.01,1.027,1.044),labels)]
                result=merge_judgments(data,[],frames)
                self.assertNotIn('judgment_label',result['matches'][0])

    def test_counter_frames_stop_before_the_next_input(self):
        data=self.combo_data([1.,1.04],[(.99,1.01),(1.025,1.04)])
        frames=[{'source_pts_seconds':t+5,'playback_seconds':t,**observation(label)}
                for t,label in [(1.01,'PERFECT'),(1.027,'GREAT'),(1.044,'GREAT'),(1.061,'GREAT')]]
        result=merge_judgments(data,[],frames)
        self.assertNotIn('judgment_label',result['matches'][0])
        self.assertEqual(result['matches'][1]['judgment_label'],'GREAT')

    def test_current_word_observations_reuse_without_decoding_or_ocr(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)
            data=self.combo_data([1.],[(.94,1.01)])
            data.update(media={},analysis_width=650,judgment_analysis_version=VERSION,
                        judgment_template_labels=[],judgment_events=[])
            data['judgment_cache']=cache_contracts(data,[])
            frames=[{'source_pts_seconds':t+5,'playback_seconds':t,**observation('PERFECT')}
                    for t in (1.01,1.027,1.044)]
            (output/'judgments.jsonl').write_text(''.join(json.dumps(frame)+'\n' for frame in frames))
            with patch('piu_timeline.play.judgments.collect_features',side_effect=AssertionError('must reuse native observations')), \
                    patch('piu_timeline.play.judgments.ocr_images',side_effect=AssertionError('must not OCR')):
                result=augment_judgments(data,output)
            self.assertEqual(result['judgment_analysis_version'],VERSION)
            self.assertEqual(result['matches'][0]['judgment_label'],'PERFECT')
            self.assertEqual(result['matches'][0]['observation_lower_seconds'],.94)

    def test_two_close_reads_survive_later_occlusion_without_majority_vote(self):
        data=self.combo_data([1.],[(.99,1.01)])
        frames=[{'source_pts_seconds':t+5,'playback_seconds':t,**observation(label)}
                for t,label in [(1.01,'GREAT'),(1.027,'GREAT'),(1.044,None),(1.06,None)]]
        result=merge_judgments(data,[],frames)
        self.assertEqual(result['matches'][0]['judgment_label'],'GREAT')
        self.assertEqual(len(result['matches'][0]['judgment_observations']),2)

    def test_disconnected_reads_do_not_bridge_a_long_occlusion(self):
        data=self.combo_data([1.],[(.99,1.01)])
        frames=[{'source_pts_seconds':t+5,'playback_seconds':t,**observation(label)}
                for t,label in [(1.01,'PERFECT'),(1.027,None),(1.044,None),(1.06,'PERFECT')]]
        result=merge_judgments(data,[],frames)
        self.assertNotIn('judgment_label',result['matches'][0])

    def test_reader_upgrade_uses_cached_pixels_and_fonts_without_ocr_or_decode(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary);directory=output/'evidence/judgments';directory.mkdir(parents=True)
            image=np.zeros((60,260,3),dtype='uint8')
            cv2.putText(image,'PERFECT',(70,40),cv2.FONT_HERSHEY_SIMPLEX,.8,(0,230,255),2)
            feature=feature_map(image);ys,xs=np.nonzero(feature<18)
            hue=int(np.median(feature[ys,xs]));mask=(feature[ys.min():ys.max()+1,xs.min():xs.max()+1]<18).astype('uint8')
            models=[{'label':'PERFECT','hue':hue,'mask':mask.tolist()}]
            times=np.array([1.01,1.027,1.044]);pts=times+5
            np.savez_compressed(directory/'features-v3.npz',features=np.array([feature]*3),pts=pts,times=times)
            (directory/'samples.json').write_text('[]')
            data=self.combo_data([1.],[(.99,1.01)])
            data.update(media={},analysis_width=260,judgment_analysis_version=-999,
                        judgment_template_labels=['PERFECT'],judgment_events=[],layout={'combo_roi':[.4,.5,.2,.1]})
            (directory/'templates.json').write_text(json.dumps({'media':{},'analysis_width':260,'models':models}))
            with patch('piu_timeline.play.judgments.load_bank',return_value=models), \
                    patch('piu_timeline.play.judgments.decode_frames',side_effect=AssertionError('must not decode')), \
                    patch('piu_timeline.play.judgments.learn_models',side_effect=AssertionError('must not OCR')):
                result=augment_judgments(data,output)
            self.assertEqual(result['judgment_analysis_version'],VERSION)
            self.assertEqual(result['judgment_bootstrap_ocr_images'],0)
            self.assertEqual(result['matches'][0]['judgment_label'],'PERFECT')
            readings=[json.loads(line) for line in (output/'judgments.jsonl').read_text().splitlines()]
            self.assertEqual([reading['source_pts_seconds'] for reading in readings],pts.tolist())

    def test_cache_dependencies_are_independent_of_result_version(self):
        data=self.combo_data([1.],[(.99,1.01)])
        data.update(media={'path':'source'},analysis_width=650,layout={'combo_roi':[.4,.5,.2,.1]})
        model={'label':'PERFECT','hue':9,'mask':[[1,0,1],[0,1,0],[1,0,1]]}
        original=cache_contracts(data,[model])
        data['judgment_analysis_version']='any application release'
        self.assertEqual(cache_contracts(data,[model]),original)
        data['display_delay_correction_ms']=15
        changed=cache_contracts(data,[model])
        self.assertEqual(changed['observations'],original['observations'])
        self.assertNotEqual(changed['association'],original['association'])
        data['notes'][0]['target_seconds']=1.02
        self.assertEqual(cache_contracts(data,[model])['observations'],original['observations'])
        data['layout']['judgment_roi']=[.2,.3,.4,.1]
        self.assertNotEqual(cache_contracts(data,[model])['observations'],original['observations'])
        model['mask'][1][1]=0
        self.assertNotEqual(cache_contracts(data,[model])['observations']['templates'],original['observations']['templates'])

    def test_legacy_template_format_is_normalized_and_unknown_formats_rejected(self):
        saved={'media':{},'analysis_width':650,'models':[{'label':'PERFECT','hue':9,'mask':[[1,0,1],[0,1,0],[1,0,1]]}]}
        normalized=template_document(saved)
        self.assertEqual(normalized['format'],TEMPLATE_FORMAT)
        self.assertNotIn('format',saved)
        self.assertIsNone(template_document({**saved,'format':{'schema':'future'}}))
        with patch('piu_timeline.play.judgments.TEMPLATE_FORMAT',{'schema':'new encoding'}):
            self.assertIsNone(template_document(saved))
        saved['models'][0]['mask'][1][1]=2
        self.assertIsNone(template_document(saved))

    def test_changed_pixel_input_invalidates_features_even_with_same_file_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary);directory=output/'evidence/judgments';directory.mkdir(parents=True)
            times=np.array([1.,1.02]);features=np.zeros((2,19,38),dtype='uint8')
            np.savez_compressed(directory/'features-v3.npz',features=features,pts=times,times=times)
            (directory/'samples.json').write_text('[]')
            (output/'frames.jsonl').write_text(''.join(json.dumps({'source_pts_seconds':t,'playback_seconds':t})+'\n' for t in times))
            data={'media':{},'start_seconds':1.,'end_seconds':2.,'game_roi':[0,0,100,100],
                  'analysis_width':100,'frame_count':2,'layout':{'combo_roi':[.4,.5,.2,.1]}}
            with patch('piu_timeline.play.judgments.decode_frames',side_effect=AssertionError('legacy pixels should be reused')):
                result,_,_,_=collect_features(data,output)
            np.testing.assert_array_equal(result,features)
            data['layout']['judgment_roi']=[.2,.2,.4,.2]
            decoded=[(t,t,np.zeros((20,40,3),dtype='uint8')) for t in times]
            with patch('piu_timeline.play.judgments.decode_frames',return_value=iter(decoded)) as decode:
                result,_,_,_=collect_features(data,output)
            decode.assert_called_once()
            self.assertTrue(np.all(result==255))

    def test_touching_objects_and_partial_occlusion_preserve_word_shapes(self):
        models=[];clean={};bounds={}
        for label in LABELS:
            image=np.zeros((60,260,3),dtype='uint8')
            width=cv2.getTextSize(label,cv2.FONT_HERSHEY_SIMPLEX,.8,2)[0][0]
            x=(260-width)//2
            cv2.putText(image,label,(x,40),cv2.FONT_HERSHEY_SIMPLEX,.8,(0,230,255),2)
            feature=feature_map(image);ys,xs=np.nonzero(feature<18)
            hue=int(np.median(feature[ys,xs]));mask=(feature[ys.min():ys.max()+1,xs.min():xs.max()+1]<18).astype('uint8')
            models.append({'label':label,'hue':hue,'mask':mask.tolist()})
            clean[label]=image;bounds[label]=(int(xs.min()),int(ys.min()),mask.shape[1],mask.shape[0])
        reader=JudgmentReader(models)
        self.assertIsNone(reader.read(feature_map(np.zeros_like(image)))["label"])
        for label,image in clean.items():
            with self.subTest(label=label):
                x,y,w,h=bounds[label]
                damaged=image.copy()
                cv2.rectangle(damaged,(x+w//8,0),(x+w//8+max(3,w//15),59),(0,230,255),-1)
                result=reader.read(feature_map(damaged))
                self.assertEqual(result['label'],label)
                self.assertEqual(result['read_mode'],'partial_template')
        fragment=np.zeros_like(image)
        x,y,w,h=bounds['PERFECT']
        fragment[:,x:x+w//4]=clean['PERFECT'][:,x:x+w//4]
        self.assertIsNone(reader.read(feature_map(fragment))['label'])
        solid=np.zeros_like(image);cv2.rectangle(solid,(30,20),(230,45),(0,230,255),-1)
        self.assertIsNone(reader.read(feature_map(solid))['label'])

        tracker=JudgmentTracker()
        tracker.update(0,{'source_pts_seconds':5,**reader.read(feature_map(clean['PERFECT']))})
        tracker.update(.017,reader.read(feature_map(clean['PERFECT'])))
        x,y,w,h=bounds['PERFECT']
        for i in range(12):
            moving=clean['PERFECT'].copy()
            cv2.rectangle(moving,(x+i*w//12,0),(x+i*w//12+5,59),(0,230,255),-1)
            tracker.update(.034+i/60,reader.read(feature_map(moving)))
        self.assertEqual(len(tracker.events),1)

    def test_shrunken_word_with_touching_note_is_read_without_a_smaller_font_sample(self):
        image=np.zeros((80,300,3),dtype='uint8')
        cv2.putText(image,'GREAT',(60,50),cv2.FONT_HERSHEY_SIMPLEX,1.1,(0,230,255),2)
        feature=feature_map(image);ys,xs=np.nonzero(feature<18)
        mask=(feature[ys.min():ys.max()+1,xs.min():xs.max()+1]<18).astype('uint8')
        hue=int(np.median(feature[ys,xs]))
        reader=JudgmentReader([{'label':'GREAT','hue':hue,'mask':mask.tolist()}])
        for scale in (.7,.8,.9):
            with self.subTest(scale=scale):
                small=cv2.resize(mask,None,fx=scale,fy=scale,interpolation=cv2.INTER_LINEAR)
                h,w=small.shape;left=(300-w)//2;top=35
                damaged=np.zeros_like(image)
                damaged[top:top+h,left:left+w][small>0]=(0,230,255)
                cv2.rectangle(damaged,(left+w//3,0),(left+w//3+3,79),(0,230,255),-1)
                reading=reader.read(feature_map(damaged))
                self.assertEqual(reading['label'],'GREAT')
                self.assertEqual(reading['read_mode'],'partial_template')


    def test_persistent_word_and_unreadable_gap_do_not_create_inputs(self):
        tracker=JudgmentTracker()
        for t in (0,.02,.04,.06):tracker.update(t,observation())
        for t in (.08,.10,.15,.20,.25):tracker.update(t,observation(None))
        tracker.update(.27,observation());tracker.update(.29,observation())
        self.assertEqual(len(tracker.events),1)

    def test_a_completed_clear_interval_survives_later_unreadable_frames(self):
        for fps in (30,60,120):
            with self.subTest(fps=fps):
                frames,expected=reappearing_word_capture(fps);before=deepcopy(frames);tracker=JudgmentTracker()
                for frame in frames:tracker.update(frame['playback_seconds'],frame)
                self.assertEqual(len(tracker.events),2)
                event=tracker.events[-1]
                self.assertEqual(event['trigger'],'reappearance')
                self.assertEqual([event['lower_seconds'],event['upper_seconds']],expected)
                self.assertEqual(event['blank_observation_range'],[2/fps,expected[0]])
                self.assertEqual(event['detection_status'],'candidate')
                self.assertEqual(frames,before)
        frames,expected=reappearing_word_capture(hidden_frames=12);tracker=JudgmentTracker()
        for frame in frames:tracker.update(frame['playback_seconds'],frame)
        self.assertEqual(len(tracker.events),2)
        self.assertEqual([tracker.events[-1]['lower_seconds'],tracker.events[-1]['upper_seconds']],expected)
        self.assertEqual(tracker.events[-1]['detection_reason'],'judgment_observation_gap')
        frames,_=reappearing_word_capture(clear_seconds=.05);tracker=JudgmentTracker()
        for frame in frames:tracker.update(frame['playback_seconds'],frame)
        self.assertEqual(len(tracker.events),1,'unknown frames cannot complete a short clear interval')
        frames,_=reappearing_word_capture();tracker=JudgmentTracker()
        clear=[f for f in frames if f['blank']]
        frames=[f for f in frames if not f['blank']or f in (clear[0],clear[-1])]
        for frame in frames:tracker.update(frame['playback_seconds'],frame)
        self.assertEqual(len(tracker.events),1,'missing native frames cannot prove a continuous clear interval')
        frames,_=reappearing_word_capture(clear_seconds=.05,hidden_frames=12);tracker=JudgmentTracker()
        for frame in frames:
            if frame['label']is not None or frame['blank']:tracker.update(frame['playback_seconds'],frame)
        self.assertEqual(len(tracker.events),1,'a capture gap after a short blank does not prove reappearance')

    def test_word_change_blank_reappearance_and_animation_restart(self):
        tracker=JudgmentTracker()
        for t in (0,.02):tracker.update(t,observation())
        for t in (.04,.06):tracker.update(t,observation('GREAT'))
        for t in (.08,.10,.15,.20):tracker.update(t,observation(None,blank=True))
        for t in (.22,.24):tracker.update(t,observation('GREAT'))
        for t in (.26,.28):tracker.update(t,observation('GREAT',width=120,height=24))
        self.assertEqual([e['trigger'] for e in tracker.events],['label_change','label_change','reappearance','animation_restart'])
        self.assertEqual((tracker.events[1]['lower_seconds'],tracker.events[1]['upper_seconds']),(.02,.04))

    def test_label_change_after_occlusion_keeps_the_observation_gap(self):
        tracker=JudgmentTracker()
        tracker.update(0,observation());tracker.update(.02,observation())
        for t in (.04,.1,.2,.3):tracker.update(t,observation(None))
        tracker.update(.32,observation('GREAT'));tracker.update(.34,observation('GREAT'))
        event=tracker.events[-1]
        self.assertEqual((event['lower_seconds'],event['upper_seconds']),(.02,.32))
        self.assertEqual(event['detection_status'],'excluded')
        data={'notes':[{'lane':0,'status':'estimated','target_seconds':.32}],
              'matches':[],'coverage':{}}
        self.assertEqual(merge_judgments(data,[event])['matches'],[])

    def test_one_frame_size_glitch_does_not_confirm_a_refresh(self):
        tracker=JudgmentTracker()
        tracker.update(0,observation());tracker.update(.02,observation())
        tracker.update(.04,observation(width=120,height=24));tracker.update(.06,observation())
        self.assertEqual(len(tracker.events),1)

    def test_gradual_word_growth_retains_the_whole_native_observation_bracket(self):
        tracker=JudgmentTracker()
        sizes=[(134,16),(134,16),(136,17),(142,17),(148,19),(162,20),(162,20)]
        for i,(width,height) in enumerate(sizes):
            tracker.update(i/60,observation(width=width,height=height))
        self.assertEqual(len(tracker.events),2)
        event=tracker.events[-1]
        self.assertEqual(event['trigger'],'animation_restart')
        self.assertAlmostEqual(event['lower_seconds'],2/60)
        self.assertAlmostEqual(event['upper_seconds'],4/60)

    def test_new_label_is_not_lost_when_it_interrupts_pending_growth(self):
        tracker=JudgmentTracker()
        sizes=[(134,16),(134,16),(142,16),(149,16),(162,20)]
        for i,(width,height) in enumerate(sizes):
            tracker.update(i/60,observation(width=width,height=height))
        tracker.update(5/60,observation('MISS',width=87,height=20))
        tracker.update(6/60,observation('MISS',width=83,height=19))
        self.assertEqual([e['label'] for e in tracker.events],['PERFECT','MISS'])
        self.assertAlmostEqual(tracker.events[-1]['lower_seconds'],4/60)
        self.assertAlmostEqual(tracker.events[-1]['upper_seconds'],5/60)

    def test_gradual_growth_does_not_bridge_unknown_frames_or_slow_drift(self):
        for gap in (None,.08):
            tracker=JudgmentTracker()
            tracker.update(0,observation());tracker.update(.017,observation())
            tracker.update(.034,observation(width=106,height=21))
            if gap is None:
                tracker.update(.05,observation(None))
                start=.067
            else:
                start=gap+.034
            tracker.update(start,observation(width=112,height=22))
            tracker.update(start+.017,observation(width=118,height=23))
            tracker.update(start+.034,observation(width=118,height=23))
            self.assertEqual(len(tracker.events),1)

    def test_event_tracker_upgrade_replays_word_reads_without_pixel_recognition(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)
            data={'notes':[], 'matches':[], 'coverage':{}, 'media':{}, 'analysis_width':650,
                  'judgment_events':[{'label':'MISS','lower_seconds':99,'upper_seconds':100}]}
            data['judgment_cache']=cache_contracts(data,[])
            data['judgment_cache']['association']['events']={'schema':1,'revision':1}
            sizes=[(134,16),(134,16),(136,17),(142,17),(148,19),(162,20),(162,20)]
            frames=[{'source_pts_seconds':42+i/60,'playback_seconds':i/60,
                     **observation(width=w,height=h)} for i,(w,h) in enumerate(sizes)]
            trace=output/'judgments.jsonl'
            raw=''.join(json.dumps(frame)+'\n' for frame in frames);trace.write_text(raw)
            with patch('piu_timeline.play.judgments.collect_features',side_effect=AssertionError('must reuse word reads')), \
                    patch('piu_timeline.play.judgments.ocr_images',side_effect=AssertionError('must not OCR')):
                result=augment_judgments(data,output)
            self.assertEqual([e['label'] for e in result['judgment_events']],['PERFECT','PERFECT'])
            self.assertEqual(result['judgment_events'][-1]['trigger'],'animation_restart')
            self.assertEqual(trace.read_text(),raw)

    def test_first_three_and_bad_match_without_combo_and_miss_is_not_a_press(self):
        times=(1.,1.15,1.30,1.45,1.6)
        data={'notes':[{'lane':0,'status':'estimated','target_seconds':t} for t in times],
              'matches':[],'coverage':{},'unsupported_intervals':[]}
        events=[{'label':label,'lower_seconds':t-.01,'upper_seconds':t+.01,'trigger':'label_change'}
                for label,t in zip(LABELS,(1.,1.15,1.30,1.45,1.8))]
        result=merge_judgments(data,events)
        self.assertEqual(len(result['matches']),4)
        self.assertEqual([m['judgment_label'] for m in result['matches']],list(LABELS[:4]))
        self.assertTrue(all(m['combo_event'] is None for m in result['matches']))
        self.assertEqual(result['miss_candidates'][0]['note'],4)
        self.assertIsNone(result['miss_candidates'][0]['input_seconds'])

    def test_same_note_combo_and_word_are_corroboration_not_duplicate_input(self):
        data={'notes':[{'lane':0,'status':'estimated','target_seconds':1.}],
              'matches':[{'note':0,'combo_event':0,'target_seconds':1.,'combo_lower_seconds':.99,'combo_upper_seconds':1.01}],
              'coverage':{},'unsupported_intervals':[]}
        result=merge_judgments(data,[{'label':'PERFECT','lower_seconds':.99,'upper_seconds':1.01,'trigger':'label_change'}])
        self.assertEqual(len(result['matches']),1)
        self.assertEqual(result['matches'][0]['evidence_source'],'combo+judgment')

    def test_dense_miss_is_observed_without_guessing_a_missed_note(self):
        data={'notes':[{'lane':0,'status':'estimated','target_seconds':t} for t in (1.,1.1)],'matches':[],'coverage':{}}
        result=merge_judgments(data,[{'label':'MISS','lower_seconds':1.19,'upper_seconds':1.21,'trigger':'label_change'}])
        self.assertEqual(result['matches'],[])
        self.assertEqual(result['miss_candidates'],[])
        self.assertEqual(result['coverage']['observed_miss_updates'],1)
