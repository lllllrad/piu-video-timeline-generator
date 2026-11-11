/** Inspection windows do not change reviewed coverage or source timestamps. */
export function inspectWindow(start:number,end:number,bounds:readonly[number,number]):[number,number]{
 if(![start,end,...bounds].every(Number.isFinite)||start<bounds[0]||end>bounds[1]||start>=end||end-start>120)
  throw Error('Choose an interval inside this play, up to 120 seconds.');
 return [start,end];
}
export function moveWindow(current:readonly[number,number],bounds:readonly[number,number],direction:number):[number,number]{
 const span=current[1]-current[0],start=Math.max(bounds[0],Math.min(bounds[1]-span,current[0]+span*direction));
 return [start,start+span];
}
export function zoomWindow(center:number,seconds:number,bounds:readonly[number,number]):[number,number]{
 const span=Math.min(seconds,bounds[1]-bounds[0]);
 if(!Number.isFinite(center)||!Number.isFinite(span)||span<=0||span>120)throw Error('Invalid inspection zoom.');
 const start=Math.max(bounds[0],Math.min(bounds[1]-span,center-span/2));
 return [start,start+span];
}
