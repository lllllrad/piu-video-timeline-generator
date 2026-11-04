import {imageHoldScene} from '../fixtures.ts';

/** Two independently typed caps with positive body tiles outside one foreground word. */
export function occludedHold(scale=1,fps=60,continueAfterHead=false){
 const s=imageHoldScene(scale,fps),speed=continueAfterHead?800:Math.min(600,40*fps/3);
 const times=Array.from({length:continueAfterHead?16:4},(_,i)=>i/fps);
 s.data.layout.combo_roi=[.7,.8,.14,.075];s.data.layout.judgment_roi=[.05,.4,.1,.25];
 s.data.notes.forEach((n,i)=>Object.assign(n,{points:[],target_seconds:((i?260:80)-15)/speed,
  velocity_pixels_per_second:-speed*scale}));
 s.references.hold_body=[[0,8*scale]];
 s.native=times.map(time=>{
  const head=80-speed*time,tail=head+180,images=[];
  const cap=(role:string,y:number,index:number)=>{
   if(y<32||y-(index?25:10)<195&&y+(index?10:25)>120)return;
   images.push({lane:0,x:.1,y:y/300,role,template:role,skin:'synthetic',classification_status:'full_pattern',
    region_errors:{cap:0,connection:0},bounds_pixels:[10*scale,(y-(index?25:10))*scale,30*scale,(y+(index?10:25))*scale]});
   s.data.notes[index].points.push([time,y*scale]);
  };
  cap('hold_start',head,0);cap('hold_end',tail,1);
  for(let y=Math.ceil(Math.max(26,head+15));y+8<=tail-10;y+=1){
   if(y<195&&y+8>120)continue;
   images.push({lane:0,x:.1,y:(y+4)/300,role:'hold_body',template:'hold_body',skin:'synthetic',classification_status:'full_pattern',
    region_errors:{body:0},bounds_pixels:[16*scale,y*scale,24*scale,(y+8)*scale]});
  }
  return {playback_seconds:time,source_pts_seconds:80+time,skin_observations:images};
 });
 return s;
}
