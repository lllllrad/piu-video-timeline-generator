import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {associate,key} from '../../../src/piu_timeline/derived/charts/localized.ts';

const source={url:'https://official.example/song-list.pdf',sha256:'a'.repeat(64)};
const songs=[{index:'CS101',title:'Example Song'},{index:'CS102',title:'Example Song - SHORT CUT -'},
 {index:'CS103',title:'Example Song - FULL SONG -'}];
const row=(type='NORMAL')=>({page:1,type,title:'Example Song',localized_title:'예시 곡'});
test('official bilingual rows preserve chart variants and normalize OCR spacing',()=>{
 const r=associate(songs,[row(),row('SHORT'),row('FULL')],{},source);
 assert.equal(r.aliases[key('예 시 곡')].index,'CS101');
 assert.equal(r.aliases[key('예시 곡 - SHORT CUT -')].index,'CS102');
 assert.equal(r.aliases[key('예시 곡 - FULL SONG -')].index,'CS103');
 assert.equal(r.added,3);assert.deepEqual(r.conflicts,[]);
 assert.equal(r.aliases[key('예시 곡')].pdf_sha256,source.sha256);
 assert.equal(r.aliases[key('예시 곡')].official_title,'Example Song');
});
test('duplicate official names, absent names and conflicting aliases never select a code',()=>{
 const ambiguous=associate([...songs,{index:'CS104',title:'Example Song'}],[row()],{},source);
 assert.deepEqual(ambiguous.aliases,{});assert.equal(ambiguous.unresolved[0].reason,'ambiguous_official_title');
 assert.deepEqual(associate([], [row()],{},source).aliases,{});
 const human={title:'예시 곡',index:'CS999',basis:'explicit_assignment'};
 const r=associate(songs,[row()],{[key(human.title)]:human},source);
 assert.deepEqual(r.aliases[key(human.title)],human);assert.equal(r.conflicts.length,1);
});
test('multiple official rows cannot assign one localized name to different identities',()=>{
 const r=associate([...songs,{index:'CS104',title:'Other Song'}],[row(),{...row(),title:'Other Song'}],{},source);
 assert.deepEqual(r.aliases,{});assert.equal(r.conflicts.length,1);
});
test('official PDF adapter joins wrapped titles and excludes neighboring headings and levels',()=>{
 const pages=[[[55,100,'FULL'],[82,100,'160'],[120,100,'작곡자'],[176,102,'예시 곡 - FULL'],
  [220,97,'SONG -'],[300,100,'Artist'],[354,102,'Example Song - FULL'],[400,97,'SONG -'],
  [500,100,'24'],[224,80,'곡명'],[55,60,'NORMAL'],[220,60,'다음 곡'],[396,60,'Next Song']]];
 const script='import json,sys; from piu_timeline.charts.localized import cells; print(json.dumps(cells(json.load(sys.stdin))))';
 const rows=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{input:JSON.stringify(pages),encoding:'utf8'}));
 assert.deepEqual(rows,[{page:1,type:'FULL',localized_title:'예시 곡 - FULL SONG -',title:'Example Song - FULL SONG -'},
  {page:1,type:'NORMAL',localized_title:'다음 곡',title:'Next Song'}]);
});
