import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {render} from '../../src/piu_timeline/derived/report.ts';
import {createDOM,descendants} from './browser-dom.ts';

function inspector(overrides={}) {
  const data={media:{path:'/original.mkv',video_streams:[{width:1920,height:1080}]},game_roi:[100,50,1300,730],
    start_seconds:8,end_seconds:20,analysis_width:650,analysis_height:365,frame_count:4,
    layout:{receptor_y:.14,combo_roi:[.4,.5,.2,.1],lanes:[{name:'C',x:.5,color:'yellow'}]},
    judgment_roi:[.35,.4,.3,.1],bootstrap:{ocr_images:0,missing_digits:[]},notes:[
      {status:'estimated',lane:0,target_seconds:10,prediction_uncertainty_seconds:.01,points:[[9.98,182.5]],fit_method:'native_test'},
      {status:'excluded',lane:0,target_seconds:null,points:[[11,90],[11.02,80]],reason:'ambiguous_type'}],
    matches:[],combo_events:[],judgment_events:[],excluded_notes:{},limitations:[],combo_readable_fraction:1,
    hold_analysis:{holds:[]},timing_ranges:{notes:{0:{status:'unknown',input_ranges:[]}},association_limits_seconds:{early:.25,late:.5}},
    visual_channels:{timeline:{frames:[[9.98,99.98],[10,100],[11,101],[11.02,101.02]]},
      popup:{observations:[[3,.9,null,0,true],[4,.9,'GREAT',.9,false],[5,.9,'PERFECT',.9,false],[5,.9,'PERFECT',.9,false]],combo_events:[],judgment_events:[]},
      receptors:{observations:[[[false],[.1],false],[[true],[.9],false],[[null],[.5],true],[[false],[.1],false]],onsets:1,unknown_lane_frames:1},
      motion:{observations:[[[0,.5,.5,.9]],[],[[0,.5,.25,.9]],[]],detections:2,tracks:[{},{}]},
      processing:{notes:[],counts:{},body_observations:[[],[],[],[]]}},
    recognition_diagnostics:{warnings:[{note:1,lane:0,reason:'ambiguous_type',visible_start_seconds:11,visible_end_seconds:11.02}]},...overrides};
  const html=render(JSON.stringify(data),'Song','S20','source.mkv'),dom=createDOM(html),{elements}=dom;
  elements.get('data').textContent=html.match(/<script id="data" type="application\/json">(.*?)<\/script>/s)[1];
  elements.get('spacingScale').value='1';elements.get('channelFocus').value='all';
  const context=vm.createContext({document:dom.document,URL,Blob,setTimeout,
    Element:class{static [Symbol.hasInstance](node){return !!node&&typeof node.closest==='function'}},
    ResizeObserver:class{observe(){}},requestAnimationFrame(){return 1},cancelAnimationFrame(){}});
  vm.runInContext(html.match(/<script>\s*(.*?)<\/script>/s)[1],context,{timeout:5000});
  const evaluate=expression=>JSON.parse(vm.runInContext(`JSON.stringify(${expression})`,context));
  return {data,dom,elements,evaluate,run:code=>vm.runInContext(code,context)};
}

test('tabs preserve shared note/time and support accessible keyboard navigation',()=>{
  const {elements,evaluate,run}=inspector();
  run('seek(10,-1,0)');const before=evaluate('({selectedNote,playhead})');
  for(const tab of ['channels','analysis','ucs','warnings','data','chart']){
    elements.get('tab-'+tab).onclick();assert.deepEqual(evaluate('({selectedNote,playhead})'),before);
    for(const other of ['chart','channels','analysis','ucs','warnings','data']){
      assert.equal(elements.get('panel-'+other).hidden,other!==tab);assert.equal(elements.get('tab-'+other).getAttribute('aria-selected'),String(other===tab));
    }
  }
  elements.get('tab-chart').onkeydown({key:'End',preventDefault(){}});
  assert.equal(elements.get('tab-data').focused,true);assert.equal(evaluate('activeInspectorTab'),'data');
});

