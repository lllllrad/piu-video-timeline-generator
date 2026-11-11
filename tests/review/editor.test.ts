import test from 'node:test';
import assert from 'node:assert/strict';
import {editReview,validateReview,ucsLosses,type ReviewDocument} from '@piu/chart-editor';
import {compareInterval} from '../../web/review/comparison.ts';

const document=():ReviewDocument=>({schema:1,revision:0,source:{id:'generated',size_bytes:10,mtime_ns:'9007199254740999'},analysis_fingerprint:'generated',coverage:[10,20],status:'draft',notes:[],ticks:[],scroll:[],comment:''});
test('independent nonuniform weighted ticks and censored holds survive editing without UCS assumptions',()=>{
 const d=document();d.ticks=[{id:'a',seconds:10.1,count:3,evidence:[]},{id:'b',seconds:10.35,count:null,evidence:[]}];d.scroll=[{id:'stop',seconds:12,multiplier:0,evidence:[]}];
 const next=editReview(d,{kind:'put-note',note:{id:'hold',lane:2,kind:'hold',start_seconds:null,end_seconds:15,observed_range:[10,15],evidence:[]}});
 assert.equal(d.notes.length,0);assert.deepEqual(next.ticks,d.ticks);assert.equal(next.notes[0].start_seconds,null);assert.equal(ucsLosses(next).length,3);
 const invalid=structuredClone(next);invalid.ticks[0].seconds=21;assert.throws(()=>validateReview(invalid),/tick/);
});
test('interval comparison excludes automatic targets outside reviewed coverage and never scores censored heads',()=>{
 const d=document();d.status='reviewed';d.notes=[{id:'tap',lane:0,kind:'tap',start_seconds:10,end_seconds:10,observed_range:[10,10],evidence:[]},{id:'censored',lane:1,kind:'hold',start_seconds:null,end_seconds:12,observed_range:[10,12],evidence:[]}];
 const wrong={...d.notes[0],id:'outside',start_seconds:9.99,end_seconds:9.99};
 assert.match(compareInterval(d,[wrong]),/0\/1 known heads matched/);
 assert.match(compareInterval(d,[{...wrong,id:'inside',start_seconds:10,end_seconds:10}]),/1\/1 known heads matched/);
});

import {inspectWindow,moveWindow,zoomWindow} from '../../web/review/navigation.ts';
test('inspection navigation clamps to original play bounds without changing reviewed coverage',()=>{
 const truth=document(),before=structuredClone(truth);
 assert.deepEqual(moveWindow([12,17],[10,30],-1),[10,15]);
 assert.deepEqual(moveWindow([25,30],[10,30],1),[25,30]);
 assert.deepEqual(zoomWindow(29,5,[10,30]),[25,30]);
 assert.deepEqual(zoomWindow(10,60,[10,30]),[10,30]);
 assert.throws(()=>inspectWindow(9,15,[10,30]),/inside this play/);
 assert.throws(()=>inspectWindow(0,121,[0,200]),/120 seconds/);
 assert.deepEqual(truth,before);
});
