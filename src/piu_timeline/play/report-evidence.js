// @ts-check
'use strict';
// Retained native observations. Playback moves only the cursor, never the rows.
let evidenceScene=null;
function updateEvidenceCursor(time){
  if(!evidenceScene)return;
  const x=evidenceScene.x(time),visible=time>=evidenceScene.lo&&time<=evidenceScene.hi;
  evidenceScene.cursor.setAttribute('visibility',visible?'visible':'hidden');
  evidenceScene.cursor.setAttribute('x1',x);evidenceScene.cursor.setAttribute('x2',x);
}
function renderEvidence(noteIndex){
  const channel=data.visual_channels,selectedRecord=data.notes[noteIndex],panel=$('nativeEvidence');
  const anchor=evidenceAnchor??selectedRecord?.target_seconds??selectedRecord?.points?.[0]?.[0]??playhead;
  const note={target_seconds:anchor,lane:evidenceLane??selectedRecord?.lane??null};
  if(!channel?.timeline){panel.hidden=false;$('evidenceSummary').textContent='No retained channel timeline is available.';return}
  panel.hidden=false;
  const control=$('evidenceWindow'),span=Number(control.value)||.6,key=noteIndex+':'+span+':'+anchor+':'+note.lane;
  if(evidenceScene?.key===key){updateEvidenceCursor(playhead);return}
  control.onchange=()=>{evidenceScene=null;renderEvidence(selectedNote)};
  const lo=note.target_seconds-span,hi=note.target_seconds+span,x=t=>180+1000*(t-lo)/(hi-lo);
  const root=svgRoot('evidenceTimeline',1200,280),rows=$('evidenceFrames');rows.replaceChildren();
  const processing=channel.processing?.notes?.find(e=>e.note===noteIndex),states=new Map((processing?.samples||[]).map(s=>[s.time.toFixed(6),s]));
  const riskFrames=new Map((channel.motion?.hold_risk?.frames||[]).map(f=>[f.playback_seconds.toFixed(6),f.causes]));
  const known=state=>state===true?'on':state===false?'off':'unknown';
  const color=state=>state==='present'||state===true?'#9cddbe':state==='absent'||state===false?'#ff8e9b':'#99a5ae';
  const confidence=value=>Number.isFinite(value)?Number(value).toFixed(2):'?';
  const height=data.analysis_height||1,receptor=(data.layout.receptor_y||0)*height;
  const bodyScale=height/(channel.processing?.pixel_coordinates?.height||height);
  $('evidenceSummary').textContent=(selectedRecord?'Note '+(noteIndex+1):'Frame review')+' / '+(note.lane===null?'all lanes':'lane '+(note.lane+1))+' · Processing: '+(processing?processing.status+' / '+processing.reason:'unavailable')+(processing?.range?' / '+formatRange(processing.range):'')+(processing?.visibility_loss?' / Visibility loss (processing unconfirmed): '+formatRange(processing.visibility_loss.range):'')
    +(processing?.motion_basis?' / Motion basis: '+processing.motion_basis:'')+'. Positions use the '+(data.analysis_width||'?')+'×'+height+' game crop, with y increasing downward. Click a frame to inspect its original timestamp.';
  /** @type {[string, number][]} */
  const channelRows=[['Popup',45],['Receptor effect',105],['Moving heads',165],['Note processing',225]];
  for(const [name,y] of channelRows){
    label(root,name,4,y+4);line(root,180,y,1180,y,'#314448');
  }
  for(const t of [lo,note.target_seconds,hi]){
    const px=x(t);line(root,px,14,px,245,t===note.target_seconds?'#b6ff59':'#314448');label(root,fmt(t),Math.min(1110,px-35),267);
  }
  function marker(time,y,fill,description){
    const mark=document.createElementNS('http://www.w3.org/2000/svg','circle');
    for(const [k,v] of Object.entries({cx:x(time),cy:y,r:3,fill}))mark.setAttribute(k,v);
    const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=description;mark.appendChild(title);
    mark.onclick=()=>seek(time,-1,noteIndex);root.appendChild(mark);
  }
  const observations=[];
  for(let i=0;i<channel.timeline.frames.length;i++){
    const [time,pts]=channel.timeline.frames[i];if(time<lo||time>hi)continue;
    const popup=channel.popup?.observations?.[i]||[],effect=channel.receptors?.observations?.[i]||[[],[]],motion=channel.motion?.observations?.[i]||[],sample=states.get(time.toFixed(6));
    const bodies=(channel.processing?.body_observations?.[i]||[]).filter(b=>note.lane===null||b[0]===note.lane);
    const bodyText=bodies.map(b=>'body '+Number(b[1]*bodyScale).toFixed(1)+'…'+Number(b[2]*bodyScale).toFixed(1)+' px'+(!b[3]?' / head clipped':'')+(!b[4]?' / tail clipped':'')).join('; ');
    const heads=motion.filter(n=>note.lane===null||n[0]===note.lane),state=effect[0][note.lane],fraction=effect[1]?.[note.lane];
    const risks=riskFrames.get(time.toFixed(6))||[];
    const riskText=risks.map(c=>'lane '+(c.lane+1)+' proximity '+c.vertical_range_pixels.join('…')+' px / '+c.state+(c.owner_hold!=null?' / hold '+c.owner_hold:' / unowned')).join('; ');
    const word=popup[2]||(popup[4]?'blank':'unknown'),stateText=known(state)+(effect[2]?' (common flash)':'');
    const pose=processing?.template_evidence?.poses?.[sample?.template_pose];
    const poseText=sample?.template_pose!=null?' / shape '+sample.template_pose+(pose?' / reference PTS '+Number(pose.source_pts_seconds).toFixed(6):''):'';
    const alignmentText=sample?.template_vertical_offset_pixels?' / vertical offset '+sample.template_vertical_offset_pixels+' feature px':'';
    const processingText=(sample?sample.state+' / '+confidence(sample.score)+' / '+(sample.unknown_reason||'clear'):'unmeasured')+poseText+alignmentText;
    marker(time,45,popup[2]?'#88dfff':'#99a5ae','Combo '+(popup[0]??'unknown')+' / '+word);
    marker(time,105-12*(fraction||0),color(state),stateText+' / white fraction '+confidence(fraction));
    for(const head of heads)marker(time,165+Math.max(-20,Math.min(20,(head[2]*height-receptor)/height*70)),'#ffe476','Head y='+Number(head[2]*height).toFixed(1)+' px / quality '+confidence(head[3]));
    if(risks.length)marker(time,190,risks.every(c=>c.state==='approaching')?'#9cddbe':'#ff8e9b',riskText);
    if(bodies.length)marker(time,212,'#c9acff',bodyText);
    marker(time,225,color(sample?.state),processingText);
    const row=document.createElement('tr'),cell=document.createElement('td'),button=document.createElement('button');
    button.textContent=fmt(time)+' / PTS '+pts.toFixed(6);button.onclick=()=>seek(time,-1,noteIndex);cell.appendChild(button);row.appendChild(cell);
    const provenance=popup.length>5?' / '+(popup[5]||'unknown read mode')+(popup[6]?' / recovered':'')+' / baseline '+(popup[7]??'unknown'):'';
    const values=[(popup[0]??'unknown')+' / '+confidence(popup[1])+provenance,word+' / '+confidence(popup[3]),stateText+' / '+confidence(fraction),(heads.length?heads.map(h=>(h[2]*height).toFixed(1)).join(', '):'No detected head')+(riskText?' / '+riskText:''),processingText+(bodyText?' / '+bodyText:'')];
    for(const value of values)text('td',value,row);rows.appendChild(row);observations.push({time,pts,values});
  }
  for(const [events,y,stroke] of [[channel.popup?.combo_events||[],30,'#9cddbe'],[channel.popup?.judgment_events||[],60,'#88dfff']]){
    for(const event of events){if(event.upper_seconds<lo||event.lower_seconds>hi)continue;
      line(root,x(Math.max(lo,event.lower_seconds)),y,x(Math.min(hi,event.upper_seconds)),y,stroke,4);
      label(root,event.label||String(event.before)+'→'+String(event.after),Math.min(1100,x(Math.max(lo,event.lower_seconds))),y-5,stroke);
    }
  }
  if(processing?.range)line(root,x(Math.max(lo,processing.range[0])),240,x(Math.min(hi,processing.range[1])),240,'#ff70dd',5);
  const cursor=line(root,x(playhead),14,x(playhead),245,'#ffffff',2);
  evidenceScene={key,lo,hi,x,cursor,observations};updateEvidenceCursor(playhead);
}
