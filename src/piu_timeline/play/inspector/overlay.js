// @ts-check
'use strict';
// One source video. SVG measurements use the documented crop inside the full recording.
let frameOverlay=null;
function initializeFrameOverlay(){
  const stream=data.media.video_streams?.[0],roi=data.game_roi;
  if(!stream?.width||!stream?.height||!roi){$('showOverlay').checked=false;$('showOverlay').disabled=true;$('overlayStatus').textContent='Overlay unavailable: source dimensions or game crop are missing.';return}
  const root=svgRoot('sourceOverlay',stream.width,stream.height);
  root.parentElement.style.aspectRatio=stream.width+' / '+stream.height;
  const rectangle=(rect,color)=>svgNode('rect',{x:roi[0]+rect[0]*roi[2],y:roi[1]+rect[1]*roi[3],width:rect[2]*roi[2],height:rect[3]*roi[3],fill:'none',stroke:color,'stroke-width':2},root);
  const popup=[];if(data.layout.combo_roi)popup.push(rectangle(data.layout.combo_roi,'#f1c478'));if(data.judgment_roi)popup.push(rectangle(data.judgment_roi,'#88dfff'));
  const receptorY=roi[1]+data.layout.receptor_y*roi[3];
  const receptors=data.layout.lanes.map(l=>svgNode('circle',{cx:roi[0]+l.x*roi[2],cy:receptorY,r:6,fill:'none',stroke:'#c9acff','stroke-width':3},root));
  const maxCount=records=>(records||[]).reduce((n,frame)=>Math.max(n,frame?.length||0),0);
  const heads=Array.from({length:maxCount(data.visual_channels?.motion?.observations)},()=>svgNode('circle',{r:8,fill:'none',stroke:'#ffe476','stroke-width':3},root));
  const bodies=Array.from({length:maxCount(data.visual_channels?.processing?.body_observations)},()=>svgNode('line',{stroke:'#c9acff','stroke-width':5},root));
  const processing=data.layout.lanes.map(l=>svgNode('circle',{cx:roi[0]+l.x*roi[2],cy:receptorY,r:11,fill:'none',stroke:'#ff70dd','stroke-width':2},root));
  frameOverlay={root,roi,popup,receptors,heads,bodies,processing};
  $('showOverlay').onchange=()=>updateInspectorFrame(playhead,true);
  $('channelFocus').onchange=()=>updateInspectorFrame(playhead,true);
}
function renderFrameOverlay(index){
  if(!frameOverlay)return;
  const {root,roi,popup,receptors,heads,bodies,processing}=frameOverlay,channel=data.visual_channels,focus=$('channelFocus').value;
  root.hidden=!$('showOverlay').checked;
  root.style.display=$('showOverlay').checked?'':'none';
  const visible=(node,show)=>node.setAttribute('visibility',show?'visible':'hidden');
  const applies=name=>focus==='all'||focus===name;
  for(const node of popup)visible(node,applies('popup'));
  const effect=channel.receptors?.observations?.[index];
  receptors.forEach((node,lane)=>{visible(node,applies('receptors'));node.setAttribute('stroke',effect?.[0]?.[lane]===true?'#9cddbe':effect?.[0]?.[lane]===false?'#ff8e9b':'#99a5ae')});
  const positions=channel.motion?.observations?.[index]||[];
  heads.forEach((node,i)=>{const head=positions[i];visible(node,applies('motion')&&!!head);if(head){node.setAttribute('cx',roi[0]+head[1]*roi[2]);node.setAttribute('cy',roi[1]+head[2]*roi[3])}});
  const observed=channel.processing?.body_observations?.[index]||[],height=channel.processing?.pixel_coordinates?.height;
  bodies.forEach((node,i)=>{const body=observed[i],lane=data.layout.lanes[body?.[0]];visible(node,applies('motion')&&!!body&&!!height&&!!lane);if(body&&height&&lane){
    const x=roi[0]+lane.x*roi[2];for(const key of ['x1','x2'])node.setAttribute(key,x);node.setAttribute('y1',roi[1]+body[1]/height*roi[3]);node.setAttribute('y2',roi[1]+body[2]/height*roi[3]);
  }});
  const note=data.notes[selectedNote],time=channel.timeline.frames[index][0],record=channel.processing?.notes?.find(n=>n.note===selectedNote),sample=record?.samples?.find(s=>Math.abs(s.time-time)<1e-6);
  processing.forEach((node,lane)=>{visible(node,applies('processing')&&note?.lane===lane&&Number.isFinite(sample?.y)&&!!height);if(Number.isFinite(sample?.y)&&height)node.setAttribute('cy',roi[1]+sample.y/height*roi[3]);node.setAttribute('stroke',sample?.state==='present'?'#9cddbe':sample?.state==='absent'?'#ff8e9b':'#99a5ae')});
}
