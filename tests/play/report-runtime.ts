// Execute shipped SVG code with observable DOM and browser-animation substitutes.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const html = fs.readFileSync(process.argv[2], 'utf8');
const payload = html.match(/<script id="data" type="application\/json">(.*?)<\/script>/s)[1];
const runtime = html.match(/<script>\s*(.*?)<\/script>/s)[1];
assert.ok(!html.includes('<canvas'),'report must not contain canvas elements');
let createdNodes=0;
const activeAnimations=new Set<{currentTime: number; keyframes: unknown; options: unknown; cancel(): void}>();
function element(tag): Record<string, any> {
  createdNodes++;
  return {tag,style:{},attributes:{},children:[],textContent:'',value:'',
    clientWidth:1200,clientHeight:350,complete:false,files:[],paused:true,ended:false,currentTime:0,playbackRate:1,handlers:{},
    setAttribute(name,value){this.attributes[name]=String(value);if(['x','y','x1','y1','x2','y2','cx','cy','width','height','r'].includes(name))assert.ok(Number.isFinite(Number(value)),name+' has invalid geometry')},
    getAttribute(name){return this.attributes[name]??null},
    appendChild(node){node.parentElement=this;this.children.push(node);return node},
    replaceChildren(){this.children=[]},
    addEventListener(event,callback){(this.handlers[event]??=[]).push(callback)},
    getBoundingClientRect(){return {left:0,top:0,width:this.clientWidth,height:this.clientHeight}},
    closest(selector){if(selector==='[data-note]'&&this.getAttribute('data-note')!==null)return this;return this.parentElement?.closest(selector)??null},
    animate(keyframes,options){const animation={currentTime:0,keyframes,options,cancel(){activeAnimations.delete(this)}};activeAnimations.add(animation);return animation},
    getContext(){throw Error('canvas rendering is forbidden')},
  };
}
const elements=new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(match=>[match[1],element(match[1])]));
for(const match of html.matchAll(/<svg id="([^"]+)" viewBox="0 0 (\d+) (\d+)"/g)){
  const root=elements.get(match[1]);root.setAttribute('viewBox',`0 0 ${match[2]} ${match[3]}`);root.clientWidth=Number(match[2]);root.clientHeight=Number(match[3]);
}
const descendants=node=>node.children.flatMap(child=>[child,...descendants(child)]);
const squares=()=>descendants(elements.get('lanes')).filter(node=>node.getAttribute('data-kind')==='note-square');
elements.get('data').textContent = payload;
elements.get('spacingScale').value = '1';
elements.get('spacingInput').value = '1';
const initialNoteSize=Number(html.match(/id="noteSize"[^>]*value="(\d+)"/)[1]);
elements.get('noteSize').value=String(initialNoteSize);
let callbackId=0,resizeCallback=null;
const videoCallbacks=new Map(),animationCallbacks=new Map();
const video=elements.get('video');
video.requestVideoFrameCallback=callback=>{const id=++callbackId;videoCallbacks.set(id,callback);return id};
video.cancelVideoFrameCallback=id=>videoCallbacks.delete(id);
const dispatch=event=>{for(const handler of video.handlers[event]||[])handler()};
const context = vm.createContext({document: {
  getElementById(id) { assert.ok(elements.has(id), 'missing element '+id); return elements.get(id); },
  createElement: element,createElementNS(namespace,tag){assert.equal(namespace,'http://www.w3.org/2000/svg');return element(tag)},
}, URL, Blob, setTimeout,
Element: class {static [Symbol.hasInstance](node: unknown) {return node !== null && typeof node === "object" && "closest" in node}},
ResizeObserver:class {constructor(callback){resizeCallback=callback}observe(canvas){assert.equal(canvas,elements.get('lanes'))}},
requestAnimationFrame:callback=>{const id=++callbackId;animationCallbacks.set(id,callback);return id},
cancelAnimationFrame:id=>animationCallbacks.delete(id)});
vm.runInContext(runtime, context, {timeout: 10000});
const evaluate = expression => JSON.parse(vm.runInContext('JSON.stringify('+expression+')', context));
const rows = () => elements.get('events').children.map(row => row.children.map(cell => cell.textContent));
const initialRows = rows();
const verticalGeometry = evaluate('(()=>{const g=laneGeometry();return {earlier:g.y(playhead-.2),now:g.y(playhead),later:g.y(playhead+.2),firstLane:g.x(0),lastLane:g.x(data.layout.lanes.length-1)}})()');
assert.ok(verticalGeometry.earlier < verticalGeometry.now && verticalGeometry.now < verticalGeometry.later);
if (evaluate('data.layout.lanes.length') > 1) assert.ok(verticalGeometry.firstLane < verticalGeometry.lastLane);
const data = JSON.parse(payload);
assert.equal(initialRows.length, data.notes.filter(note => note.status === 'estimated').length);
const verticalNotes = evaluate('reviewNotes.map(({note})=>({lane:note.lane,x:laneGeometry().x(note.lane),y:laneGeometry().y(note.target_seconds)}))');
const targetRanges = evaluate('reviewNotes.map(({note})=>targetRange(note))');
const initialInputs = evaluate('reviewNotes.map(({index})=>inputRange(matchByNote.get(index)?.match,index))');
const markers=()=>{const shift=evaluate('(chartScene.origin-playhead)*chartScene.pps'),g=evaluate('({top:laneGeometry().top,bottom:laneGeometry().bottom})');return descendants(elements.get('lanes')).filter(node=>node.tag==='circle'&&['#b6ff59','#ff70dd'].includes(node.getAttribute('stroke'))).map(node=>({color:node.getAttribute('stroke'),args:[Number(node.getAttribute('cx')),Number(node.getAttribute('cy'))+shift]})).filter(mark=>mark.args[1]>=g.top&&mark.args[1]<=g.bottom)};
const initialMarkers=markers();
const defaultCandidateConnections=descendants(elements.get('lanes')).filter(node=>node.getAttribute('data-kind')==='candidate-connection').length;
assert.equal(defaultCandidateConnections,0,'unconfirmed candidates must be hidden by default');
assert.ok(!descendants(elements.get('lanes')).some(node=>node.getAttribute('data-kind')!=='note-square'&&node.getAttribute('stroke-dasharray')),'no unlinked hold envelope is drawn');
elements.get('candidates').checked=true;elements.get('candidates').onchange();
const optionalConnections=descendants(elements.get('lanes')).filter(node=>node.getAttribute('data-kind')==='candidate-connection');
for(const group of optionalConnections){
  const index=Number(group.getAttribute('data-note')),target=data.notes[index].target_seconds;
  assert.ok(Number(group.getAttribute('data-range-start'))>=target-.25-1e-9);
  assert.ok(Number(group.getAttribute('data-range-end'))<=target+.5+1e-9);
  assert.equal(group.children[0].getAttribute('stroke-dasharray'),'4 3','candidate has a link from its note');
}
const optionalCandidateConnections=optionalConnections.length;
elements.get('candidates').checked=false;elements.get('candidates').onchange();
for(const {index,note} of evaluate('reviewNotes')){
  if(note.note_type==='hold')continue;
  const intervals=evaluate('inputIntervals(matchByNote.get('+index+')?.match,'+index+')');
  for(const range of intervals){assert.ok(range[0]>=note.target_seconds-.25-1e-9);assert.ok(range[1]<=note.target_seconds+.5+1e-9)}
}
const initialDifferences = evaluate('reviewNotes.map(({note,index})=>difference(targetRange(note),inputRange(matchByNote.get(index)?.match,index)))');
elements.get('delay').value = '30';
elements.get('delay').oninput();
const correctedRows = rows();
const correctedMarkers=markers();
const correctedInputs = evaluate('reviewNotes.map(({index})=>inputRange(matchByNote.get(index)?.match,index))');
const correctedDifferences = evaluate('reviewNotes.map(({note,index})=>difference(targetRange(note),inputRange(matchByNote.get(index)?.match,index)))');
const details = [];
for (const index of [...new Set([0, initialRows.length - 1])]) {
  if (!elements.get('events').children[index]) continue;
  elements.get('events').children[index].onclick();
  details.push(elements.get('comparisonDetails').children.map(node => node.textContent));
}
const scaleGeometry=[];
for (const scale of [.25, 1, 16]) {
  const before = evaluate('({selectedNote,playhead})');
  elements.get('spacingScale').value = String(scale);
  elements.get('spacingScale').oninput();
  assert.equal(elements.get('lanes').getAttribute('viewBox').split(' ')[3],'680');
  assert.deepEqual(evaluate('({selectedNote,playhead})'), before);
  assert.deepEqual(evaluate('reviewNotes.map(({note})=>targetRange(note))'), targetRanges);
  if(initialRows.length){assert.ok(squares().length,'visible note has a colored square');assert.ok(squares().every(op=>Number(op.getAttribute('width'))===initialNoteSize&&op.getAttribute('width')===op.getAttribute('height')),'spacing must preserve square dimensions')}
  scaleGeometry.push(evaluate('(()=>{const g=laneGeometry();return g.y(playhead+.1)-g.y(playhead)})()'));
}
assert.ok(scaleGeometry[0]<scaleGeometry[1] && scaleGeometry[1]<scaleGeometry[2]);
if(initialRows.length)assert.ok(descendants(elements.get('lanes')).filter(node=>node.tag==='text'&&['↙','↖','●','↗','↘'].includes(node.textContent)).every(node=>[20,initialNoteSize].includes(Number(node.getAttribute('font-size')))));
elements.get('spacingInput').value = '1.01';elements.get('spacingInput').oninput();
assert.equal(elements.get('spacingScale').value,'1.01');
assert.ok(Math.abs(evaluate('(()=>{const g=laneGeometry();return g.y(playhead+.1)-g.y(playhead)})()')/scaleGeometry[1]-1.01)<1e-8);
const beforeSize=evaluate('({playhead,span:laneGeometry().to-laneGeometry().from})');
for(const size of [16,64,32]){elements.get('noteSize').value=String(size);elements.get('noteSize').oninput();assert.equal(evaluate('noteSize()'),size);assert.ok(squares().every(op=>Number(op.getAttribute('width'))===size));assert.deepEqual(evaluate('({playhead,span:laneGeometry().to-laneGeometry().from})'),beforeSize)}
// Narrow charts must retain every lane, square and both timing rails without
// a forced SVG width or horizontal scrolling, even at a large requested size.
const originalWidth=elements.get('lanes').clientWidth;
for(const width of [280,360,540]){
  elements.get('lanes').clientWidth=width;elements.get('noteSize').value='64';
  assert.ok(resizeCallback);resizeCallback();
  assert.equal(Number(elements.get('lanes').getAttribute('viewBox').split(' ')[2]),width);
  assert.ok(!elements.get('lanes').style.minWidth);
  const fit=evaluate('(()=>{const g=laneGeometry(),size=noteSize();return {size,left:g.left,right:g.right,laneWidth:g.laneWidth,lanes:data.layout.lanes.map((_,i)=>g.x(i))}})()');
  assert.ok(fit.size<=64);
  for(const x of fit.lanes){assert.ok(x-fit.size/2-8>=fit.left);assert.ok(x+fit.size/2+8<=fit.right)}
  assert.ok(squares().every(op=>Number(op.getAttribute('width'))===fit.size));
  assert.equal(elements.get('noteSizeValue').textContent,fit.size+' px'+(fit.size<64?' (fit to width)':''));
  const fitBeforeSpacing=fit.size;
  elements.get('spacingInput').value='0.37';elements.get('spacingInput').oninput();
  assert.equal(evaluate('noteSize()'),fitBeforeSpacing);
}
elements.get('lanes').clientWidth=originalWidth;elements.get('noteSize').value='32';resizeCallback();
elements.get('spacingScale').value = '1';elements.get('spacingScale').oninput();
if (initialRows.length) {
  elements.get('events').children[0].onclick();
  // Test hit coordinates after CSS scaling, including a click on the input band.
  const canvas = elements.get('lanes');
  const [,,svgWidth,svgHeight]=canvas.getAttribute('viewBox').split(' ').map(Number);
  canvas.clientWidth = svgWidth / 2;
  canvas.clientHeight = svgHeight / 2;
  const before = evaluate('selectedNote');
  const position = evaluate('(()=>{const g=laneGeometry(),n=data.notes[selectedNote];return {x:chartScene.selectionRects.get(selectedNote)?Number(chartScene.selectionRects.get(selectedNote).getAttribute("x"))+(noteSize()+6)/2:g.x(n.lane),y:g.y(n.target_seconds)}})()');
  canvas.onclick({clientX: position.x*canvas.clientWidth/svgWidth, clientY: position.y*canvas.clientHeight/svgHeight});
  assert.equal(evaluate('selectedNote'), before);
  const inputPosition = evaluate('(()=>{const g=laneGeometry(),n=data.notes[selectedNote],intervals=chartInputIntervals(selectedNote),input=intervals.length?[intervals[0][0],intervals.at(-1)[1]]:null;return input?{x:g.x(n.lane),y:g.y((input[0]+input[1])/2)}:null})()');
  const [,,currentWidth,currentHeight]=canvas.getAttribute('viewBox').split(' ').map(Number);
  if (inputPosition) canvas.onclick({clientX: inputPosition.x*canvas.clientWidth/currentWidth, clientY: inputPosition.y*canvas.clientHeight/currentHeight});
  assert.equal(evaluate('selectedNote'), before);
  elements.get('nextNote').onclick();
  elements.get('previousNote').onclick();
  assert.equal(evaluate('selectedNote'), before);
  elements.get('position').value = '12';
  elements.get('position').oninput();
  assert.equal(evaluate('playhead'), 12);
  assert.equal(elements.get('chartPosition').textContent, '0:12.000');
  canvas.clientWidth=originalWidth;canvas.clientHeight=680;resizeCallback();
}

