/** Source-bound channel reader. No inference, media decoder or Python dependency. */
import {readFileSync, statSync, existsSync} from 'node:fs';
import {resolve, sep} from 'node:path';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';
import {parseData} from '../json.ts';

export function manifest(directory: string,{notes=true}={}) {
  const value=parseData(readFileSync(resolve(directory,'manifest.json'),'utf8'));
  if(value.schema!==1 || value.contract?.format?.schema!==1 || value.contract?.format?.rgb_encoding!=='planar_green_difference_temporal_delta_v1')throw new Error('Unsupported observation bundle');
  const source=value.contract.source, media=source.media, stat=statSync(media.path,{bigint:true});
  if(stat.size!==BigInt(media.size_bytes) || stat.mtimeNs!==BigInt(media.mtime_ns))throw new Error('Original observation source changed');
  let count=0;
  for(const chunk of value.chunks){
    if(chunk.first_frame!==count || !Number.isSafeInteger(chunk.frames) || chunk.frames<1)throw new Error('Observation timeline has a gap');
    count+=chunk.frames;
  }
  if(count!==value.frame_count || !count)throw new Error('Incomplete observation bundle');
  const notesPath=resolve(directory,'notes/manifest.json');
  if(notes && existsSync(notesPath)){
    const stage=parseData(readFileSync(notesPath,'utf8'));
    const identity=createHash('sha256').update(readFileSync(resolve(directory,'manifest.json'))).digest('hex');
    if(stage.schema!==1 || stage.contract?.pixels?.sha256!==identity || stage.frame_count!==count || stage.chunks.length!==value.chunks.length)throw new Error('Note stage differs from acquired pixels');
    value.notes_stage=stage;
    value.channels.notes={status:'available',artifact:'notes/manifest.json',detector:stage.contract.detector};
  }
  return value;
}

function bytes(directory,chunk,suffix){
  const names=Object.keys(chunk.files).filter(n=>n.endsWith('.'+suffix));
  if(names.length!==1)throw new Error('Missing or ambiguous channel chunk');
  const path=resolve(directory,names[0]);
  if(!path.startsWith(resolve(directory)+sep))throw new Error('Observation chunk escapes bundle');
  const raw=readFileSync(path), identity=chunk.files[names[0]];
  if(raw.length!==identity.size_bytes || createHash('sha256').update(raw).digest('hex')!==identity.sha256)throw new Error('Corrupt observation channel');
  return gunzipSync(raw);
}

function* rgbFrames(raw:Buffer,count:number,width:number,height:number){
  const plane=width*height, size=plane*3;
  if(raw.length!==count*size)throw new Error('Observation RGB shape differs');
  let prior=null;
  for(let frame=0;frame<count;frame++){
    const color=Buffer.from(raw.subarray(frame*size,(frame+1)*size));
    if(prior)for(let i=0;i<size;i++)color[i]=(color[i]+prior[i])&255;
    const rgb=Buffer.allocUnsafe(size);
    for(let p=0;p<plane;p++){
      const green=color[plane+p];
      rgb[p*3]=(color[p]+green)&255;rgb[p*3+1]=green;rgb[p*3+2]=(color[plane*2+p]+green)&255;
    }
    prior=color;yield rgb;
  }
}

export function* frames(directory: string,{pixels=false,channel='all',gamePixels=false}={}){
  const saved=manifest(directory,{notes:channel==='all'||channel==='notes'}), source=saved.contract.source;
  let index=0, previous=null;
  for(const chunk of saved.chunks){
    const records=bytes(directory,chunk,'frames.jsonl.gz').toString('utf8').trim().split('\n').map(l=>JSON.parse(l));
    if(records.length!==chunk.frames)throw new Error('Observation frame count differs');
    const selected=channel==='all'?(saved.notes_stage?['notes']:[]):['timeline','input','popup','processing'].includes(channel)?[]:[channel];
    for(const name of selected){
      if(name!=='notes')throw new Error('Unknown observation channel');
      if(!saved.notes_stage)throw new Error('Note detection has not been acquired');
      const noteChunk=saved.notes_stage.chunks[saved.chunks.indexOf(chunk)];
      const extra=bytes(resolve(directory,'notes'),noteChunk,name+'.jsonl.gz').toString('utf8').trim().split('\n').map(l=>JSON.parse(l));
      if(extra.length!==records.length || extra.some((r,i)=>['frame','source_pts_seconds','playback_seconds'].some(k=>r[k]!==records[i][k])))throw new Error('Channel timeline differs');
      for(let i=0;i<records.length;i++)Object.assign(records[i],extra[i]);
    }
    const inputs=pixels?bytes(directory,chunk,'input.rgb.gz'):null, popups=pixels?bytes(directory,chunk,'popup.rgb.gz'):null;
    const geometry=saved.geometry;
    const inputSize=(geometry.input[2]-geometry.input[0])*(geometry.input[3]-geometry.input[1])*3;
    const popupSize=(geometry.popup[2]-geometry.popup[0])*(geometry.popup[3]-geometry.popup[1])*3;
    if(pixels && (inputs.length!==inputSize*chunk.frames || popups.length!==popupSize*chunk.frames))throw new Error('Observation RGB shape differs');
    const game=gamePixels?bytes(directory,chunk,'game.rgb.gz'):null;
    const gameSize=source.width*source.height*3;
    if(game && game.length!==gameSize*chunk.frames)throw new Error('Full-game RGB shape differs');
    const gameFrames=game?rgbFrames(game,chunk.frames,source.width,source.height):null;
    const inputFrames=inputs?rgbFrames(inputs,chunk.frames,geometry.input[2]-geometry.input[0],geometry.input[3]-geometry.input[1]):null;
    const popupFrames=popups?rgbFrames(popups,chunk.frames,geometry.popup[2]-geometry.popup[0],geometry.popup[3]-geometry.popup[1]):null;
    for(let i=0;i<records.length;i++){
      const frame=records[i], pts=frame.source_pts_seconds, time=frame.playback_seconds;
      if(frame.frame!==index++ || !Number.isFinite(pts) || !Number.isFinite(time) || previous && (pts<=previous.pts || time<=previous.time) || Math.abs(pts-source.media.container_start_seconds-time)>1e-6)throw new Error('Invalid original observation timestamp');
      previous={pts,time};
      yield {...frame,...(gamePixels?{game_rgb:gameFrames.next().value}:{}),
        ...(pixels?{input_rgb:inputFrames.next().value,popup_rgb:popupFrames.next().value}:{})};
    }
  }
}

export function* spatialMasks(directory: string){
  const saved=manifest(directory,{notes:false}), geometry=saved.masks;
  const stride=geometry.fields.length*geometry.height*Math.ceil(geometry.width/8);
  for(const chunk of saved.chunks){
    const data=bytes(directory,chunk,'masks.bin.gz');
    if(data.length!==stride*chunk.frames)throw new Error('Observation mask shape differs');
    for(let i=0;i<chunk.frames;i++)yield {frame:chunk.first_frame+i,geometry,packed:data.subarray(i*stride,(i+1)*stride)};
  }
}
