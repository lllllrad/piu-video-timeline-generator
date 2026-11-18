/** Read-only shared RGB; one independent cue window per task. */
import {parentPort,workerData} from 'node:worker_threads';
import {measure} from './play_measure.ts';
const {capture,bank}=workerData;
parentPort.on('message',({index,event})=>{
 try {parentPort.postMessage({index,result:measure(capture,bank,event)});}
 catch(error) {throw error;}
});
