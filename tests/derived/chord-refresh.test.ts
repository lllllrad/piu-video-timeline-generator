import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeScene} from './fixtures.ts';
import type {RecordData} from '../../src/piu_timeline/derived/types.ts';
import {present} from '../../src/piu_timeline/derived/hold_presentation.ts';
import {recoverRows} from '../../src/piu_timeline/derived/recovery.ts';

function scene(spacing=40,fps=60):RecordData{
 const d=nativeScene([[1,0],[1,1]],spacing,fps,5,{end:1.4});
 d.notes.forEach(n=>Object.assign(n,{target_seconds:1,prediction_uncertainty_seconds:1/fps,type_status:'tap',timing_reconstruction:{status:'restored'}}));
 const lo=1,hi=1+1/fps;
 return {...d,matches:[{note:0,target_seconds:1,combo_event:0,judgment_event:0,row_note_count:1,
  judgment_label:'PERFECT',combo_lower_seconds:lo,combo_upper_seconds:hi}],
 combo_events:[{delta:1,status:'matched',lower_seconds:lo,upper_seconds:hi}],
 judgment_events:[{delta:1,label:'PERFECT',detection_status:'candidate',lower_seconds:lo,upper_seconds:hi}],
 hold_analysis:{holds:[],unresolved_tracks:[],receptor_runs:[]},median_frame_interval_seconds:1/fps};
}
for(const spacing of[20,40,80])for(const fps of[30,60,120])test(`complete a partly owned visible chord: ${spacing} spacing / ${fps} fps`,()=>{
 const d=scene(spacing,fps),before=structuredClone(d),[matches,recovered]=recoverRows(d);
 assert.deepEqual(recovered,[1]);assert.equal(matches.length,2);
 assert.deepEqual(matches[0],{...before.matches[0],row_note_count:2});
 assert.equal(matches[1].combo_event,0);assert.equal(matches[1].judgment_event,0);
 assert.equal(matches[1].row_note_count,2);assert.equal(matches[1].target_seconds,1);
 assert.deepEqual([matches[1].observation_lower_seconds,matches[1].observation_upper_seconds],[1,1+1/fps]);
 assert.deepEqual(d,before);
 assert.deepEqual(recoverRows({...d,matches})[1],[]);
});
for(const mode of['stagger','same_lane','foreign_counter','foreign_word','one_channel','hold','unknown','failed_timing','competing_popup','processing_conflict'])test(`partial chord retains uncertainty: ${mode}`,()=>{
 const d=scene();
 if(mode==='stagger')d.notes[1].target_seconds+=.001;
 if(mode==='same_lane')d.notes[1].lane=0;
 if(mode==='foreign_counter')d.matches[0].combo_event=1;
 if(mode==='foreign_word')d.matches[0].judgment_event=1;
 if(mode==='one_channel')delete d.matches[0].judgment_event;
 if(mode==='hold')d.hold_analysis.unresolved_tracks.push({visible_start_seconds:.9,visible_end_seconds:1.1});
 if(mode==='unknown')d.notes[1].type_status='unknown';
 if(mode==='failed_timing')d.notes[1].timing_reconstruction.status='failed';
 if(mode==='competing_popup')d.judgment_events.push({...d.judgment_events[0],lower_seconds:1.02,upper_seconds:1.03});
 if(mode==='processing_conflict')d.visual_channels={processing:{notes:[{note:1,status:'disappeared_near_receptor',range:[.7,.72]}]}};
 const before=structuredClone(d),[matches,recovered]=recoverRows(d);
 assert.deepEqual(recovered,[]);assert.deepEqual(matches,d.matches);assert.deepEqual(d,before);
});

test('a chord completed after label recovery keeps the full row size in presentation',()=>{
 const d=scene();d.matches[0].recovery_method='unique_row_with_independent_lane_onset';delete d.matches[0].judgment_event;delete d.matches[0].judgment_label;
 d.unsupported_intervals=[];d.coverage={};d.native_body_risk_available=true;
 const view=present(d);
 assert.equal(view.matches.length,2);
 assert.ok(view.matches.every(m=>m.row_note_count===2));
 assert.equal(view.matches.find(m=>m.note===1).recovery_generation,2);
});
