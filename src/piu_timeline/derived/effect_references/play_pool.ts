/** Bounded pool with ordered results and shared immutable pixel bytes. */
import {availableParallelism} from 'node:os';
import {Worker} from 'node:worker_threads';
import {measure} from './play_measure.ts';
export function workers() {
 const count=Number(process.env.PIU_EFFECT_JOBS??process.env.PIU_SKIN_JOBS??Math.min(8,availableParallelism()));
 if(!Number.isInteger(count)||count<1||count>32)throw new Error('PIU_EFFECT_JOBS must be an integer from 1 to 32');
 return count;
}
function shared(bytes:Uint8Array) {
 const result=new Uint8Array(new SharedArrayBuffer(bytes.byteLength));result.set(bytes);return result;
}
export async function measureWindows(capture,bank,jobs=workers()) {
 if(!Number.isInteger(jobs)||jobs<1||jobs>32)throw new Error('Effect workers must be 1..32');
 if(jobs===1||capture.events.length<2)return capture.events.map(event=>measure(capture,bank,event));
 const input={pixels:shared(capture.pixels),exclusions:shared(capture.exclusions)};
 const results=new Array(capture.events.length),pool:Worker[]=[];
 let next=0,finished=0;
 try {
  await new Promise<void>((resolve,reject)=>{
   const dispatch=worker=>{
    if(next<capture.events.length) {const index=next++;worker.postMessage({index,event:capture.events[index]});}
   };
   for(let i=0;i<Math.min(jobs,capture.events.length);i++) {
    const worker=new Worker(new URL('./play_worker.ts',import.meta.url),{workerData:{capture:input,bank}});pool.push(worker);
    worker.on('error',reject);
    worker.on('exit',code=>{if(finished<results.length)reject(new Error(`Effect worker exited before completion (${code})`));});
    worker.on('message',({index,result})=>{
     results[index]=result;finished++;
     if(finished===results.length)resolve();else dispatch(worker);
    });
    dispatch(worker);
   }
  });
  return results;
 }finally {await Promise.all(pool.map(worker=>worker.terminate()));}
}
