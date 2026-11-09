/** Preserve exact integer provenance without a source-context tree per property. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync}from 'node:child_process';
import {parseData,stringifyData}from '../../../src/piu_timeline/derived/json.ts';
test('unsafe integer tokens stay exact without confusing strings, keys or exponents',()=>{
 const text=String.raw`{"stamp":1794198683330348765,"negative":-9007199254740992,"safe":9007199254740991,"decimal":9007199254740992.0,"exponent":1e20,"quoted":"1794198683330348765","\\escaped\"":"line\\end","nul":"\u0000integer:0","nuls":"\u0000\u0000integer:0","duplicate":12345678901234567,"duplicate":2,"__proto__":{"stamp":1794198683330348765}}`;
 const result=parseData(text);
 assert.equal(result.stamp,1794198683330348765n);assert.equal(result.negative,-9007199254740992n);
 assert.equal(result.safe,9007199254740991);assert.equal(result.decimal,9007199254740992);
 assert.equal(result.exponent,1e20);assert.equal(result.quoted,'1794198683330348765');
 assert.equal(result.nul,'\0integer:0');assert.equal(result.nuls,'\0\0integer:0');assert.equal(result.duplicate,2);
 assert.deepEqual(result.__proto__,{stamp:1794198683330348765n});
 assert.deepEqual(parseData(stringifyData(result)),{...result,decimal:9007199254740992n,exponent:100000000000000000000n});
 assert.equal(parseData('9007199254740992'),9007199254740992n);
 for(const invalid of ['1e400','{"x":1e400}','{"x":9007199254740992,}','[NaN]','{9007199254740992:0}','{9007199254740992 \n :0}'])assert.throws(()=>parseData(invalid));
});
test('large ordinary records parse under a bounded heap while retaining exact stamps',()=>{
 const url=new URL('../../../src/piu_timeline/derived/json.ts',import.meta.url).href;
 const code=`import {parseData}from ${JSON.stringify(url)};
 const text='{"stamp":1794198683330348765,"records":['+Array(150000).fill('{"a":1,"b":2,"c":3}').join(',')+']}';
 const result=parseData(text);
 if(result.records.length!==150000||result.stamp!==1794198683330348765n)throw Error('Lost records or provenance');
 console.log('ok');`;
 assert.equal(execFileSync(process.execPath,['--max-old-space-size=64','--input-type=module','-e',code],{encoding:'utf8'}).trim(),'ok');
});
