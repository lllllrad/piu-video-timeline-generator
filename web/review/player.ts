/** Recording controls use the original media clock and ordinary browser media APIs. */
export function installPlayer(video:HTMLVideoElement):()=>void{
 const element=<T extends HTMLElement>(id:string)=>document.getElementById(id) as T;
 const seek=element<HTMLInputElement>('video-seek'),volume=element<HTMLInputElement>('volume');
 const speed=element<HTMLSelectElement>('playback-rate'),mute=element<HTMLButtonElement>('mute');
 const status=element('player-state'),container=element('player');
 const format=(seconds:number)=>{
  if(!Number.isFinite(seconds))return '—';
  const hours=Math.floor(seconds/3600),minutes=Math.floor(seconds/60)%60,rest=(seconds%60).toFixed(3).padStart(6,'0');
  return `${hours?hours+':':''}${String(minutes).padStart(2,'0')}:${rest}`;
 };
 let scrubbing=false;
 const sync=()=>{
  seek.disabled=!Number.isFinite(video.duration);seek.max=String(Number.isFinite(video.duration)?video.duration:1);
  if(!scrubbing)seek.value=String(video.currentTime);
  seek.setAttribute('aria-valuetext',`${format(video.currentTime)} of ${format(video.duration)}`);
  element('player-time').textContent=`${format(video.currentTime)} / ${format(video.duration)}`;
  volume.value=String(video.muted?0:video.volume);mute.textContent=video.muted?'Unmute':'Mute';
  mute.setAttribute('aria-pressed',String(video.muted));speed.value=String(video.playbackRate);
 };
 seek.oninput=()=>{scrubbing=true;video.currentTime=Number(seek.value);sync();};
 seek.onchange=()=>{scrubbing=false;sync();};seek.onblur=()=>{scrubbing=false;sync();};
 volume.oninput=()=>{video.volume=Number(volume.value);video.muted=video.volume===0;sync();};
 mute.onclick=()=>{video.muted=!video.muted;sync();};speed.onchange=()=>{video.playbackRate=Number(speed.value);};
 element('fullscreen').onclick=async()=>{
  try{if(document.fullscreenElement)await document.exitFullscreen();else await container.requestFullscreen();}
  catch{status.textContent='Fullscreen is unavailable in this browser.';}
 };
 document.addEventListener('fullscreenchange',()=>{element('fullscreen').textContent=document.fullscreenElement?'Exit fullscreen':'Fullscreen';});
 for(const event of ['timeupdate','durationchange','loadedmetadata','seeking','seeked','volumechange','ratechange','play','pause'])video.addEventListener(event,sync);
 video.addEventListener('waiting',()=>{status.textContent='Buffering recording…';});
 video.addEventListener('seeking',()=>{status.textContent='Seeking recording…';});
 video.addEventListener('canplay',()=>{status.textContent='Ready';});
 video.addEventListener('seeked',()=>{status.textContent=video.paused?'Paused':'Playing';});
 video.addEventListener('playing',()=>{status.textContent='Playing';});
 video.addEventListener('pause',()=>{status.textContent='Paused';});
 video.addEventListener('ended',()=>{status.textContent='End of recording';});
 video.addEventListener('error',()=>{status.textContent='Recording could not be loaded. Check the error above.';});
 sync();return sync;
}
