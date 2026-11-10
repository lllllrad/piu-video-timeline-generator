/** Execute one persisted timing producer; only a segment directory crosses the CLI. */
import {resolve}from 'node:path';
import {save as coordinates,view as coordinateView}from '../stages/coordinate_files.ts';
import {physical,native,view as physicalView}from '../stages/timing_files.ts';
import {prepare,calculate,view}from '../beats/files.ts';
const stages={coordinates,'coordinate-view':coordinateView,'physical-timing':physical,'physical-view':physicalView,
 'native-timing':native,'beat-input':prepare,'musical-timing':calculate,'timed-view':view};
export function run(stage:string,directory:string){
 if(!Object.hasOwn(stages,stage))throw Error(`Unknown persisted timing stage: ${stage}`);
 return stages[stage](directory);
}
if(process.argv[1]&&resolve(process.argv[1])===resolve(import.meta.filename)){
 try{
  if(process.argv.length!==4)throw Error('Usage: derive-file STAGE SEGMENT_DIRECTORY');
  process.stdout.write(JSON.stringify(run(process.argv[2],process.argv[3]))+'\n');
 }catch(error){process.stderr.write(`Timing stage failed: ${error.message}\n`);process.exitCode=1;}
}
