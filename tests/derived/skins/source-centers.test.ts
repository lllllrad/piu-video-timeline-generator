import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';

const script=String.raw`
import json,tempfile
from pathlib import Path
from unittest.mock import patch
import cv2,numpy as np
from piu_timeline.play.skins.source_centers import prepare,proposals
from piu_timeline.play.skins.bank import load_bank
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);source=root/'recording.bin';source.write_bytes(b'original recording')
 stat=source.stat();media={'path':str(source),'size_bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns}
 rgb=np.zeros((120,120,3),dtype='uint8');entries=[]
 for index,role in enumerate(('tap','hold_start')):
  image=np.zeros((50,40,3),dtype='uint8');image[12:32,10:30]=[255,255,255];image[14:30,12:28]=[20,150,245]
  if role=='hold_start':image[32:,16:24]=[20,150,245]
  cv2.imwrite(str(root/(role+'.png')),np.dstack([image[:,:,::-1],np.full((50,40),255,dtype='uint8')]))
  x=10+50*index;crop=[x,40,x+40,90];rgb[40:90,x:x+40]=image
  regions=[{'name':'cap','box':[10,12,30,32]}]
  if role=='hold_start':regions.append({'name':'connection','box':[16,34,24,50]})
  entries.append({'id':role,'role':role,'lane_kind':0,'anchor_pixels':[20,18],'image':role+'.png','regions':regions,
   'source_evidence':{'media':media,'roi':[0,0,120,120],'reference_dimensions':[120,120],
    'source_crop':crop,'playback_seconds':2.,'source_pts_seconds':52.}})
 document={'schema':1,'skin':'synthetic-bright','spacing_pixels':24,'templates':entries}
 bank_path=root/'bank.json';bank_path.write_text(json.dumps(document));bank=load_bank(bank_path)
 p=proposals(bank)
 assert p['tap']['center_pixels']==[20,22] and p['hold_start']['center_pixels']==[20,22]
 assert p['hold_start']['basis']=='complete_tap_cap_rgb_match'
 def build(name,image=rgb,pts=52.):
  with patch('piu_timeline.play.skins.source_centers.decode_frames',return_value=iter([(pts,2.,image)])):
   return prepare(bank_path,root/name)
 path=build('verified');verified=load_bank(path)
 assert set(verified['anchor_registrations'])=={'tap','hold_start'}
 assert all(t['anchor_pixels']==[20,18] and t['native_center_pixels']==[20,22]for t in verified['templates'])
 assert all(r['center_offset_y_pixels']==4 for r in verified['anchor_registrations'].values())
 changed=rgb.copy();changed[54,74,0]^=1
 partial=load_bank(build('partial',changed))
 assert set(partial['anchor_registrations'])=={'tap'}
 invalid_reference=rgb.copy();invalid_reference[54,24,0]^=1
 try:build('invalid-reference',invalid_reference)
 except ValueError:pass
 else:raise AssertionError('unverified tap geometry supplied a hold center')
 for mode in ('wrong_pts','changed_media','overwritten_output'):
  try:
   if mode=='wrong_pts':build('wrong',pts=52.01)
   elif mode=='changed_media':
    source.write_bytes(b'changed source');build('changed')
   else:build('verified')
  except (ValueError,FileExistsError):pass
  else:raise AssertionError(mode+' reused an invalid source')
 # Two independently sourced caps can measure a leading glyph beside a stem.
 direct=load_bank(bank_path);duplicate=json.loads(json.dumps(document['templates'][0]));duplicate['id']='independent-tap'
 duplicate['source_evidence']['source_pts_seconds']=53.;duplicate['source_evidence']['playback_seconds']=3.
 bank_path.write_text(json.dumps({**document,'templates':[document['templates'][0],duplicate,document['templates'][1]]}))
 leading=load_bank(bank_path)
 # Change cap texture enough to rule out transferring a full RGB match while
 # preserving independently measured bright glyph boundaries and shoulders.
 leading['templates'][2]['rgb'][14:30,12:28]=[245,245,245]
 result=proposals(leading)['hold_start'];assert result['basis']=='leading_cap_with_independently_measured_dimensions'
 assert result['center_pixels']==[20,22] and result['lower_shoulder_pixels']>0
 leading['templates'][2]['rgb'][30:32]=0
 assert 'hold_start'not in proposals(leading),'a missing lower glyph boundary is not completed from its stem'
 bank_path.write_text(json.dumps(document))
 # Incomplete or clipped glyphs do not define a center.
 broken=load_bank(bank_path);broken['templates'][0]['rgb'][:]=255
 assert proposals(broken)=={}
 print(json.dumps({'registered':len(verified['anchor_registrations'])}))
`;
test('bright-source geometry and complete cap RGB need exact native source pixels and PTS',()=>{
 const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
 assert.equal(r.registered,2);
});
