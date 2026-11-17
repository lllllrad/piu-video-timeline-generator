import test from 'node:test';
import assert from 'node:assert/strict';
import {binding} from '../../../src/piu_timeline/derived/effect_references/play.ts';
import {links} from '../../../src/piu_timeline/derived/effect_references/play_links.ts';
import {recognizePlay} from '../../../src/piu_timeline/derived/effect_references/play_search.ts';
import {sequence} from '../../../src/piu_timeline/derived/effect_references/model.ts';
test('play refuses foreign source, segment and sampled-only captures',()=>{
 const ref={source:'/tmp/recording.mkv',identity:{size:12,mtime_ns:123456789123456789n},manifest:{segment:'/tmp/play/segment-001'}};
 const query={source:ref.source,source_identity:{...ref.identity},segment:'/tmp/play/segment-001.build-1',selection:'all_light_candidates'};
 assert.doesNotThrow(()=>binding(ref,query));
 assert.throws(()=>binding(ref,{...query,source:'/tmp/other.mkv'}),/another source/);
 assert.throws(()=>binding(ref,{...query,segment:'/tmp/play/segment-002'}),/another segment/);
 assert.throws(()=>binding(ref,{...query,selection:'sampled_off_to_on'}),/all candidate/);
});
const event=(id='one')=>({id,lane:0,status:'ordered_image_candidate',observation_range:[10,10.1]});
const data=()=>({notes:[{lane:0,note_type:'tap',visible_start_seconds:9.5,visible_end_seconds:10,target_seconds:10.03}],matches:[{note:0,raw_offset_ms:20}],hold_analysis:{holds:[]}});
test('unique image candidate is informational and never rewrites existing timing',()=>{
 const source=data(),before=structuredClone(source),result=links(source,[event()]);
 assert.equal(result[0].status,'unique_tap_image_candidate');assert.equal(result[0].physical_input_range,null);
 assert.deepEqual(source,before);
 assert.equal(links(source,[{...event(),status:'appearance_only_phase_unresolved'}])[0].status,'image_phase_unresolved');
 assert.equal(links(source,[{...event(),status:'large_RGB_alignment_error'}])[0].status,'no_image_correspondence');
});
test('competing notes, overlapping windows and censored holds remain ambiguous',()=>{
 const source=data();source.notes.push({...source.notes[0],visible_start_seconds:9.8});
 assert.equal(links(source,[event()])[0].status,'ambiguous_note_candidates');
 assert.ok(links(data(),[event(),event('two')]).every(r=>r.status==='overlapping_effect_windows'));
 const held:any=data();held.hold_analysis.holds=[{lane:0,start_range:[9,9.1],last_body_seconds:9.5}];
 assert.equal(links(held,[event()])[0].status,'hold_context');
});
test('bounded play search validates RGB and retains ambiguity for static images',()=>{
 const frames=Array.from({length:34},(_,i)=>({offset:i,pts:100+i/60,time:i/60,crop:[0,0,47,47],envelopes:[]}));
 const e={id:'one',lane:0,kind:0,marker:8/60,frames};
 const capture={events:[e],pixels:new Uint8Array(34*47*47*3).fill(70),exclusions:new Uint8Array(34*47*47)};
 const result=recognizePlay(capture,e,[{id:'rgb',patches:sequence(capture,e)}]);
 assert.equal(result.status,'appearance_only_phase_unresolved');assert.equal(result.best.fit.rawError,0);
});
