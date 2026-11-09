import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync,statSync,renameSync,mkdirSync}from 'node:fs';
import {tmpdir}from 'node:os';
import {join}from 'node:path';
import {definition,lookup,run,identity}from '../../../src/piu_timeline/derived/pipeline/serialized.ts';

test('saved stage reuse reads upstream identities without rebuilding or rewriting its serialized input',()=>{
 const root=mkdtempSync(join(tmpdir(),'piu-serialized-'));
 try{
  writeFileSync(join(root,'upstream.json'),'{"value":3}');
  writeFileSync(join(root,'example-input.json'),'{"value":3}');
  const bind=()=>definition(root,'example','producer-1',{units:'seconds'},['upstream.json']);
  assert.equal(lookup(root,bind()),null);
  const first=run(root,bind(),input=>({value:input.value*2})),stamp=statSync(join(root,'example-input.json'),{bigint:true}).mtimeNs;
  assert.deepEqual(JSON.parse(readFileSync(first.path,'utf8')),{value:6});
  assert.deepEqual(run(root,bind(),()=>{throw Error('Cached stage must not recompute');}),first);
  assert.equal(statSync(join(root,'example-input.json'),{bigint:true}).mtimeNs,stamp);
  writeFileSync(join(root,'upstream.json'),'{"value":4}');
  assert.equal(lookup(root,bind()),null,'changed producer bytes invalidate dependent output');
  writeFileSync(join(root,'example-input.json'),'{"value":4}');
  const second=run(root,bind(),input=>({value:input.value*2}));
  assert.deepEqual(JSON.parse(readFileSync(second.path,'utf8')),{value:8});
  writeFileSync(second.path,'{"value":9}');
  assert.throws(()=>lookup(root,bind()),/Corrupt serialized stage output/);
 }finally{rmSync(root,{recursive:true,force:true});}
});

test('serialized stages reject input mutation and changed producer contracts',()=>{
 const root=mkdtempSync(join(tmpdir(),'piu-serialized-'));
 try{
  writeFileSync(join(root,'upstream.json'),'{}');writeFileSync(join(root,'example-input.json'),'{}');
  const bind=definition(root,'example','producer-1',{},['upstream.json']);
  assert.throws(()=>run(root,bind,()=>{writeFileSync(join(root,'upstream.json'),'{"changed":true}');return {};}),/changed during/);
  const next=definition(root,'example','producer-1',{},['upstream.json']);run(root,next,()=>({}));
  assert.equal(lookup(root,{...next,producer:'producer-2'}),null);
  writeFileSync(join(root,'example-input.json'),'{"changed":true}');
  assert.throws(()=>lookup(root,next),/Corrupt serialized stage input/);
  assert.throws(()=>definition(root,'example','producer-1',{},['../elsewhere']),/Invalid upstream/);
 }finally{rmSync(root,{recursive:true,force:true});}
});


test('serialized identities survive segment promotion, including a prefix across read blocks',()=>{
 const root=mkdtempSync(join(tmpdir(),'piu-promoted-')),old=join(root,'pending'),next=join(root,'final');
 try{
  mkdirSync(old);const prefix=JSON.stringify(old+'/').slice(0,-1),
   offset=JSON.stringify({text:'',path:old+'/evidence/proof.json'}).indexOf(prefix),
   text='x'.repeat(1024*1024-5-offset),encoded=JSON.stringify({text,path:old+'/evidence/proof.json'});
  assert.equal(encoded.indexOf(prefix),1024*1024-5);
  writeFileSync(join(old,'upstream.json'),encoded);
  const before=identity(join(old,'upstream.json'),old);
  writeFileSync(join(old,'example-input.json'),JSON.stringify({path:old+'/proof.json'}));
  run(old,definition(old,'example','producer',{},['upstream.json']),input=>input);
  renameSync(old,next);
  const moved=readFileSync(join(next,'upstream.json'),'utf8').replaceAll(old+'/',next+'/');
  writeFileSync(join(next,'upstream.json'),moved);
  assert.deepEqual(identity(join(next,'upstream.json'),next),before);
  for(const name of ['example-input.json','example-output.json']){
   const file=join(next,name);writeFileSync(file,readFileSync(file,'utf8').replaceAll(old+'/',next+'/'));
  }
  assert.ok(lookup(next,definition(next,'example','producer',{},['upstream.json'])));
 }finally{rmSync(root,{recursive:true,force:true});}
});
