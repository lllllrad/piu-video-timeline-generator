import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync}from 'node:fs';
import {tmpdir}from 'node:os';
import {join}from 'node:path';
import {execFileSync}from 'node:child_process';
import {render,renderFile}from '../../../src/piu_timeline/derived/report.ts';

test('file rendering preserves UTF-8, escaping and template-looking user text across chunk boundaries',()=>{
 const directory=mkdtempSync(join(tmpdir(),'piu-render-'));
 try{
  const input=join(directory,'input.json'),output=join(directory,'report.html');
  const data=JSON.stringify({caption:'a'.repeat(65525)+'🙂한글</script>&__DATA__'});
  writeFileSync(input,data);renderFile(input,output,'__DATA__<&','D20','source?x=<y>&');
  assert.equal(readFileSync(output,'utf8'),render(data,'__DATA__<&','D20','source?x=<y>&'));
  assert.throws(()=>renderFile(input,output,'song','D20','source'));
 }finally{rmSync(directory,{recursive:true,force:true});}
});

test('prepared JSON larger than the worker heap renders without constructing one large string',()=>{
 const directory=mkdtempSync(join(tmpdir(),'piu-render-'));
 try{
  const url=new URL('../../../src/piu_timeline/derived/report.ts',import.meta.url).href;
  const code=`import{openSync,writeSync,closeSync,statSync}from'node:fs';
  import{renderFile}from ${JSON.stringify(url)};
  const input=${JSON.stringify(join(directory,'input.json'))},output=${JSON.stringify(join(directory,'report.html'))};
  const fd=openSync(input,'wx'),chunk='a'.repeat(1024*1024);writeSync(fd,'["');
  for(let i=0;i<64;i++)writeSync(fd,chunk);writeSync(fd,'"]');closeSync(fd);
  renderFile(input,output,'song','D20','source');
  if(statSync(output).size<=64*1024*1024)throw Error('Incomplete HTML');console.log('ok');`;
  assert.equal(execFileSync(process.execPath,['--max-old-space-size=32','--input-type=module','-e',code],{encoding:'utf8'}).trim(),'ok');
 }finally{rmSync(directory,{recursive:true,force:true});}
});
