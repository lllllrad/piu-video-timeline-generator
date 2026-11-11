import {displaySeconds,noteGlyphSize} from '@piu/chart-editor/glyphs';
import {editReview,validateReview,type ReviewDocument,type ReviewNote} from '@piu/chart-editor';
import {chartPoint,drawChart,type ChartView} from '@piu/chart-editor/canvas';
import {installPlayer} from './player.js';
import {compareInterval} from './comparison.js';
import {inspectWindow,moveWindow,zoomWindow} from './navigation.js';

// getRandomValues is available on remote HTTP too; randomUUID requires a secure context.
function uuid(){
 const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
 const hex=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
 return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
const $=<T extends HTMLElement=HTMLElement>(id:string)=>document.getElementById(id) as T;
const input=(id:string)=>$<HTMLInputElement>(id);
const select=(id:string)=>$<HTMLSelectElement>(id);
const video=$<HTMLVideoElement>('video'),canvas=$<HTMLCanvasElement>('chart');
let meta:any,review:ReviewDocument,reviewId:string=uuid(),dirty=false,selected:string|null=null;
let observations:ReviewNote[]=[],automatic:any[]=[],rows:any[]=[],nextOffset:number|null=null;
let history:ReviewDocument[]=[],future:ReviewDocument[]=[],loop=false,generation=0,rowGeneration=0;
let selectedAuto:any=null,frameEvidence:any=null,frameRequest=0;
let lastFrameRequest=-Infinity,windowRange:[number,number]=[0,1],pageOffset=0,detailRequest=0;
let commentEditing=false;
let followRange:[number,number]|null=null,loopRange:[number,number]|null=null;
const syncPlayer=installPlayer(video,()=>meta?[meta.start_seconds,meta.end_seconds]:null,()=>loop&&loopRange?loopRange[0]:null);
let panTarget:[number,number]|null=null,panTimer:ReturnType<typeof setTimeout>|undefined;
const selection=new URLSearchParams(location.search);
function scoped(path:string){
 const url=new URL(path,location.origin);
 for(const key of ['source','segment'])if(selection.has(key))url.searchParams.set(key,selection.get(key)!);
 return url.pathname+url.search;
}
const error=(message='')=>{$('error').textContent=message;$('error').hidden=!message;};
async function api(path:string,options:RequestInit={}){
 const response=await fetch(scoped(path),options),body=await response.json();
 if(!response.ok)throw Error(body.error||`Request failed (${response.status})`);return body;
}
function guarded(work:()=>unknown){return()=>{error();Promise.resolve().then(work).catch(e=>error(e.message));};}
function coverage():[number,number]{return [...windowRange];}
function chartRange():[number,number]{return followRange??coverage();}
function stopFollow(){followRange=null;input('follow').checked=false;}
function bounds():[number,number]{return [meta.start_seconds,meta.end_seconds];}
async function showWindow(range:[number,number],panning=false){
 stopFollow();
 if(!panning){clearTimeout(panTimer);panTimer=undefined;panTarget=null;}
 input('from').value=String(range[0]);input('to').value=String(range[1]);await loadWindow();
}
function glyphSize(){return noteGlyphSize(Math.max(1,(canvas.clientWidth-64)/(meta?.layout.lanes.length??10)));}
function anchorOffset(span=coverage()[1]-coverage()[0]){return span*glyphSize()/Math.max(1,canvas.clientHeight-30);}
function syncSpacing(){
 if(!meta||!review)return;
 const span=coverage()[1]-coverage()[0],preset=[5,10,20,60].find(value=>Math.abs(value-span)<.000001);
 select('zoom').value=preset?String(preset):'custom';
 if(document.activeElement!==input('spacing'))input('spacing').value=String(Math.round((canvas.clientHeight-30)/span));
}
function panWindow(current:readonly[number,number],direction:number):[number,number]{
 const span=current[1]-current[0],time=Math.max(meta.start_seconds,Math.min(meta.end_seconds,current[0]+anchorOffset()+span*direction));
 return [time-anchorOffset(),time-anchorOffset()+span];
}
function panTo(range:[number,number]){
 stopFollow();video.pause();panTarget=range;input('chart-position').value=String(range[0]+anchorOffset(range[1]-range[0]));
 if(panTimer!==undefined)return;
 panTimer=setTimeout(guarded(async()=>{
  panTimer=undefined;const target=panTarget;if(!target)return;const run=++generation;
  followRange=target;windowRange=moveWindow(target,bounds(),0);
  input('from').value=String(windowRange[0]);input('to').value=String(windowRange[1]);
  video.currentTime=Math.max(meta.start_seconds,Math.min(meta.end_seconds,target[0]+anchorOffset()));
  syncSpacing();paint();$('load').setAttribute('aria-busy','true');
  try{await loadRows(0);if(run===generation)renderReview();}
  finally{if(run===generation)$('load').removeAttribute('aria-busy');if(panTarget===target)panTarget=null;}
 }),70);
}
function blank():ReviewDocument{
 return {schema:1,revision:0,source:{id:meta.source_id,size_bytes:meta.media.size_bytes,mtime_ns:meta.media.mtime_ns},
 analysis_fingerprint:meta.fingerprint,coverage:coverage(),status:'draft',notes:[],ticks:[],scroll:[],comment:''};
}
function view():ChartView{const [start,end]=chartRange();return {start,end,lanes:meta?.layout.lanes.length??10,
 notes:review?.notes??[],ticks:review?.ticks??[],observations:input('ghosts').checked?observations:[],selected:selected??selectedAuto?.id??null};}
function paint(){if(meta&&review)drawChart(canvas,view());updatePlayhead();}
function change(next:ReviewDocument){next.revision=review.revision;validateReview(next);history.push(structuredClone(review));future=[];review=next;dirty=true;paint();renderReview();}
function setState(){ $('save-state').textContent=dirty?'Unsaved changes':review.revision?`Saved · revision ${review.revision}`:'New draft';
 $<HTMLButtonElement>('undo').disabled=!history.length;$<HTMLButtonElement>('redo').disabled=!future.length;}
function renderReview(){
 const picker=select('manual-notes');picker.replaceChildren(new Option('New note',''));
 for(const note of review.notes)picker.add(new Option(`Lane ${note.lane+1} · ${note.kind} · ${note.start_seconds?.toFixed(3)??'censored head'} s`,note.id));
 picker.value=selected??'';
 select('status').value=review.status;$<HTMLTextAreaElement>('comment').value=review.comment;
 $('coverage').textContent=`Review coverage: ${review.coverage[0].toFixed(3)}–${review.coverage[1].toFixed(3)} s. Outside this interval is unreviewed.`;
 for(const [collection,container]of [['ticks','ticks'],['scroll','scrolls']] as const){
  const host=$(container);host.replaceChildren();
  for(const event of review[collection]){
   const row=document.createElement('div');row.className='event-row';
   const text=document.createElement('span');text.textContent=`${event.seconds.toFixed(4)} s · ${'count'in event?`weight ${event.count??'unknown'}`:`×${event.multiplier}`}`;
   const remove=document.createElement('button');remove.textContent='Remove';remove.onclick=()=>{const next=structuredClone(review);next[collection]=next[collection].filter(r=>r.id!==event.id) as any;next.status='draft';change(next);};row.append(text,remove);host.append(row);
  }
 }
 const includesTruth=windowRange[0]<=review.coverage[0]&&windowRange[1]>=review.coverage[1];
 const result=!includesTruth?'Show the review interval to compare its complete coverage.':compareInterval(review,observations);
 $('comparison').textContent=review.status==='reviewed'?result:`Draft · ${result}`;setState();
}
function showNote(n:ReviewNote|null,keepAutomatic=false){
 selected=n?.id??null;
 if(!keepAutomatic){
  selectedAuto=null;++detailRequest;$<HTMLButtonElement>('copy-auto').disabled=true;
  $('selected-evidence').textContent=n?`Manual note · ${n.id}`:'No observation selected.';
  $('detail').textContent=n?JSON.stringify(n,null,2):'Select an observation to inspect its saved evidence.';
 }
 select('manual-notes').value=selected??'';select('lane').value=String(n?.lane??0);select('kind').value=n?.kind??'tap';
 input('head').value=n?.start_seconds?.toString()??'';input('tail').value=n?.end_seconds?.toString()??'';
 $('apply-note').textContent=n?'Apply note edit':'Add note';$<HTMLButtonElement>('remove-note').disabled=!n;paint();
}
function autoNote(row:any):ReviewNote|null{
 const low=row.observed_range[0],high=row.observed_range[1];if(low==null||high==null||row.lane==null)return null;
 const target=row.status==='estimated'&&Number.isFinite(row.target_seconds)?row.target_seconds:null;
 const kind=row.note_type==='tap'&&target!==null?'tap':row.collection==='holds'?'hold':'unknown';
 return {id:row.id,lane:row.lane,kind,start_seconds:target,end_seconds:kind==='tap'?target:null,
 observed_range:[low,high],evidence:[row.id]};
}
async function loadWindow(){
 const range=inspectWindow(Number(input('from').value),Number(input('to').value),bounds());
 const [start,end]=range,run=++generation;
 $('load').setAttribute('aria-busy','true');
 try{
  if(run!==generation)return;
  const preset=[5,10,20,60].find(seconds=>Math.abs(seconds-(end-start))<.000001);
  select('zoom').value=preset?String(preset):'custom';
  windowRange=range;
  const position=input('chart-position');position.min=String(meta.start_seconds);position.max=String(meta.end_seconds);
  position.disabled=Number(position.min)===Number(position.max);position.step='any';
  if(!panTarget)position.value=String(Math.min(meta.end_seconds,start+anchorOffset()));
  position.setAttribute('aria-valuetext',`${start.toFixed(3)} to ${end.toFixed(3)} recording seconds`);
  await loadRows(0);renderReview();syncSpacing();paint();
  $<HTMLButtonElement>('previous-window').disabled=start<=meta.start_seconds;
  $<HTMLButtonElement>('next-window').disabled=end>=meta.end_seconds;
 }finally{if(run===generation)$('load').removeAttribute('aria-busy');}
}
async function chooseEvidence(row:any){
 const request=++detailRequest;selectedAuto=row;showNote(null,true);
 $<HTMLButtonElement>('copy-auto').disabled=!autoNote(row);paint();
 $('selected-evidence').textContent=`${row.id}${row.lane!=null?` · lane ${row.lane+1}`:''}`;
 $<HTMLDetailsElement>('evidence-panel').open=true;
 $('detail').textContent='Loading selected evidence…';
 if(row.observed_range[0]!==null)video.currentTime=row.observed_range[0];
 const detail=await api(`/api/detail?id=${encodeURIComponent(row.id)}`);
 if(request===detailRequest)$('detail').textContent=JSON.stringify(detail,null,2);
}
async function loadRows(offset:number){
 const run=++rowGeneration,[start,end]=coverage(),kind=select('channel').value;
 const local=kind==='notes'||kind==='holds'?automatic.filter(row=>row.collection===kind&&row.observed_range[0]<=end&&row.observed_range[1]>=start):null;
 const result=local?{rows:local.slice(offset,offset+100),total:local.length,next_offset:offset+100<local.length?offset+100:null}:await api(`/api/window?kind=${kind}&start=${start}&end=${end}&offset=${offset}&limit=100`);
 if(run!==rowGeneration)return;rows=result.rows;nextOffset=result.next_offset;pageOffset=offset;
 $<HTMLButtonElement>('less').disabled=offset===0;
 $('row-count').textContent=`${result.total} saved records · ${rows.length?offset+1:0}–${offset+rows.length}. Diagnostics may overlap.`;
 $<HTMLButtonElement>('more').disabled=nextOffset===null;const host=$('observations');host.replaceChildren();
 for(const row of rows){
  const button=document.createElement('button');button.textContent=`${row.observed_range[0]?.toFixed(3)??'Unknown time'} · ${row.reason??row.kind??row.judgment_label??row.collection}${row.lane!=null?` · lane ${row.lane+1}`:''}`;
  button.onclick=guarded(async()=>{
   host.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed','false'));button.setAttribute('aria-pressed','true');
   await chooseEvidence(row);
  });host.append(button);
 }
 if(!rows.length)host.textContent='No saved observations in this interval.';
}
async function listReviews(){
 const list=await api('/api/reviews');const picker=select('reviews');picker.replaceChildren(new Option('New interval',''));
 for(const item of list)picker.add(new Option(`${item.coverage[0].toFixed(2)}–${item.coverage[1].toFixed(2)} s · ${item.status}${item.stale?' · stale analysis':''}`,item.id));
 picker.value=review.revision?reviewId:'';
}
function updatePlayhead(){
 if(!meta)return;syncPlayer();const [start,end]=chartRange(),head=$('playhead'),fraction=(video.currentTime-start)/(end-start);
 head.style.display=fraction>=0&&fraction<=1?'block':'none';head.style.top=`${30+fraction*(canvas.clientHeight-30)}px`;
 $('chart-window').textContent=`Chart ${start.toFixed(3)}–${end.toFixed(3)} s${input('follow').checked?' · following playback':''}`;
 $('clock').textContent=`Recording ${video.currentTime.toFixed(3)} s${frameEvidence?` · nearest observed ${frameEvidence.time.toFixed(3)} s · PTS ${frameEvidence.source_pts}`:''}`;
 drawOverlay();

}
function drawOverlay(){
 const overlay=$<HTMLCanvasElement>('overlay'),context=overlay.getContext('2d');if(!context)return;
 overlay.width=video.clientWidth;overlay.height=video.clientHeight;context.clearRect(0,0,overlay.width,overlay.height);
 if(!frameEvidence||Math.abs(frameEvidence.time-video.currentTime)>.1||!video.videoWidth)return;
 const scale=Math.min(overlay.width/video.videoWidth,overlay.height/video.videoHeight),ox=(overlay.width-video.videoWidth*scale)/2,oy=(overlay.height-video.videoHeight*scale)/2;
 const [rx,ry,rw,rh]=meta.game_roi;context.strokeStyle='#b6ff59';context.lineWidth=1.5;
 for(const point of frameEvidence.motion??[]){
  const [lane,x,y]=point;if(!Number.isFinite(x)||!Number.isFinite(y))continue;
  context.strokeRect(ox+(rx+x*rw)*scale-6,oy+(ry+y*rh)*scale-6,12,12);
 }
}
async function refreshFrame(){
 const request=++frameRequest,time=video.currentTime;
 const evidence=await api(`/api/frame?time=${time}`);if(request!==frameRequest)return;frameEvidence=evidence;
 const states=evidence?.receptors?.[0]??[],active=states.flatMap((state:any,i:number)=>state===true||state==='active'?[i+1]:[]);
 $('channels').textContent=evidence?`Popup: ${evidence.popup?.[2]??'unreadable'} · combo: ${evidence.popup?.[0]??'unknown'} · active receptor lanes: ${states.length?(active.join(', ')||'none'):'unavailable'} · motion: ${evidence.motion_total??0} saved detections`:'No nearby saved source frame.';
 updatePlayhead();
}
function updateFollowing(){
 if(!meta||!review||!input('follow').checked)return;
 const span=coverage()[1]-coverage()[0],offset=anchorOffset(span),start=video.currentTime-offset;
 followRange=[start,start+span];windowRange=moveWindow(followRange,bounds(),0);
 for(const [id,value]of [['from',windowRange[0]],['to',windowRange[1]]] as const)if(document.activeElement!==input(id))input(id).value=value.toFixed(6);
 input('chart-position').value=String(video.currentTime);
 drawChart(canvas,view());
}
function trackPlayback(){
 if(video.paused)return;
 if(loop&&loopRange&&video.currentTime>=loopRange[1])video.currentTime=loopRange[0];
 updateFollowing();
 if(Math.abs(video.currentTime-lastFrameRequest)>.2){lastFrameRequest=video.currentTime;void refreshFrame().catch(e=>error(e.message));}
 updatePlayhead();if(!video.paused)requestAnimationFrame(trackPlayback);
}
async function boot(){
 const library=await api('/api/library'),sources=library.sources as {id:string;segments:{number:number;song:string|null;chart:string|null}[]}[];
 if(!sources.length)throw Error('No prepared plays available. Run play analysis first.');
 const sourcePicker=select('source-picker'),segmentPicker=select('segment-picker');
 for(const source of sources)sourcePicker.add(new Option(`${source.id} · ${source.segments.length} plays`,source.id));
 sourcePicker.value=selection.get('source')??library.default_source;
 if(!sourcePicker.value)sourcePicker.value=sources[0].id;
 const fillSegments=()=>{
  segmentPicker.replaceChildren();
  const source=sources.find(item=>item.id===sourcePicker.value)!;
  for(const play of source.segments)segmentPicker.add(new Option(`${play.number} · ${play.song??'Unknown song'} · ${play.chart??'Unknown chart'}`,String(play.number)));
 };
 fillSegments();
 segmentPicker.value=selection.get('segment')??(sourcePicker.value===library.default_source?String(library.default_segment):segmentPicker.value);
 if(!segmentPicker.value)segmentPicker.selectedIndex=0;
 sourcePicker.onchange=fillSegments;
 $('open-play').onclick=()=>{
  const query=new URLSearchParams({source:sourcePicker.value,segment:segmentPicker.value});
  if(query.get('source')!==selection.get('source')||query.get('segment')!==selection.get('segment'))location.assign('/?'+query);
 };
 $('play-picker').removeAttribute('inert');
 selection.set('source',sourcePicker.value);selection.set('segment',segmentPicker.value);
 window.history.replaceState(null,'','/?'+selection);
 $<HTMLAnchorElement>('full-evidence').href=scoped('/artifact?path=report-data.json');
 $<HTMLAnchorElement>('report-link').href=scoped('/report.html');

 meta=await api('/api/meta');
 video.src=scoped('/media');video.currentTime=meta.start_seconds;
 const chart=await api('/api/chart');automatic=chart.rows;observations=automatic.map(autoNote).filter((n):n is ReviewNote=>n!==null);
 $('title').textContent=`${meta.song??'Unknown song'} · ${meta.chart??'Unknown chart'}`;
 $('subtitle').textContent=`Segment ${meta.segment_number??''} · source-bound interval review`;
 input('from').value=String(meta.start_seconds);input('to').value=String(Math.min(meta.end_seconds,meta.start_seconds+Math.min(10,displaySeconds(Math.max(1,canvas.clientHeight-30),160))));
 for(let lane=0;lane<meta.layout.lanes.length;lane++)select('lane').add(new Option(`${lane+1} · ${['DL','UL','C','UR','DR'][lane%5]}`,String(lane)));
 windowRange=[Number(input('from').value),Number(input('to').value)];
 review=blank();showNote(null);await listReviews();await loadWindow();video.currentTime=coverage()[0];
 document.querySelectorAll('[inert]').forEach(element=>element.removeAttribute('inert'));document.body.setAttribute('aria-busy','false');
}
for(const id of ['from','to'])input(id).onfocus=()=>{stopFollow();video.pause();};
$('load').onclick=guarded(()=>{stopFollow();clearTimeout(panTimer);panTimer=undefined;panTarget=null;return loadWindow();});
$('at-playhead').onclick=guarded(()=>showWindow(zoomWindow(video.currentTime,coverage()[1]-coverage()[0],bounds())));
$('previous-window').onclick=guarded(()=>showWindow(moveWindow(coverage(),bounds(),-1)));
$('next-window').onclick=guarded(()=>showWindow(moveWindow(coverage(),bounds(),1)));
input('spacing').onchange=guarded(()=>{
 const pixels=Number(input('spacing').value);
 if(!Number.isFinite(pixels)||pixels<20||pixels>1000)throw Error('Choose note spacing from 20 to 1000 pixels per second.');
 const span=Math.min(meta.end_seconds-meta.start_seconds,120,displaySeconds(Math.max(1,canvas.clientHeight-30),pixels));
 const time=Math.max(meta.start_seconds,Math.min(meta.end_seconds,video.currentTime)),start=time-anchorOffset(span),range:[number,number]=[start,start+span];
 if(input('follow').checked){
  windowRange=moveWindow(range,bounds(),0);updateFollowing();syncSpacing();paint();renderReview();
 }else panTo(range);
});
select('zoom').onchange=guarded(()=>showWindow(zoomWindow((coverage()[0]+coverage()[1])/2,Number(select('zoom').value),bounds())));
$('review-window').onclick=guarded(()=>showWindow(review.coverage));
$('new').onclick=guarded(()=>{if(dirty&&!confirm('Discard unsaved review changes?'))return;reviewId=uuid();review=blank();history=[];future=[];dirty=false;showNote(null);renderReview();});
select('reviews').onchange=guarded(async()=>{
 if(dirty&&!confirm('Discard unsaved review changes?')){select('reviews').value=review.revision?reviewId:'';return;}
 if(!select('reviews').value){select('reviews').value=review.revision?reviewId:'';return;}
 const id=select('reviews').value,loaded=await api(`/api/review?id=${id}`);reviewId=id;review=loaded;dirty=false;history=[];future=[];
 input('from').value=String(review.coverage[0]);input('to').value=String(review.coverage[1]);showNote(null);await loadWindow();
 if(review.analysis_fingerprint!==meta.fingerprint)error('This review belongs to an older analysis. Its truth is preserved; saving requires explicit evidence reconciliation.');
});
$('save').onclick=guarded(async()=>{
 const button=$<HTMLButtonElement>('save'),submitted=review,identity=reviewId;button.disabled=true;
 try{
  validateReview(submitted);
  const saved=await api(`/api/review?id=${identity}`,{method:'PUT',headers:{'Content-Type':'application/json','X-Review-Token':meta.write_token},body:JSON.stringify({base_revision:submitted.revision,document:submitted})});
  if(reviewId===identity){
   if(review===submitted){review=saved;dirty=false;}
   else{review={...review,revision:saved.revision};dirty=true;}
   renderReview();
  }
  await listReviews();
 }finally{button.disabled=false;}
});
select('status').onchange=()=>{const next=structuredClone(review);next.status=select('status').value as 'draft'|'reviewed';change(next);};
$<HTMLTextAreaElement>('comment').oninput=()=>{
 if(!commentEditing){history.push(structuredClone(review));future=[];commentEditing=true;}
 review={...review,comment:$<HTMLTextAreaElement>('comment').value};dirty=true;setState();
};
$<HTMLTextAreaElement>('comment').onblur=()=>{commentEditing=false;};
$('new-note').onclick=()=>showNote(null);
select('manual-notes').onchange=()=>showNote(review.notes.find(n=>n.id===select('manual-notes').value)??null);
$('note-form').onsubmit=e=>{e.preventDefault();guarded(()=>{
 const start=input('head').value===''?null:Number(input('head').value),kind=select('kind').value as ReviewNote['kind'];
 const end=kind==='tap'?start:input('tail').value===''?null:Number(input('tail').value);
 const existing=review.notes.find(n=>n.id===selected),range: [number,number]=[start??review.coverage[0],end??review.coverage[1]];
 const note:ReviewNote={id:existing?.id??uuid(),lane:Number(select('lane').value),kind,start_seconds:start,end_seconds:end,observed_range:range,evidence:existing?.evidence??[]};
 change(editReview(review,{kind:'put-note',note}));showNote(note);
 })();};
$('remove-note').onclick=guarded(()=>{if(!selected)return;change(editReview(review,{kind:'remove-note',id:selected}));showNote(null);});
$('copy-auto').onclick=guarded(()=>{
 const note=autoNote(selectedAuto);if(!note)return;note.id=uuid();
 note.observed_range=[Math.max(review.coverage[0],note.observed_range[0]),Math.min(review.coverage[1],note.observed_range[1])];
 if(note.start_seconds!==null&&(note.start_seconds<review.coverage[0]||note.start_seconds>=review.coverage[1]))note.start_seconds=null;
 change(editReview(review,{kind:'put-note',note}));showNote(note);
});
for(const kind of ['tick','scroll'] as const)$(kind+'-form').onsubmit=e=>{e.preventDefault();guarded(()=>{
 const next=structuredClone(review),seconds=Number(input(kind+'-time').value),id=uuid();next.status='draft';
 if(kind==='tick')next.ticks.push({id,seconds,count:input('tick-count').value===''?null:Number(input('tick-count').value),evidence:[]});
 else next.scroll.push({id,seconds,multiplier:Number(input('scroll-ratio').value),evidence:[]});change(next);
 })();};
$('undo').onclick=()=>{if(!history.length)return;future.push(review);review={...history.pop()!,revision:review.revision};dirty=true;showNote(null);renderReview();};
$('redo').onclick=()=>{if(!future.length)return;history.push(review);review={...future.pop()!,revision:review.revision};dirty=true;showNote(null);renderReview();};
$('loop').onclick=()=>{loop=!loop;loopRange=loop?coverage():null;$('loop').setAttribute('aria-pressed',String(loop));$('loop').textContent=`Loop interval: ${loop?'on':'off'}`;};
input('ghosts').onchange=paint;select('channel').onchange=guarded(()=>loadRows(0));$('more').onclick=guarded(()=>loadRows(nextOffset??0));$('less').onclick=guarded(()=>loadRows(Math.max(0,pageOffset-100)));
canvas.onclick=e=>{guarded(async()=>{
 const point=chartPoint(canvas,view(),e.clientX,e.clientY);if(!point)return;
 const hit=review.notes.filter(n=>n.lane===point.lane).find(n=>Math.abs((n.start_seconds??n.observed_range[0])-point.seconds)<(coverage()[1]-coverage()[0])*.02||n.kind==='hold'&&point.seconds>=(n.start_seconds??n.observed_range[0])&&point.seconds<=(n.end_seconds??n.observed_range[1]));
 if(hit){showNote(hit);return;}
 const automaticHit=input('ghosts').checked&&observations.filter(n=>n.lane===point.lane).find(n=>Math.abs((n.start_seconds??n.observed_range[0])-point.seconds)<(coverage()[1]-coverage()[0])*.015||n.kind==='hold'&&point.seconds>=n.observed_range[0]&&point.seconds<=n.observed_range[1]);
 if(!e.shiftKey&&automaticHit){await chooseEvidence(automatic.find(row=>row.id===automaticHit.id));return;}
 if(e.shiftKey){const note:ReviewNote={id:uuid(),lane:point.lane,kind:'tap',start_seconds:point.seconds,end_seconds:point.seconds,observed_range:[point.seconds,point.seconds],evidence:[]};change(editReview(review,{kind:'put-note',note}));showNote(note);}else{selectedAuto=null;showNote(null);video.currentTime=point.seconds;select('lane').value=String(point.lane);input('head').value=String(point.seconds);}
 })();};
input('follow').onchange=()=>{if(input('follow').checked){updateFollowing();updatePlayhead();}else{followRange=null;paint();}};
video.onclick=()=>$('play-toggle').click();
input('chart-position').oninput=()=>{
 const span=coverage()[1]-coverage()[0],start=Number(input('chart-position').value)-anchorOffset();
 panTo([start,start+span]);
};
canvas.addEventListener('wheel',e=>{
 if(!meta||!review||e.ctrlKey||e.metaKey||!e.deltaY)return;
 e.preventDefault();
 const height=canvas.getBoundingClientRect().height,current=panTarget??chartRange();
 const pixels=e.deltaMode===1?e.deltaY*16:e.deltaMode===2?e.deltaY*height:e.deltaY;
 panTo(panWindow(current,pixels/height));
},{passive:false});
canvas.onkeydown=e=>{if(e.key==='PageDown'||e.key==='PageUp'){e.preventDefault();panTo(panWindow(panTarget??chartRange(),e.key==='PageDown'?1:-1));return;}if(e.key==='Delete'&&selected){e.preventDefault();$('remove-note').click();}};
for(const [id,direction]of [['frame-back',-1],['frame-next',1]] as const)$(id).onclick=guarded(async()=>{
 video.pause();
 const low=Math.max(meta.start_seconds,video.currentTime-1),high=Math.min(meta.end_seconds,video.currentTime+1);
 const result=await api(`/api/window?kind=frames&start=${low}&end=${high}&limit=500`);
 const times=result.rows.map((r:any)=>r.time??r.playback_seconds).filter((t:any)=>typeof t==='number'&&(direction>0?t>video.currentTime+.000001:t<video.currentTime-.000001)).sort((a:number,b:number)=>a-b);
 if(times.length)video.currentTime=direction>0?times[0]:times.at(-1);
});
$('play-toggle').onclick=guarded(async()=>{if(video.paused){if(video.currentTime>=meta.end_seconds||video.currentTime<meta.start_seconds)video.currentTime=meta.start_seconds;if(loop&&loopRange&&(video.currentTime<loopRange[0]||video.currentTime>=loopRange[1]))video.currentTime=loopRange[0];await video.play();}else video.pause();});
video.onpause=()=>{$('play-toggle').textContent='Play';if(meta&&review){void loadRows(0).catch(e=>error(e.message));renderReview();}};
video.onplay=()=>{clearTimeout(panTimer);panTimer=undefined;panTarget=null;input('follow').checked=true;$('play-toggle').textContent='Pause';trackPlayback();};video.ontimeupdate=updatePlayhead;video.onseeking=updatePlayhead;video.onseeked=guarded(async()=>{updateFollowing();updatePlayhead();await refreshFrame();});
video.onerror=()=>error('The browser cannot decode this original recording. Try a browser with support for its codec; the source is never transcoded.');
new ResizeObserver(()=>{syncSpacing();paint();}).observe(canvas);
window.addEventListener('keydown',e=>{
 if(!meta||!review||e.defaultPrevented)return;
 const target=e.target as HTMLElement,editing=target.closest('input,textarea,select,[contenteditable=true]');
 const command=e.ctrlKey||e.metaKey;
 if(command&&e.key.toLowerCase()==='s'){e.preventDefault();if(editing)target.blur();$('save').click();return;}
 if(editing||target.closest('button,summary,video')||e.altKey)return;
 let action:string|undefined;
 if(command&&e.key.toLowerCase()==='z')action=e.shiftKey?'redo':'undo';
 else if(!command&&e.code==='Space')action='play-toggle';
 else if(!command&&e.key==='ArrowLeft')action=e.shiftKey?'previous-window':'frame-back';
 else if(!command&&e.key==='ArrowRight')action=e.shiftKey?'next-window':'frame-next';
 if(action){e.preventDefault();if(!e.repeat)$(action).click();}
});
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
guarded(boot)();
