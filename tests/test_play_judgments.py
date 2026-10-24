import unittest
import cv2
import numpy as np
from piu_timeline.play_judgments import JudgmentReader, JudgmentTracker, feature_map, merge_judgments, LABELS


def observation(label='PERFECT',width=100,height=20,blank=False):
    return {'label':label,'confidence':.99 if label else 0,'box':[5,5,width,height] if label else None,'blank':blank}


class JudgmentTest(unittest.TestCase):
    def test_all_five_words_are_classified_by_shape_without_counter(self):
        models=[];images={}
        for label in LABELS:
            image=np.zeros((50,220,3),dtype='uint8')
            width=cv2.getTextSize(label,cv2.FONT_HERSHEY_SIMPLEX,.8,2)[0][0]
            cv2.putText(image,label,((220-width)//2,33),cv2.FONT_HERSHEY_SIMPLEX,.8,(0,230,255),2)
            feature=feature_map(image);ys,xs=np.nonzero(feature<18)
            hue=int(np.median(feature[ys,xs]))
            mask=(feature[ys.min():ys.max()+1,xs.min():xs.max()+1]<18).astype('uint8')
            models.append({'label':label,'hue':hue,'mask':mask.tolist()});images[label]=image
        reader=JudgmentReader(models)
        for label,image in images.items():
            with self.subTest(label=label):self.assertEqual(reader.read(feature_map(image))['label'],label)
        self.assertIsNone(reader.read(feature_map(np.zeros_like(image)))['label'])

    def test_persistent_word_and_unreadable_gap_do_not_create_inputs(self):
        tracker=JudgmentTracker()
        for t in (0,.02,.04,.06):tracker.update(t,observation())
        for t in (.08,.10,.15,.20,.25):tracker.update(t,observation(None))
        tracker.update(.27,observation());tracker.update(.29,observation())
        self.assertEqual(len(tracker.events),1)

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