elements.get('center').onclick();
elements.get('next').onclick();
elements.get('previous').onclick();
elements.get('excluded').checked = true;
elements.get('excluded').onchange();
elements.get('spacingScale').value = '8';elements.get('spacingScale').oninput();
const tableRowBeforePlayback=elements.get('events').children[0];
video.currentTime=12.1;dispatch('seeked');video.paused=false;dispatch('play');dispatch('play');
assert.equal(videoCallbacks.size,1,'only one frame clock should run');
const motionBefore=evaluate('chartScene.key'),nodeCount=createdNodes;
const retainedScene=elements.get('lanes').children.at(-2);
assert.equal(activeAnimations.size,1,'one CSS transform animation should move the SVG scene');
for(const animation of activeAnimations)animation.currentTime=25;
let [id,callback]=videoCallbacks.entries().next().value;videoCallbacks.delete(id);callback(0,{mediaTime:12.125});
assert.equal(evaluate('playhead'),12.125);
assert.equal(elements.get('chartPosition').textContent,'0:12.125');
assert.equal(createdNodes,nodeCount,'ordinary video frames must not create SVG or HTML nodes');
assert.equal(evaluate('chartScene.key'),motionBefore);
assert.equal(elements.get('lanes').children.at(-2),retainedScene);
video.playbackRate=.5;video.currentTime=12.125;dispatch('ratechange');
assert.equal(evaluate('chartScene.rate'),.5);
for(const animation of activeAnimations)animation.currentTime=250;
[id,callback]=videoCallbacks.entries().next().value;videoCallbacks.delete(id);callback(0,{mediaTime:12.25});
assert.equal(evaluate('playhead'),12.25,'use presented media time, independently of playback speed');
assert.equal(createdNodes,nodeCount,'rate changes must reuse retained SVG');
video.currentTime=12.25;dispatch('waiting');assert.equal(activeAnimations.size,0,'buffering freezes CSS motion');
dispatch('playing');assert.equal(activeAnimations.size,1);
video.paused=true;dispatch('pause');assert.equal(videoCallbacks.size,0);assert.equal(activeAnimations.size,0);
video.currentTime=14.125;dispatch('seeking');dispatch('seeked');assert.equal(evaluate('playhead'),14.125);
assert.ok(evaluate('chartScene.motion.style.transform').includes('translateY('));
video.currentTime=24.125;dispatch('seeked');assert.equal(evaluate('playhead'),24.125);
assert.notEqual(evaluate('chartScene.key'),motionBefore,'distant seeking replaces the bounded time page');
video.requestVideoFrameCallback=undefined;video.paused=false;dispatch('play');assert.equal(animationCallbacks.size,1);
video.currentTime=24.25;
[id,callback]=animationCallbacks.entries().next().value;animationCallbacks.delete(id);callback(0);
assert.equal(evaluate('playhead'),24.25);
video.paused=true;dispatch('pause');assert.equal(animationCallbacks.size,0);assert.equal(activeAnimations.size,0);
// Older browsers still move the retained SVG group rather than rebuilding it.
vm.runInContext('chartScene.motion.animate=undefined',context);const fallbackNodes=createdNodes;
video.currentTime=24.3;video.paused=false;dispatch('play');
[id,callback]=animationCallbacks.entries().next().value;animationCallbacks.delete(id);callback(0);
assert.equal(createdNodes,fallbackNodes);assert.ok(evaluate('chartScene.motion.style.transform').includes('translateY('));
video.paused=true;dispatch('pause');
assert.equal(elements.get('events').children[0],tableRowBeforePlayback,'playback must not rebuild the note table');
assert.deepEqual(evaluate('data'), data, 'embedded evidence changed');
let evidencePreview=null;
if(data.visual_channels?.timeline){
  vm.runInContext('seek(10,-1,0)',context);
  const body=elements.get('evidenceFrames'),first=body.children[0];
  const rows=body.children.map(row=>row.children.map(cell=>cell.children[0]?.textContent||cell.textContent).join(' | '));
  assert.equal(rows.length,3,'only frames around selected note appear');
  body.children[1].children[0].children[0].onclick();
  const seekTime=video.currentTime;assert.equal(seekTime,10,'frame seeks recording time, not source PTS');
  vm.runInContext('updatePlayback(10.005)',context);
  assert.equal(body.children[0],first,'ordinary playback retains observation rows');
  assert.equal(elements.get('evidenceTimeline').children.at(-1).getAttribute('visibility'),'visible');
  vm.runInContext('seek(11,-1,1)',context);
  assert.equal(body.children.length,1,'note selection updates the observation window');
  evidencePreview={rows,seekTime,secondNoteSummary:elements.get('evidenceSummary').textContent};
  assert.deepEqual(evaluate('data'),data,'observation UI changed embedded evidence');
}
let typePreview=null;
if(data.notes[0]?.type_evidence?.length){
  vm.runInContext('seek(data.notes[0].target_seconds,-1,0)',context);
  const proof=data.notes[0].type_evidence.find(o=>o.kind!=='unknown');
  const button=elements.get('comparisonDetails').children.find(node=>node.tag==='button'&&node.textContent.includes('PTS '+proof.source_pts_seconds.toFixed(6)));
  assert.ok(button,'type evidence exposes original source PTS');button.onclick();
  assert.equal(video.currentTime,proof.playback_seconds,'type evidence seeks original recording time');
  typePreview={status:data.notes[0].type_status,seek:video.currentTime};
}
console.log(JSON.stringify({initialRows, correctedRows, details, evidencePreview, typePreview, targetRanges, initialInputs,
  initialDifferences, correctedInputs, correctedDifferences, verticalGeometry, verticalNotes, initialMarkers, correctedMarkers, defaultCandidateConnections, optionalCandidateConnections}));
