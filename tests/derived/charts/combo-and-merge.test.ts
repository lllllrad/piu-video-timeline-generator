import test from 'node:test';
import assert from 'node:assert/strict';
import {parse,text,grid,standard,expanded} from '../../../src/piu_timeline/derived/charts/ucs.ts';
import {annotate} from '../../../src/piu_timeline/derived/charts/combo.ts';
import {merge,remap} from '../../../src/piu_timeline/derived/charts/merge.ts';
const header = (split=4,combo=true) => `:Format=1\n:Mode=Single\n${combo?':Combo=1\n':''}:BPM=120\n:Delay=0\n:Beat=4\n:Split=${split}\n`;
const hold = (count:number|null=1) => parse(header()+[
 'M.... ?', 'H.... ?', 'H.... ?', 'H.... ?', `H.... ${count===null?'?':count}`, 'H.... ?', 'H.... ?', 'H.... ?', 'W.... ?',
 ...Array(7).fill('.....'),
].join('\n'));
const proof = () => ({placements:[{note:0,lane:0,kind:'hold',start:0,end:8,section:0,row:0,end_section:0,end_row:8,song_seconds:0,end_song_seconds:1}],
 unresolved:[],summary:{placed_taps:0,placed_holds:1,unresolved_note_heads:0},transcription_alignment:{song_start_seconds:10}});
const evidence = () => ({notes:[{lane:0,status:'estimated',target_seconds:10}],display_delay_correction_ms:0,
 hold_analysis:{holds:[{head_note:0,input:{segments:[{lower_seconds:10,upper_seconds:11,frames:60}]}}]},
 combo_events:[{delta:1,lower_seconds:10.492,upper_seconds:10.508}],judgment_events:[]});

