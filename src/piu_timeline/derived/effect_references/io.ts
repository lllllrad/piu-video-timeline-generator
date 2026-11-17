import {readFileSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {createHash} from 'node:crypto';
import {deflateSync} from 'node:zlib';
import {parseData} from '../json.ts';
import type {Capture,Patch} from './model.ts';
export function load(path:string):{capture:Capture;manifest:any} {
  const manifest=parseData(readFileSync(path,'utf8'));
  if(manifest.schema!==1)throw new Error('Unsupported capture schema');
  const pixels=readFileSync(resolve(dirname(path),'pixels.rgb'));
  const exclusions=readFileSync(resolve(dirname(path),'exclusions.bin'));
  for(const [data,key] of [[pixels,'pixels_sha256'],[exclusions,'exclusions_sha256']] as const)
    if(createHash('sha256').update(data).digest('hex')!==manifest[key])throw new Error('Capture hash mismatch');
  if(pixels.length!==exclusions.length*3||exclusions.length%(47*47))throw new Error('Invalid RGB dimensions');
  for(const e of manifest.events) {
    if(!e.frames.length||!Number.isFinite(e.marker)||!Number.isInteger(e.kind)||e.kind<0||e.kind>4)throw new Error('Invalid event');
    let last=-Infinity;
    for(const f of e.frames) {
      if(!Number.isInteger(f.offset)||f.offset<0||(f.offset+1)*47*47>exclusions.length||!Number.isFinite(f.pts)||!Number.isFinite(f.time)||f.pts<=last)throw new Error('Invalid frame timeline or offset');
      last=f.pts;
    }
  }
  return {capture:{events:manifest.events,pixels,exclusions},manifest};
}
function crc(bytes:Uint8Array) {
  let c=0xffffffff;
  for(const b of bytes){c^=b;for(let j=0;j<8;j++)c=c&1?(c>>>1)^0xedb88320:c>>>1;}
  return (c^0xffffffff)>>>0;
}
function chunk(name:string,bytes:Uint8Array) {
  const body=Buffer.concat([Buffer.from(name),bytes]), header=Buffer.alloc(4),sum=Buffer.alloc(4);
  header.writeUInt32BE(bytes.length);sum.writeUInt32BE(crc(body));return Buffer.concat([header,body,sum]);
}
/** Exact RGB PNG; unsupported pixels are diagnostic checkerboard, never hidden artwork. */
export function png(path:string,p:Patch) {
  const raw=Buffer.alloc(39*(1+39*3));
  for(let y=0;y<39;y++)for(let x=0;x<39;x++)for(let c=0;c<3;c++) {
    const i=y*39+x;raw[y*118+1+x*3+c]=p.visible[i]?p.rgb[i*3+c]:((Math.floor(x/4)+Math.floor(y/4))%2?60:100);
  }
  const header=Buffer.alloc(13);header.writeUInt32BE(39,0);header.writeUInt32BE(39,4);header[8]=8;header[9]=2;
  writeFileSync(path,Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',deflateSync(raw)),chunk('IEND',Buffer.alloc(0))]));
}
export const hash=(path:string)=>createHash('sha256').update(readFileSync(path)).digest('hex');
