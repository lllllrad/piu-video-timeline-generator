// @ts-check
'use strict';
// Shared selection changes only on explicit navigation; playback retains every row.
function inspectorElement(id){return document.getElementById(id)}
const inspectorTabs=['chart','channels','analysis','ucs','warnings','data'];
let inspectorNavigating=false;
let inspectorReady=false,activeInspectorTab='chart',evidenceAnchor=null,evidenceLane=null,selectedWarning=null;
const inspectorWarnings=[];
let warningLimit=50,inspectorFrame=-1;
function selectInspectorTab(name,focus=false){
  if(!inspectorTabs.includes(name))return;
  activeInspectorTab=name;
  if(name!=='chart')cancelChartAnimation();
  for(const tab of inspectorTabs){
    inspectorElement('panel-'+tab).hidden=tab!==name;
    inspectorElement('tab-'+tab).setAttribute('aria-selected',String(tab===name));
    inspectorElement('tab-'+tab).setAttribute('tabindex',tab===name?'0':'-1');
  }
  if(focus)inspectorElement('tab-'+name).focus();
  if(name==='chart'){if(data.notes[selectedNote]?.status==='excluded')$('excluded').checked=true;chartScene=null;draw()}
  if(name==='channels'){renderEvidence(selectedNote);updateInspectorFrame(playhead,true);renderFrameTracks()}
  if(name==='analysis')renderDerivation();
  if(name==='ucs')renderUcsSelection();
  if(name==='warnings')renderInspectorWarnings();
}
function inspectAt(time,note=null,lane=null,tab='channels',warning=null){
  if(!Number.isFinite(time))return;
  selectedWarning=warning;evidenceAnchor=time;evidenceLane=lane;
  if(note===null)selectedNote=null;
  inspectorNavigating=true;
  try{seek(time,-1,note)}finally{inspectorNavigating=false}
  selectInspectorTab(tab);
}
function warningTime(record){
  for(const value of [record.visible_start_seconds,record.playback_seconds,record.playback_start_seconds,record.lower_seconds,record.target_seconds])if(Number.isFinite(value))return value;
  return null;
}
function collectInspectorWarnings(){
  const seen=new Map();
  const sources=[['exclusion_diagnostics',data.exclusion_diagnostics],['recognition_diagnostics',data.recognition_diagnostics],
    ['visibility_diagnostics',data.visibility_diagnostics],['beat_timing',data.beat_timing],['timing_reconstruction',data.timing_reconstruction],['head_registration',data.head_registration]];
  for(const [source,bundle] of sources)for(const record of bundle?.warnings||[]){
    const key=JSON.stringify([record.reason,record.note,record.hold,record.lane,warningTime(record),record.visible_end_seconds,record.failure_detail]);
    let item=seen.get(key);
    if(!item){item={record,origins:[],records:[],id:inspectorWarnings.length};inspectorWarnings.push(item);seen.set(key,item)}
    item.origins.push(source);item.records.push({source,record});
  }
  $('warningCount').textContent=String(inspectorWarnings.length);
}
function warningNote(record){
  if(Number.isInteger(record.note)&&data.notes[record.note])return record.note;
  const hold=holdById.get(record.hold);return hold?.display_note??null;
}
function renderInspectorWarnings(){
  const query=$('warningSearch').value.toLowerCase(),scoped=$('warningScope').value==='selected';
  const list=inspectorWarnings.filter(item=>(!scoped||selectedNote!==null&&warningNote(item.record)===selectedNote)&&
    (!query||(JSON.stringify(item.records)+(warningNote(item.record)===null?'':' note '+(warningNote(item.record)+1))+(item.record.lane==null?'':' lane '+(item.record.lane+1))).toLowerCase().includes(query)));
  $('warningSummary').textContent=list.length+' cases / '+inspectorWarnings.length+' total · showing '+Math.min(warningLimit,list.length)+'. Related diagnostic copies are grouped; all original records remain available.';
  const root=$('warningRows');root.replaceChildren();
  for(const item of list.slice(0,warningLimit)){
    const record=item.record,note=warningNote(record),time=warningTime(record),card=text('article','',root);card.className='warning-card';
    text('h3',(record.reason||'Unspecified warning').replaceAll('_',' '),card);
    text('p',(time===null?'No recording time supplied':fmt(time)+(Number.isFinite(record.visible_end_seconds)?' … '+fmt(record.visible_end_seconds):''))+
      (record.lane!=null?' · lane '+(record.lane+1):'')+(note!==null?' · note #'+(note+1):'')+' · '+item.origins.join(', '),card);
    const actions=text('div','',card);actions.className='row';
    const jump=tab=>{inspectAt(time,note,record.lane??null,tab,item.id)};
    if(time!==null){text('button','Video + channels',actions).onclick=()=>jump('channels');text('button','Derived data',actions).onclick=()=>jump('analysis');text('button','Note chart',actions).onclick=()=>jump('chart')}
    const details=text('details','',card);text('summary','Diagnostic records',details);text('pre',JSON.stringify(item.records,null,2),details);
  }
  $('moreWarnings').hidden=warningLimit>=list.length;
}
function refreshInspector(){
  if(!inspectorReady)return;
  const note=data.notes[selectedNote],name=note?'#'+(selectedNote+1)+' · lane '+(note.lane+1)+' · '+(note.note_type||note.type_status||'type unconfirmed'):'No note selected';
  $('selectionLabel').textContent=name+(selectedWarning!==null?' · warning '+(selectedWarning+1):'');
  $('inspectNote').value=selectedNote===null?'':String(selectedNote);
  if(activeInspectorTab==='analysis')renderDerivation();
  if(activeInspectorTab==='ucs')renderUcsSelection();
  if(activeInspectorTab==='warnings'&&$('warningScope').value==='selected')renderInspectorWarnings();
  updateInspectorFrame(playhead,true);
  if(activeInspectorTab==='channels')renderFrameTracks();
}
function nearestInspectorFrame(time){
  const frames=data.visual_channels?.timeline?.frames||[];
  let lo=0,hi=frames.length;
  while(lo<hi){const mid=(lo+hi)>>>1;if(frames[mid][0]<time)lo=mid+1;else hi=mid}
  if(!frames.length)return -1;
  if(lo===frames.length)return lo-1;
  return lo>0&&time-frames[lo-1][0]<=frames[lo][0]-time?lo-1:lo;
}
function updateInspectorFrame(time,force=false){
  if(!inspectorReady)return;
  const timeline=data.visual_channels?.timeline?.frames||[];
  if(frameOverlay)frameOverlay.root.style.visibility=timeline.length&&time>=timeline[0][0]&&time<=timeline.at(-1)[0]?'visible':'hidden';
  const index=nearestInspectorFrame(time);if(!force&&index===inspectorFrame)return;
  inspectorFrame=index;
  if(index<0){$('framePosition').textContent='No retained channel timeline. Original video remains available.';return}
  const channel=data.visual_channels,frame=channel.timeline.frames[index],popup=channel.popup?.observations?.[index],receptors=channel.receptors?.observations?.[index];
  const lane=evidenceLane??data.notes[selectedNote]?.lane;
  $('framePosition').textContent='Captured frame '+index+' · recording '+fmt(frame[0])+' · source PTS '+Number(frame[1]).toFixed(6)+' · playback distance '+Math.round(Math.abs(time-frame[0])*1000)+' ms';
  $('snapshot-popup').textContent=popup?'Combo '+(popup[0]??'unknown')+' · judgment '+(popup[2]||(popup[4]?'blank':'unknown')):'Popup unavailable';
  const state=receptors?.[0]?.[lane];
  $('snapshot-receptors').textContent=lane==null?'All lanes · inspect a lane for receptor state':'Lane '+(lane+1)+' · receptor '+(state===true?'on':state===false?'off':'unknown')+(receptors?.[2]?' · common flash':'');
  $('snapshot-motion').textContent=(channel.motion?.observations?.[index]?.length??0)+' detected heads · '+(channel.processing?.body_observations?.[index]?.length??0)+' bodies';
  $('snapshot-processing').textContent='Processing is a separate pixel observation; inspect its samples in Channel observations.';
  renderFrameOverlay(index);
  if(activeInspectorTab==='channels')$('frameData').textContent=JSON.stringify({frame_index:index,recording_seconds:frame[0],source_pts_seconds:frame[1],
    popup:popup??null,receptors:receptors??null,motion:channel.motion?.observations?.[index]??null,bodies:channel.processing?.body_observations?.[index]??null},null,2);
}
function renderFrameTracks(){
  const root=$('frameTracks');root.replaceChildren();
  const frames=data.visual_channels?.timeline?.frames||[],index=nearestInspectorFrame(evidenceAnchor??playhead),frame=frames[index];
  if(!frame){$('frameTrackSummary').textContent='No retained source frame.';return}
  const records=[];
  data.notes.forEach((note,noteIndex)=>{const point=(note.points||[]).find(p=>Math.abs(p[0]-frame[0])<1e-6);if(point)records.push({note,noteIndex,point})});
  $('frameTrackSummary').textContent='Recording '+fmt(frame[0])+' / source PTS '+Number(frame[1]).toFixed(6)+' · '+records.length+' tracks with an explicit position at this captured time. Links use recorded track membership, not a nearby target or input.';
  for(const {note,noteIndex,point} of records){text('button','#'+(noteIndex+1)+' / lane '+(note.lane+1)+' / y '+point[1].toFixed(1)+' / '+note.status,root).onclick=()=>inspectAt(frame[0],noteIndex,note.lane,'analysis',selectedWarning)}
}
function initializeInspector(){
  for(const [i,tab] of inspectorTabs.entries()){
    const button=inspectorElement('tab-'+tab);button.onclick=()=>selectInspectorTab(tab);
    button.onkeydown=event=>{let target=null;if(event.key==='ArrowRight')target=(i+1)%inspectorTabs.length;if(event.key==='ArrowLeft')target=(i+inspectorTabs.length-1)%inspectorTabs.length;if(event.key==='Home')target=0;if(event.key==='End')target=inspectorTabs.length-1;
      if(target!==null){event.preventDefault();selectInspectorTab(inspectorTabs[target],true)}};
  }
  text('option','No note / frame only',$('inspectNote')).setAttribute('value','');
  data.notes.forEach((note,index)=>{const option=text('option','#'+(index+1)+' · lane '+(note.lane+1)+' · '+note.status+(Number.isFinite(note.target_seconds)?' · '+fmt(note.target_seconds):' · '+(note.reason||'no target')),$('inspectNote'));option.setAttribute('value',String(index))});
  $('inspectNote').onchange=()=>{const index=$('inspectNote').value===''?null:Number($('inspectNote').value),note=data.notes[index];selectedWarning=null;evidenceAnchor=null;evidenceLane=null;
    if(note)seek(note.target_seconds??note.points?.[0]?.[0]??playhead,-1,index);else{selectedNote=null;draw();refreshInspector()}};
  $('followTime').onclick=()=>inspectAt(playhead,selectedNote,data.notes[selectedNote]?.lane??null);
  for(const [id,step] of [['framePrevious',-1],['frameNext',1]])inspectorElement(id).onclick=()=>{
    const frames=data.visual_channels?.timeline?.frames||[],index=Math.max(0,Math.min(frames.length-1,nearestInspectorFrame(playhead)+Number(step)));
    if(frames[index])inspectAt(frames[index][0],selectedNote,evidenceLane??data.notes[selectedNote]?.lane??null,'channels',selectedWarning);
  };
  $('warningSearch').oninput=$('warningScope').onchange=()=>{warningLimit=50;renderInspectorWarnings()};
  $('moreWarnings').onclick=()=>{warningLimit+=50;renderInspectorWarnings()};
  collectInspectorWarnings();initializeProvenance();initializeFrameOverlay();inspectorReady=true;refreshInspector();
}