test('combo extension preserves default 1, zero, weighted and unknown rows without changing timing',()=>{
 const doc=parse(header()+'M.... 0\nH....\nH.... 10\nH.... ?\nW.... 0\n');
 assert.deepEqual(doc.sections[0].combo_counts,[0,1,10,null,0]);assert.deepEqual(parse(text(doc)),doc);
 assert.deepEqual(grid(standard(doc)).map(r=>r[2].toString()),grid(doc).map(r=>r[2].toString()));
 assert.ok(!text(standard(doc)).includes(':Combo='));assert.ok(!text(standard(doc)).includes('?'));
 assert.throws(()=>expanded(doc,5),/annotated combo timing/);
 for(const suffix of ['-1','1.2','1 2','NaN','9007199254740992'])assert.throws(()=>parse(header()+`H.... ${suffix}\n`));
 assert.throws(()=>parse(header(4,false)+'H.... 2\n'));
 assert.throws(()=>text({...doc,sections:[{...doc.sections[0],combo_counts:[1]}]}),/one value per row/);
});
for(const label of ['counter','GOOD','BAD'])test(`automatic hold tick is separate from physical presses and grades: ${label}`,()=>{
 const input=evidence();
 if(label!=='counter') {input.combo_events=[];input.judgment_events=[{label,lower_seconds:10.492,upper_seconds:10.508}];}
 const before=structuredClone(input),geometry=hold(null),[out,annotation]=annotate(geometry,proof(),input);
 assert.equal(out.sections[0].combo_counts[4],1);assert.equal(annotation.placed.length,1);
 assert.equal(out.sections[0].combo_counts[0],null,'visual head does not fabricate a judgment');
 assert.deepEqual(out.sections.map(s=>s.rows),geometry.sections.map(s=>s.rows));assert.deepEqual(input,before);
});
test('aggregate jumps and nonmatching timing brackets remain unknown',()=>{
 for(const change of [d=>{d.combo_events[0].delta=10;},
  d=>{d.combo_events[0].lower_seconds=10.47;d.combo_events[0].upper_seconds=10.49;}]){
  const d=evidence();change(d);const [out,annotation]=annotate(hold(null),proof(),d);
  assert.ok(out.sections[0].combo_counts.every((c,i)=>i>8||c===null));assert.equal(annotation.placed.length,0);assert.ok(annotation.unresolved.length>0);
 }
});
test('simultaneous holds, a chord and an unrelated unbounded note do not multiply a timing-row count',()=>{
 const doc=hold(null);doc.sections[0].rows=doc.sections[0].rows.map((r,i)=>i<=8?r[0]+r[0]+(i===4?'XX.':'...'):r);
 const p=proof();p.placements.push({...p.placements[0],note:1,lane:1});
 const d=evidence();d.notes.push({lane:2,status:'estimated',target_seconds:10.5},{lane:3,status:'excluded',target_seconds:null});
 const [out,annotation]=annotate(doc,p,d);assert.equal(out.sections[0].combo_counts[4],1);
 assert.equal(annotation.placed.length,1);assert.equal(annotation.rule.unit,'simultaneous_timing_row');
});
test('identical observations corroborate the same value instead of increasing it',()=>{
 const d=evidence();d.combo_events.push({...d.combo_events[0]});
 const [out,annotation]=annotate(hold(null),proof(),d);assert.equal(out.sections[0].combo_counts[4],1);
 assert.equal(annotation.placed.length,1);assert.equal(annotation.placed[0].observations.length,2);
});
test('an explicitly configured exact increment overrides the ordinary timing-row rule',()=>{
 const d={...evidence(),chart_policy:{gimmick_candidates:[{id:'weighted',kind:'suspected_multi_increment',review_status:'pending',
  playback_start_seconds:10,playback_end_seconds:11,combo_increment:10}]}};
 d.combo_events[0].delta=10;const [out,annotation]=annotate(hold(null),proof(),d);
 assert.equal(out.sections[0].combo_counts[4],10);assert.deepEqual(annotation.placed[0].gimmick_candidates,['weighted']);
 d.chart_policy.gimmick_candidates[0].review_status='rejected';assert.equal(annotate(hold(null),proof(),d)[1].placed.length,0);
});
test('independent sources retain agreeing confirmed weights and discard needless Split=48',()=>{
 const a=hold(1),b=hold(null);b.sections[0].combo_counts[2]=2;
 const [out,merged]=merge(standard(hold()),[{id:'a',document:a},{id:'b',document:b}]);
 assert.equal(merged.conflicts.length,0);
 const rows=grid(out),at=t=>{const [si,ri]=rows.find(r=>r[2].number()===t);return out.sections[si].combo_counts[ri];};
 assert.equal(at(.5),1);assert.equal(at(.25),2);assert.equal(at(0),null);
 assert.ok(out.sections.every(s=>Object.fromEntries(s.directives).Split==='2'));
 const [again]=merge(standard(hold()),[{id:'a',document:a},{id:'b',document:a}]);
 const half=grid(again).find(r=>r[2].number()===.5);assert.equal(again.sections[half[0]].combo_counts[half[1]],1);
 const [dense]=merge(parse(header(48,false)+Array(192).fill('.....').join('\n')),[{id:'a',document:hold()}]);
 assert.ok(dense.sections.every(s=>Object.fromEntries(s.directives).Split==='1'));
});
test('disagreeing numeric weights remain unknown with both source claims',()=>{
 const [out,merged]=merge(standard(hold()),[{id:'a',document:hold(1)},{id:'b',document:hold(10)}]);
 const [si,ri]=grid(out).find(r=>r[2].number()===.5);assert.equal(out.sections[si].combo_counts[ri],null);
 assert.deepEqual(merged.conflicts.find(c=>c.reason==='Conflicting combo counts').claims,[{source:'a',count:1},{source:'b',count:10}]);
});
test('missing notes in one video do not erase positive observations in another',()=>{
 const a=parse(header(1,false)+'X....\n.....\n.....\n.....\n'),b=parse(header(1,false)+'.....\n.X...\n.....\n.....\n');
 const [out,merged]=merge(standard(a),[{id:'a',document:a},{id:'b',document:b}]);
 assert.equal(merged.placements.length,2);assert.equal(merged.conflicts.length,0);
 assert.equal(out.sections[0].rows[0],'X....');assert.equal(out.sections[0].rows[1],'.X...');
});
test('tap versus hold conflicts are explicit and cannot create headless holds',()=>{
 const a=hold(),b=parse(header(1,false)+'.....\nX....\n.....\n.....\n');
 const [out,merged]=merge(standard(a),[{id:'a',document:a},{id:'b',document:b}]);
 assert.ok(merged.conflicts.some(c=>c.reason==='Conflicting chart geometry'));assert.ok(out.sections.every(s=>s.rows.every(r=>r==='.....')));
 assert.throws(()=>merge(standard(a),[{id:'bad',document:parse(header()+'H....\n')}]),/Headless hold/);
});
test('current-recording placement indexes follow a merged grid without changing source identities',()=>{
 const [out]=merge(standard(hold()),[{id:'a',document:hold()}]),p=remap(out,proof()).placements[0];
 assert.equal(p.note,0);assert.equal(p.start,0);assert.equal(p.end,2);assert.equal(p.end_row,2);
});
