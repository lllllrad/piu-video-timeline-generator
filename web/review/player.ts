/** Recording controls use the original media clock and ordinary browser media APIs. */
export function installPlayer(video:HTMLVideoElement,getBounds:()=>readonly[number,number]|null,getLoopStart:()=>number|null=()=>null):()=>void{
 const element=<T extends HTMLElement>(id:string)=>document.getElementById(id) as T;
 const seek=element<HTMLInputElement>('video-seek'),volume=element<HTMLInputElement>('volume');
 const speed=element<HTMLSelectElement>('playback-rate'),mute=element<HTMLButtonElement>('mute');
 const status=element('player-state'),container=element('player');
 const format=(seconds:number)=>{
  if(!Number.isFinite(seconds))return '—';
  const hours=Math.floor(seconds/3600),minutes=Math.floor(seconds/60)%60,rest=(seconds%60).toFixed(3).padStart(6,'0');
  return `${hours?hours+':':''}${String(minutes).padStart(2,'0')}:${rest}`;
 };
 let scrubbing=false,boundaryTimer:ReturnType<typeof setTimeout>|undefined;
 const limits=()=>{const range=getBounds();return range?[range[0],Math.min(range[1],Number.isFinite(video.duration)?video.duration:range[1])] as const:null;};
 const clamp=(time:number)=>{const range=limits();return range?Math.max(range[0],Math.min(range[1],time)):time;};
 const finish=():void=>{
  const range=limits();if(!range)return;
  const loopStart=getLoopStart();
  if(loopStart!==null&&!video.paused){video.currentTime=clamp(loopStart);scheduleBoundary();return;}
  video.pause();if(video.currentTime!==range[1])video.currentTime=range[1];status.textContent='End of segment';
 };
 const enforce=()=>{
  const range=limits();if(!range)return;
  if(video.currentTime<range[0])video.currentTime=range[0];
  if(video.currentTime>=range[1])finish();
 };
 const scheduleBoundary=():void=>{
  clearTimeout(boundaryTimer);const range=limits();if(!range||video.paused||video.seeking||video.readyState<3)return;
  boundaryTimer=setTimeout(finish,Math.max(0,(range[1]-video.currentTime)/video.playbackRate*1000));
 };
 const sync=()=>{
  const range=limits();seek.disabled=!range||!Number.isFinite(video.duration);
  seek.min=String(range?.[0]??0);seek.max=String(range?.[1]??1);
  enforce();
  if(!scrubbing)seek.value=String(video.currentTime);
  seek.setAttribute('aria-valuetext',`${format(video.currentTime)}; segment ${format(range?.[0]??0)} to ${format(range?.[1]??0)}`);
  element('player-time').textContent=`${format(video.currentTime)} · ${format(range?.[0]??0)}–${format(range?.[1]??0)}`;
  volume.value=String(video.muted?0:video.volume);mute.textContent=video.muted?'Unmute':'Mute';
  mute.setAttribute('aria-pressed',String(video.muted));speed.value=String(video.playbackRate);
 };
 seek.oninput=()=>{scrubbing=true;video.currentTime=clamp(Number(seek.value));sync();};
 seek.onchange=()=>{scrubbing=false;sync();};seek.onblur=()=>{scrubbing=false;sync();};
 volume.oninput=()=>{video.volume=Number(volume.value);video.muted=video.volume===0;sync();};
 mute.onclick=()=>{video.muted=!video.muted;sync();};speed.onchange=()=>{video.playbackRate=Number(speed.value);};
 element('fullscreen').onclick=async()=>{
  try{if(document.fullscreenElement)await document.exitFullscreen();else await container.requestFullscreen();}
  catch{status.textContent='Fullscreen is unavailable in this browser.';}
 };
 document.addEventListener('fullscreenchange',()=>{element('fullscreen').textContent=document.fullscreenElement?'Exit fullscreen':'Fullscreen';});
 for(const event of ['timeupdate','durationchange','loadedmetadata','seeking','seeked','volumechange','ratechange','play','pause'])video.addEventListener(event,sync);
 for(const event of ['play','seeking','seeked','ratechange','pause','playing'])video.addEventListener(event,scheduleBoundary);
 video.addEventListener('waiting',()=>{clearTimeout(boundaryTimer);status.textContent='Buffering recording…';});
 video.addEventListener('seeking',()=>{status.textContent='Seeking recording…';});
 video.addEventListener('canplay',()=>{status.textContent='Ready';});
 video.addEventListener('seeked',()=>{status.textContent=video.paused?'Paused':'Playing';});
 video.addEventListener('playing',()=>{status.textContent='Playing';});
 video.addEventListener('pause',()=>{status.textContent='Paused';});
 video.addEventListener('ended',()=>{status.textContent='End of segment';});
 video.addEventListener('error',()=>{status.textContent='Recording could not be loaded. Check the error above.';});
 sync();return sync;
}
