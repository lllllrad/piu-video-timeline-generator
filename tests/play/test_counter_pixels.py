"""Digit-template changes must reuse exact native pixels and source timestamps."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import cv2

from piu_timeline.play.counter_pixels import CounterPixelWriter, counter_crops


class CounterPixelsTest(unittest.TestCase):
    def test_reader_refresh_rechecks_known_and_missing_values_without_changing_notes(self):
        from piu_timeline.play.analysis import refresh_counter_observations
        from piu_timeline.play.tracking import DigitReader
        data={**self.data,'analysis_width':150,'game_roi':[0,0,150,60],
              'layout':{'combo_roi':[0,0,1,1]},'frame_observation_version':2}
        def draw(text):
            rgb=np.zeros((60,150,3),dtype='uint8')
            cv2.putText(rgb,text,(5,45),cv2.FONT_HERSHEY_SIMPLEX,1.5,(255,255,255),3)
            return rgb
        reader=DigitReader()
        for source in (1,2):
            for value in (94,95):reader.train(draw(str(value)),value,source=source)
        evidence=self.directory/'evidence';evidence.mkdir();reader.save(evidence/'digit-templates.npz')
        images=[draw('94'),(draw('94')*.5+35).astype('uint8'),draw('95')]
        writer=CounterPixelWriter(data,self.directory);records=[]
        for (pts,time,_),image,value in zip(self.frames,images,(102,None,None),strict=True):
            writer.append(pts,time,image)
            records.append({'source_pts_seconds':pts,'playback_seconds':time,'combo':value,
                            'combo_confidence':0.,'notes':[{'lane':0,'x':.2,'y':.5}]})
        writer.save();trace=self.directory/'frames.jsonl'
        original=''.join(json.dumps(r)+'\n'for r in records);trace.write_text(original)
        with patch('piu_timeline.play.counter_pixels.decode_frames',side_effect=AssertionError('must reuse pixels')):
            refresh_counter_observations(data,self.directory,replace_font=True)
        updated=[json.loads(line)for line in trace.read_text().splitlines()]
        self.assertEqual([r['combo']for r in updated],[94,94,95])
        self.assertEqual(updated[1]['combo_read_mode'],'contrast_template')
        for before,after in zip(records,updated,strict=True):
            for key in ('source_pts_seconds','playback_seconds','notes'):self.assertEqual(after[key],before[key])
        self.assertEqual((self.directory/'frames.base.jsonl').read_text(),original)

    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory=Path(self.temporary.name)
        self.data={'media':{'path':'synthetic-recording','size_bytes':123,'mtime_ns':456},
                   'start_seconds':10.,'end_seconds':10.2,'analysis_width':20,
                   'game_roi':(0,0,20,12),'layout':{'combo_roi':(.25,.25,.5,.5)},'frame_count':3}
        rgb=np.arange(180,dtype=np.uint8).reshape(6,10,3)
        self.frames=[(110.001,10.001,rgb),(110.018,10.018,rgb+1),(110.051,10.051,rgb+2)]

    def test_legacy_decode_is_reused_exactly_without_retiming_or_second_decode(self):
        with patch('piu_timeline.play.counter_pixels.decode_frames',return_value=iter(self.frames)) as decode:
            first=list(counter_crops(self.data,self.directory))
        self.assertEqual(decode.call_args.kwargs['region'],self.data['layout']['combo_roi'])
        with patch('piu_timeline.play.counter_pixels.decode_frames',side_effect=AssertionError('decoded again')):
            second=list(counter_crops(self.data,self.directory))
        for expected,initial,saved in zip(self.frames,first,second,strict=True):
            self.assertEqual(saved[:2],expected[:2])
            np.testing.assert_array_equal(saved[2],expected[2])
            np.testing.assert_array_equal(initial[2],saved[2])
        self.assertAlmostEqual(second[2][1]-second[1][1],.033)

    def test_capture_copies_decoder_buffers_and_initial_acquisition_needs_no_replay(self):
        writer=CounterPixelWriter(self.data,self.directory)
        buffer=np.zeros((6,10,3),dtype=np.uint8)
        for index,(pts,time,_) in enumerate(self.frames):
            buffer.fill(index);writer.append(pts,time,buffer)
        writer.save();buffer.fill(255)
        with patch('piu_timeline.play.counter_pixels.decode_frames',side_effect=AssertionError('decoded again')):
            saved=list(counter_crops(self.data,self.directory))
        for i,(_,_,image) in enumerate(saved):self.assertTrue((image==i).all())

    def test_stale_source_geometry_and_frame_count_fail_instead_of_silently_redecoding(self):
        writer=CounterPixelWriter(self.data,self.directory)
        for frame in self.frames:writer.append(*frame)
        writer.save()
        for key in ('media','layout','frame_count'):
            changed=deepcopy(self.data)
            if key=='media':changed[key]['mtime_ns']+=1
            elif key=='layout':changed[key]['combo_roi']=(.1,.2,.3,.4)
            else:changed[key]+=1
            with self.subTest(key=key),self.assertRaises(ValueError):
                list(counter_crops(changed,self.directory))

    def test_incomplete_consumption_does_not_publish_a_partial_cache(self):
        with patch('piu_timeline.play.counter_pixels.decode_frames',return_value=iter(self.frames)):
            crops=counter_crops(self.data,self.directory);next(crops);crops.close()
        self.assertFalse((self.directory/'counter-pixels.npz').exists())
        with patch('piu_timeline.play.counter_pixels.decode_frames',return_value=iter(self.frames[:2])):
            with self.assertRaisesRegex(ValueError,'Incomplete'):list(counter_crops(self.data,self.directory))
        self.assertFalse((self.directory/'counter-pixels.npz').exists())

    def test_corrupted_timestamp_and_pixel_arrays_fail_explicitly(self):
        for mode in ('timestamps','dtype','shape'):
            writer=CounterPixelWriter(self.data,self.directory)
            for frame in self.frames:writer.append(*frame)
            writer.save()
            path=self.directory/'counter-pixels.npz'
            with np.load(path,allow_pickle=False) as z:arrays={k:z[k]for k in z.files}
            if mode=='timestamps':arrays['times'][1]=arrays['times'][0]
            elif mode=='dtype':arrays['images']=arrays['images'].astype(float)
            else:arrays['images']=arrays['images'][:,:,:-1]
            np.savez_compressed(path,**arrays)
            with self.subTest(mode=mode),self.assertRaises(ValueError):list(counter_crops(self.data,self.directory))
