import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';

const script=String.raw`
import copy,json,tempfile
from pathlib import Path
import cv2,numpy as np
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.coordinates import measure
from piu_timeline.play.skins.observations import observe
from piu_timeline.play.skins.coverage import reference_rows,image_spans
from piu_timeline.play.skins.held import BodyAtReceptor
from piu_timeline.play.skins.replay import detector_metadata
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);entries=[];glyphs={}
 for kind in [0,2,4]:
  glyphs[kind]=np.random.default_rng(19+kind).integers(35,245,(40,40,3),dtype='uint8')
  reference=np.full((160,160,3),[12,14,18],dtype='uint8');reference[60:100,60:100]=glyphs[kind]
  cv2.imwrite(str(root/f'{kind}.png'),np.dstack([reference[:,:,::-1],np.full((160,160),255,dtype='uint8')]))
  entries.append({'id':str(kind),'role':'tap','lane_kind':kind,'image':f'{kind}.png','anchor_pixels':[80,80],
   'sampling_context':[[0,0,160,160]],'regions':[{'name':'cap','box':[60,60,100,100],'maximum_error':.002}]})
 manifest=root/'bank.json';manifest.write_text(json.dumps({'schema':1,'skin':'generated-context','spacing_pixels':40,'templates':entries}))
 bank=load_bank(manifest);results=[];corruption_rejected=False;missing_origin_rejected=False
 for scale in [.5,1,1.5]:
  width,height=round(200*scale),round(240*scale)
  layout={'receptor_y':.1,'note_y_max':.95,'judgment_roi':[0,0,0,0],'combo_roi':[0,0,0,0],
   'lanes':[{'x':x/200}for x in [20,60,100,140,180]]}
  detector=SkinDetector(bank,layout,width,height)
  for name,kind,x,y in [('left',0,20,140),('right',4,180,140),('bottom',2,100,220),('clipped',2,100,226)]:
   image=np.full((240,200,3),[12,14,18],dtype='uint8');top,bottom=max(0,y-20),min(240,y+20)
   image[top:bottom,x-20:x+20]=glyphs[kind][top-y+20:bottom-y+20]
   image=cv2.resize(image,(width,height),interpolation=cv2.INTER_AREA)
   found=detector.detect(image);caps=[o for o in found if o['role']!='hold_body']
   result={'id':f'{name}-{scale}','name':name,'scale':scale,'caps':[], 'role_origins':[], 'coordinate_origins':[]}
   if caps:
    frame={'playback_seconds':1.25,'source_pts_seconds':42.125,'skin_observations':found}
    data={'analysis_width':width,'analysis_height':height,'layout':layout,
     'skin_detector':detector_metadata(manifest,bank),
     'notes':[{'lane':o['lane'],'points':[[1.25,o['y']*height]]}for o in caps]}
    coordinates=measure(data,[frame]);roles=observe(data,[frame]);coverage=reference_rows(data,cap_only=True)
    result['role_origins']=[r['observations'][0]['sampling_origin_pixels']for r in roles['notes']]
    result['coordinate_origins']=[r['observations'][0]['sampling_origin_pixels']for r in coordinates['notes']]
    for o in caps:
     phase=o.get('sampling_phase_pixels',[0,0]);origin=o['sampling_origin_pixels'];bounds=o['bounds_pixels']
     legacy={**o,'bounds_pixels':[bounds[0]-origin[0],bounds[1]-origin[1],bounds[0]-origin[0]+round(160*scale),bounds[1]-origin[1]+round(160*scale)]}
     legacy.pop('sampling_origin_pixels');legacy.pop('alternatives',None)
     result['caps'].append({'lane':o['lane'],'x':o['x']*width,'y':o['y']*height,'origin':origin,'bounds':bounds,
      'coverage':image_spans(o,coverage),'legacy_coverage':image_spans(legacy,coverage),
      'source_point_projection':[bounds[i]+phase[i]+scale*80-origin[i]for i in (0,1)],'time':1.25,'source_pts':42.125})
    if name=='bottom'and scale==1:
     corrupted=copy.deepcopy(frame);corrupted['skin_observations'][0]['sampling_origin_pixels'][1]+=1
     try:measure(data,[corrupted])
     except ValueError:corruption_rejected=True
     incomplete=copy.deepcopy(frame);incomplete['skin_observations'][0].pop('sampling_origin_pixels')
     try:measure(data,[incomplete])
     except ValueError:missing_origin_rejected=True
   results.append(result)
 body=np.full((160,160,3),[12,14,18],dtype='uint8');body[40:120,60:100]=[30,140,230]
 cv2.imwrite(str(root/'body.png'),np.dstack([body[:,:,::-1],np.full((160,160),255,dtype='uint8')]))
 document=json.loads(manifest.read_text());document['templates'].append({'id':'body','role':'hold_body','lane_kind':2,
  'image':'body.png','anchor_pixels':[80,80],'sampling_context':[[0,0,160,160]],'regions':[{'name':'body','box':[60,40,100,120]}]})
 manifest.write_text(json.dumps(document));extra=load_bank(manifest);risk=BodyAtReceptor(SkinDetector(extra,layout,200,240))
 old={'template':'body','lane':2,'role':'hold_body','bounds_pixels':[20,0,180,160]}
 new={**old,'bounds_pixels':[80,40,120,120],'sampling_origin_pixels':[60,40]}
 print(json.dumps({'results':results,'corruption_rejected':corruption_rejected,'missing_origin_rejected':missing_origin_rejected,
  'old_risk':risk.explain([old]),'new_risk':risk.explain([new])}))
`;
const observed=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
for(const r of observed.results)test(`unused reference context does not clip visible measurements: ${r.id}`,()=>{
 if(r.name==='clipped'){
  assert.deepEqual(r.caps,[],'actually clipped glyph pixels cannot supply an intact cap');return;
 }
 assert.equal(r.caps.length,1);
 const c=r.caps[0];const x=r.name==='left'?20:r.name==='right'?180:100;const y=r.name==='bottom'?220:140;
 assert.equal(c.lane,r.name==='left'?0:r.name==='right'?4:2);
 assert.ok(Math.abs(c.x-x*r.scale)<1e-6);assert.ok(Math.abs(c.y-y*r.scale)<1e-6);
 c.source_point_projection.forEach((p:number,i:number)=>assert.ok(Math.abs(p-[c.x,c.y][i])<1e-6));
 assert.deepEqual(r.role_origins,[c.origin]);assert.deepEqual(r.coordinate_origins,[c.origin]);
 assert.deepEqual(c.coverage,[[(y-20)*r.scale,(y+20)*r.scale]]);
 assert.deepEqual(c.legacy_coverage,c.coverage,'retained full-canvas records use the same physical support');
 assert.equal(c.time,1.25);assert.equal(c.source_pts,42.125);
});
test('a changed comparison origin cannot silently move the source-bound coordinate',()=>{
 assert.equal(observed.corruption_rejected,true);
 assert.equal(observed.missing_origin_rejected,true);
});
test('body risk keeps physical receptor support across old and cropped reference canvases',()=>{
 assert.deepEqual(observed.new_risk,observed.old_risk);
 assert.deepEqual(observed.new_risk.map((r:{vertical_range_pixels:number[]})=>r.vertical_range_pixels),[[40,120]]);
});
