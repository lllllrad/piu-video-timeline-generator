/** Bounded RGB residual regions: possible foreign imagery, never certified opacity. */
import type {Patch} from './model.ts';
export function regions(query:Patch,reference:Patch) {
 const tiles=[];
 for(let y=0;y<39;y+=6)for(let x=0;x<39;x+=6) {
  const pixels=[];let error=0;
  for(let yy=y;yy<Math.min(y+6,39);yy++)for(let xx=x;xx<Math.min(x+6,39);xx++) {
   const i=yy*39+xx;if(!query.visible[i]||!reference.visible[i])continue;
   pixels.push(i);for(let c=0;c<3;c++)error+=Math.abs(query.rgb[i*3+c]-reference.rgb[i*3+c]);
  }
  if(pixels.length>=9)tiles.push({box:[x,y,Math.min(39,x+6),Math.min(39,y+6)],pixels,error:error/(pixels.length*3*255)});
 }
 const errors=tiles.map(t=>t.error).sort((a,b)=>a-b),typical=errors[Math.floor(errors.length/2)]??1;
 const candidates=tiles.filter(t=>t.error>Math.max(.18,typical*2+.03)).sort((a,b)=>b.error-a.error);
 const visible=query.visible.slice(),removed=[];let count=0;
 for(const t of candidates) {
  // Never explain away broad phase/appearance disagreement as overlap.
  if(count+t.pixels.length>39*39*.20)continue;
  count+=t.pixels.length;for(const i of t.pixels)visible[i]=0;
  removed.push({box:t.box,rgb_error:t.error,pixels:t.pixels.length});
 }
 return {patch:{...query,visible,imageOutliers:removed},removed};
}