test('warning with no target opens original frames and excluded-track derivation',()=>{
  const {elements,evaluate,run}=inspector();elements.get('tab-warnings').onclick();
  const buttons=descendants(elements.get('warningRows')).filter(n=>n.tag==='button');
  buttons.find(n=>n.textContent==='Video + channels').onclick();
  assert.equal(evaluate('activeInspectorTab'),'channels');assert.equal(elements.get('video').currentTime,11);
  assert.equal(evaluate('selectedNote'),1);assert.equal(evaluate('evidenceAnchor'),11);
  assert.equal(elements.get('evidenceFrames').children.length,2);assert.match(elements.get('evidenceSummary').textContent,/Note 2/);
  assert.match(elements.get('framePosition').textContent,/source PTS 101\.000000/);
  assert.match(elements.get('frameTracks').children[0].textContent,/#2.*excluded/);
  elements.get('frameTracks').children[0].onclick();assert.equal(evaluate('activeInspectorTab'),'analysis');
  elements.get('tab-analysis').onclick();assert.match(elements.get('derivationSummary').textContent,/excluded.*ambiguous_type/);
  const details=elements.get('derivationDetails').children[0];details.open=true;details.handlers.toggle[0]();
  assert.match(details.children[1].textContent,/ambiguous_type/);
  run('inspectAt(11,null,null)');assert.equal(evaluate('selectedNote'),null);assert.match(elements.get('evidenceSummary').textContent,/all lanes/);
});

test('recording overlays transform normalized positions through crop geometry without changing evidence',()=>{
  const {data,elements,evaluate,run}=inspector();run('inspectAt(9.98,0,0)');
  const circles=descendants(elements.get('sourceOverlay')).filter(n=>n.tag==='circle'&&n.getAttribute('r')==='8');
  assert.equal(circles[0].getAttribute('cx'),'750');assert.equal(circles[0].getAttribute('cy'),'415');
  elements.get('channelFocus').value='popup';elements.get('channelFocus').onchange();assert.equal(circles[0].getAttribute('visibility'),'hidden');
  elements.get('frameNext').onclick();assert.equal(elements.get('video').currentTime,10);assert.match(elements.get('snapshot-popup').textContent,/GREAT/);
  assert.deepEqual(evaluate('data'),data);
});

test('playback retains channel rows, raw overlay nodes and does not rerender the hidden chart',()=>{
  const {dom,elements,evaluate,run}=inspector();run('inspectAt(9.98,0,0)');
  const row=elements.get('evidenceFrames').children[0],before=dom.nodeCount(),scene=evaluate('chartScene.key');
  run('updatePlayback(10);updatePlayback(11)');
  assert.equal(dom.nodeCount(),before);assert.equal(elements.get('evidenceFrames').children[0],row);assert.equal(evaluate('chartScene.key'),scene);
  assert.equal(JSON.parse(elements.get('frameData').textContent).source_pts_seconds,101);
});

test('unavailable channels, frame times and UCS registration remain explicit',()=>{
  const {elements,run}=inspector({visual_channels:undefined});run('inspectAt(11,null,null)');
  assert.match(elements.get('framePosition').textContent,/No retained/);assert.match(elements.get('evidenceSummary').textContent,/No retained/);
  elements.get('tab-ucs').onclick();assert.match(elements.get('ucsStatus').textContent,/No saved UCS registration/);assert.equal(elements.get('ucsRows').children.length,0);
});

test('UCS placements link only exact source identity; unresolved placement remains visible',()=>{
  const chart={registration:{status:'existing'},linked:true,text:':Format=1\nX\n',metadata:{review_status:'unreviewed_draft',
    placements:[{note:0,lane:0,section:0,row:2,song_seconds:1,kind:'tap'}],unresolved:[{note:1,reason:'Ambiguous row'}]}};
  const {elements,evaluate}=inspector({inspector_artifacts:{chart}});elements.get('tab-ucs').onclick();
  assert.match(elements.get('ucsRows').children[0].children[1].textContent,/section 1 \/ row 3/);
  assert.match(elements.get('ucsRows').children[1].children[3].textContent,/Ambiguous row/);
  elements.get('ucsRows').children[0].onclick();assert.equal(evaluate('activeInspectorTab'),'analysis');assert.equal(evaluate('selectedNote'),0);
  const unlinked=inspector({inspector_artifacts:{chart:{...chart,linked:false}}});assert.equal(unlinked.elements.get('ucsRows').children[0].onclick,undefined);
});


test('processing overlay uses its own feature height and expected trajectory center',()=>{
  const instance=inspector();
  instance.run("data.visual_channels.processing.pixel_coordinates={height:100};data.visual_channels.processing.notes=[{note:0,samples:[{time:9.98,y:25,state:'present'}]}];inspectAt(9.98,0,0)");
  const marker=descendants(instance.elements.get('sourceOverlay')).find(n=>n.tag==='circle'&&n.getAttribute('r')==='11');
  assert.equal(marker.getAttribute('cy'),'232.5');assert.equal(marker.getAttribute('stroke'),'#9cddbe');assert.equal(marker.getAttribute('visibility'),'visible');
});


test('warnings page without suppressing records, group original copies and retain untimed cases',()=>{
  const warnings=Array.from({length:70},(_,i)=>({note:i%2,lane:0,reason:'unresolved_'+i,visible_start_seconds:10,visible_end_seconds:11}));
  const {elements,evaluate}=inspector({recognition_diagnostics:{warnings},visibility_diagnostics:{warnings:[warnings[0]],known_occlusions:[],accounted_exits:[]}});
  elements.get('tab-warnings').onclick();assert.equal(elements.get('warningRows').children.length,50);
  assert.equal(evaluate('inspectorWarnings[0].records.length'),2);assert.equal(evaluate('inspectorWarnings.length'),70);
  elements.get('moreWarnings').onclick();assert.equal(elements.get('warningRows').children.length,70);
  elements.get('warningSearch').value='unresolved_66';elements.get('warningSearch').oninput();assert.equal(elements.get('warningRows').children.length,1);
  elements.get('warningSearch').value='lane 1';elements.get('warningScope').value='selected';elements.get('warningScope').onchange();assert.equal(elements.get('warningRows').children.length,35);
  const untimed=inspector({recognition_diagnostics:{warnings:[{reason:'missing_source_time'}]}});untimed.elements.get('tab-warnings').onclick();
  assert.equal(descendants(untimed.elements.get('warningRows')).filter(n=>n.tag==='button').length,0);
});


test('uncertain repeated-frame crossings expose their source interval in the inspector',()=>{
  const {elements,evaluate,run}=inspector();
  run("data.notes[0].stationary_phase_interval={recording_seconds:[9.98,10],source_pts_seconds:[99.98,100]};seek(10,-1,0)");
  const details=elements.get('comparisonDetails').children;
  assert.ok(details.some(n=>n.textContent.includes('scroll pause and a repeated captured image')));
  details.find(n=>n.tag==='button'&&n.textContent==='Review repeated native frames').onclick();
  assert.equal(elements.get('video').currentTime,9.98);assert.equal(evaluate('activeInspectorTab'),'channels');
});
