// @ts-check
'use strict';
function inspectJSON(parent,title,value){
  const details=text('details','',parent);text('summary',title,details);
  const output=text('pre','',details);let loaded=false;
  details.addEventListener('toggle',()=>{if(details.open&&!loaded){output.textContent=JSON.stringify(value??null,null,2);loaded=true}});
  return details;
}
function provenanceCard(parent,title,description,tab){
  const card=text('article','',parent);card.className='provenance-card';text('h3',title,card);text('p',description,card);
  if(tab)text('button','Inspect '+title,card).onclick=()=>selectInspectorTab(tab);
  return card;
}
function renderDerivation(){
  const index=selectedNote,note=data.notes[index],root=$('derivationDetails'),chain=$('derivationChain');root.replaceChildren();chain.replaceChildren();
  $('derivationSummary').textContent=note?'Note #'+(index+1)+' / lane '+(note.lane+1)+' · '+note.status+' · '+(note.reason||note.fit_method||'No fit method supplied'):
    'No note selected. Frame and warning evidence remains accessible without inventing a fitted chart target.';
  if(selectedWarning!==null){const item=inspectorWarnings[selectedWarning];if(item)inspectJSON(root,'Selected warning · full diagnostic records',item.records)}
  if(!note){provenanceCard(chain,'Original observations','Inspect the selected recording position, including unassigned observations.','channels');return}
  const hold=holdFor(note),matched=matchByNote.get(index)?.match,range=rangeByNote[index],processing=data.visual_channels?.processing?.notes?.find(n=>n.note===index);
  provenanceCard(chain,'1 · Native channels',(note.points?.length??0)+' tracked positions. Independent popup, receptor, motion and processing observations.','channels');
  provenanceCard(chain,'2 · Coordinates & timing',(note.fit_method||'No accepted fit')+' · '+(note.beat_reconstruction?.status||'Beat reconstruction unavailable')+'. Target: '+formatRange(targetRange(note)),null);
  provenanceCard(chain,'3 · UCS placement',data.inspector_artifacts?.chart?.registration?.status||'No saved registration','ucs');
  provenanceCard(chain,'4 · Judgment / held state',hold?'Sustained recognition; no separate head press.':range?.status||'No association','chart');
  const blocks=[['Tracked positions and raw type evidence',{lane:note.lane,points:note.points,type_status:note.type_status,type_evidence:note.type_evidence,type_unknown_reasons:note.type_unknown_reasons}],
    ['Registered geometry and target clock',Object.fromEntries(Object.entries(note).filter(([k])=>!['points','type_evidence','type_unknown_reasons'].includes(k)))],
    ['Independent note-processing observations',processing],['Long-note geometry and sustained recognition',hold],
    ['Timing association and uncertainty',{range:range??null,match:matched??null,conflicted_matches:(data.conflicted_matches||[]).filter(m=>m.note===index),
      combo_event:matched?.combo_event!=null?data.combo_events[matched.combo_event]:null,judgment_event:matched?.judgment_event!=null?data.judgment_events?.[matched.judgment_event]:null}],
    ['Applied chart policy and visual support',{policy:note.chart_policy,visual_support:data.visual_support,regions:(data.chart_policy?.regions||[]).filter(r=>{
      const t=note.target_seconds??note.points?.[0]?.[0];return r.playback_start_seconds<=t&&t<r.playback_end_seconds})}]];
  for(const [title,value] of blocks)inspectJSON(root,title,value);
  const warnings=inspectorWarnings.filter(item=>warningNote(item.record)===index);
  text('button',warnings.length+' warnings for this note',root).onclick=()=>{$('warningScope').value='selected';$('warningSearch').value='';warningLimit=50;selectInspectorTab('warnings')};
}
function renderUcsSelection(){
  const chart=data.inspector_artifacts?.chart,root=$('ucsSelection');root.replaceChildren();
  const metadata=chart?.metadata;
  $('ucsStatus').textContent=chart?'Registration: '+chart.registration.status+(chart.registration.reason?' · '+chart.registration.reason:'')+
    (chart.error?' · '+chart.error:'')+(metadata?' · '+metadata.review_status+' · source association: '+(chart.linked?'exact saved analysis identity':'unlinked / different or edited analysis'):''):
    'No saved UCS registration or draft snapshot is attached. No UCS placements are inferred from judgment times.';
  if(chart?.linked&&selectedNote!==null){
    const placements=(metadata?.placements||[]).filter(p=>p.note===selectedNote),unresolved=(metadata?.unresolved||[]).filter(p=>p.note===selectedNote);
    text('p',placements.length?'Selected note #'+(selectedNote+1)+' has '+placements.length+' saved placement(s).':
      'Selected note #'+(selectedNote+1)+' has no saved placement. '+(unresolved.map(p=>p.reason).join('; ')||'No per-note placement record supplied.'),root);
    for(const placement of [...placements,...unresolved])inspectJSON(root,'Selected placement / unresolved record',placement);
  }else if(metadata)text('p','Source note identifiers belong to the saved draft source. They are not linked to this analysis.',root);
}
function initializeProvenance(){
  const cards=[['popup','Combo / judgment popup','Counter and word reads, confidence, blank states and refresh brackets. Persistent text is not a new input.'],
    ['receptors','Receptor light','Per-lane light state, white-pixel fraction and common flashes. Light does not establish a tap by itself.'],
    ['motion','Moving notes / bodies','Observed normalized head positions and pixel-coordinate body extents. Missing detections are not proof of processing.'],
    ['processing','Note processing','Native pixel presence / clear absence / unknown around a fitted trajectory. Association consumes this evidence separately.']];
  for(const [key,title,description] of cards){const card=provenanceCard($('channelCards'),title,description,null);text('button','Highlight in video',card).onclick=()=>{$('channelFocus').value=key;updateInspectorFrame(playhead,true)}}
  const artifacts=[['Native observations','visual-channels.json','Four channels on their original timeline'],['Tracked / registered analysis','analysis.json','Trajectory positions, coordinate clocks and beats'],
    ['Coordinate source','coordinates.json','Original track observations and registered coordinate results'],
    ['Physical timing','native-timing.json','Physical validation without musical assignment'],['Beat decisions','beat-result.json','Owned musical timing decisions and proofs'],
    ['Judgment associations','judgment-associations.json','HUD interpretation without coordinate edits'],['Inspection result','inspection-result.json','Ordered owned consumer outputs'],
    ['Target and input ranges','timing-ranges.json','Associations, alternatives and explicit unknowns'],['Long-note state','holds.json','Geometry and sustained recognition'],
    ['Recognition diagnostics','recognition-warnings.json','Unresolved interpretation and timing'],['Visibility diagnostics','visibility-diagnostics.json','Lost detections, stops and velocity changes'],
    ['Excluded tracks','excluded-trajectories.json','Visible candidates and their disposition'],['Prepared view','report-data.json','Input to pure HTML rendering'],
    ['Consumer input','presentation-input.json','Prepared retained observations and native proofs'],['Consumer stages','derived-stages/manifest.json','Per-stage producer and input/output fingerprints'],
    ['UCS input','ucs-input.json','Prepared timing template and visible chart observations, when registration reached this stage']];
  for(const [title,path,description] of artifacts){const card=provenanceCard($('artifactLinks'),title,description,null);const link=text('a','Open artifact',card);link.setAttribute('href',path)}
  $('stageManifest').textContent=JSON.stringify(data.inspector_artifacts?.stages??{status:'unavailable',reason:'No retained stage manifest attached'},null,2);
  const chart=data.inspector_artifacts?.chart,metadata=chart?.metadata;
  $('ucsText').textContent=chart?.text??'No saved UCS text attached.';
  let shown=0;
  const placements=[...(metadata?.placements||[]).map(p=>({...p,outcome:'placed'})),...(metadata?.unresolved||[]).map(p=>({...p,outcome:'unresolved'}))];
  const more=()=>{for(const p of placements.slice(shown,shown+100)){
    const row=text('tr','',$('ucsRows'));text('td','#'+(p.note+1)+(p.lane!=null?' / lane '+(p.lane+1):''),row);
    text('td',p.outcome==='placed'?'section '+(p.section+1)+' / row '+(p.row+1)+(p.kind==='hold'?' → section '+(p.end_section+1)+' / row '+(p.end_row+1):''):'—',row);
    text('td',Number.isFinite(p.song_seconds)?fmt(p.song_seconds)+(p.kind==='hold'?' … '+fmt(p.end_song_seconds):''):'—',row);text('td',p.reason||p.kind||p.outcome,row);
    if(chart.linked&&data.notes[p.note])row.onclick=()=>{const n=data.notes[p.note];selectedWarning=null;evidenceAnchor=null;evidenceLane=null;seek(n.target_seconds??n.points?.[0]?.[0]??playhead,-1,p.note);selectInspectorTab('analysis')};
  }shown=Math.min(shown+100,placements.length);$('moreUcs').hidden=shown>=placements.length};
  $('moreUcs').onclick=more;more();renderUcsSelection();
}
