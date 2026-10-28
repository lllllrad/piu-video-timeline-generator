import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeScene} from './fixtures.ts';
import {candidates} from '../../src/piu_timeline/derived/candidates.ts';
import {recoverRows} from '../../src/piu_timeline/derived/recovery.ts';

function scene(spacing=40,firstTarget=.98,nextTarget=1.07){
 const d=nativeScene([[firstTarget,0],[nextTarget,1]],spacing);
 Object.assign(d,{matches:[],combo_events:[{delta:2,lower_seconds:1,upper_seconds:1.09,
  status:'excluded',reason:'ambiguous_note_or_combo_association'}],
  judgment_events:[{label:'GOOD',delta:1,lower_seconds:1.07,upper_seconds:1.08,
   status:'candidate',detection_status:'candidate'}],
  hold_analysis:{holds:[{lane:4,start_range:[.5,.51],end_range:[1.5,1.51]}],receptor_runs:[
   {lane:1,lit:true,frames:3,onset_range:[1.07,1.08],onset_source_pts_seconds:[81.07,81.08],start_seconds:1.08,end_seconds:1.12}]}});
 for(const n of d.notes)n.type_status='tap';
 return d;
}
function events(d){return [
 {...d.combo_events[0],source:'combo',event:0},
 {...d.judgment_events[0],source:'judgment',event:0}];}
for(const spacing of [20,40,80])test(`a word keeps its own capacity beside an aggregate counter at spacing ${spacing}`,()=>{
 const d=scene(spacing),before=structuredClone(d),[options]=candidates(d,events(d));
 const word=options[1].find(e=>e.source==='judgment'),counter=options[1].find(e=>e.source==='combo');
 assert.equal(word.aggregate_row_capacity,1);assert.equal(word.alternative_rows,1);
 assert.equal(counter.aggregate_row_capacity,2);
 const [matches,recovered]=recoverRows(d);
 assert.deepEqual(recovered,[1]);assert.equal(matches[0].judgment_label,'GOOD');assert.equal(matches[0].combo_event,null);
 assert.deepEqual([matches[0].observation_lower_seconds,matches[0].observation_upper_seconds],[1.07,1.08]);
 assert.deepEqual(matches[0].lane_onset_source_pts_seconds,[81.07,81.08]);assert.deepEqual(d,before);
});
test('an aggregate neighbor cannot erase competing rows for a single word',()=>{
 const d=scene();d.notes[0].target_seconds=1.01;
 Object.assign(d.judgment_events[0],{lower_seconds:1.035,upper_seconds:1.045});
 d.hold_analysis.receptor_runs.push({...d.hold_analysis.receptor_runs[0],lane:0,onset_range:[1.035,1.045]});
 const [options]=candidates(d,events(d));
 for(const i of [0,1]){
  const word=options[i].find(e=>e.source==='judgment');
  assert.equal(word.aggregate_row_capacity,1);assert.equal(word.alternative_rows,2);
 }
 assert.deepEqual(recoverRows(d)[1],[]);
});
test('missing lane proof or a MISS word cannot supply a tap from a mixed popup family',()=>{
 for(const mode of ['no-onset','MISS']){
  const d=scene();
  if(mode==='no-onset')d.hold_analysis.receptor_runs=[];
  else d.judgment_events[0].label='MISS';
  assert.deepEqual(recoverRows(d)[1],[],mode);
 }
});
test('a broad paired counter cannot hide a narrow competing word from exclusivity checks',()=>{
 const d=scene(40,1,1.08);d.hold_analysis.holds=[];
 Object.assign(d.combo_events[0],{delta:1,lower_seconds:1,upper_seconds:1.08});
 Object.assign(d.judgment_events[0],{lower_seconds:1.055,upper_seconds:1.065});
 d.judgment_events.push({...d.judgment_events[0],lower_seconds:1.11,upper_seconds:1.12});
 Object.assign(d.hold_analysis.receptor_runs[0],{onset_range:[1.105,1.12],start_seconds:1.12,end_seconds:1.16});
 const [options]=candidates(d,[...events(d),{...d.judgment_events[1],source:'judgment',event:1}]);
 assert.equal(options[1].find(o=>o.source==='judgment'&&o.event===0).alternative_rows,1);
 assert.deepEqual(recoverRows(d)[1],[],'a second plausible refresh still competes even if only one has lane support');
});
test('an aggregate counter cannot truncate the independently located word row',()=>{
 const d=scene();d.notes=nativeScene([[1,0],[1.04,1],[1.08,2]]).notes;d.hold_analysis.holds=[];
 Object.assign(d.judgment_events[0],{lower_seconds:1.075,upper_seconds:1.085});
 const [options]=candidates(d,events(d));
 const word=options[2]?.find(o=>o.source==='judgment');
 assert.ok(word,'the counter capacity cannot discard the third row before examining the word');
 assert.equal(word.alternative_rows,1);assert.equal(word.aggregate_row_capacity,1);
});
