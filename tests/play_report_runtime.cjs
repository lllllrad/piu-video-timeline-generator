// Execute the shipped inline report code with observable DOM/canvas substitutes.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(process.argv[2], 'utf8');
const payload = html.match(/<script id="data" type="application\/json">(.*?)<\/script>/s)[1];
const runtime = html.match(/<script>\s*(.*?)<\/script>/s)[1];
const noteFonts=new Set();
function element(tag) {
  return {tag, style: {}, children: [], textContent: '', value: '', width: 1200, height: 350,
    clientWidth: 1200, clientHeight: 350, complete: false, files: [], paused: true, ended: false, currentTime: 0, handlers: {},
    appendChild(node) { this.children.push(node); return node; },
    replaceChildren() { this.children = []; }, addEventListener(event, callback) { (this.handlers[event]??=[]).push(callback); },
    getBoundingClientRect() { return {left: 0, top: 0}; },
    getContext() {
      return new Proxy({}, {get: (object, key) => object[key] ?? ((...args) => {
        if(key==='fillText'&&['↙','↖','●','↗','↘'].includes(args[0]))noteFonts.add(object.font);
        for (const value of args) if (typeof value === 'number') assert.ok(Number.isFinite(value), key+' has invalid geometry');
      })});
    }
  };
}
const elements = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(match => [match[1], element(match[1])]));
for (const match of html.matchAll(/<canvas id="([^"]+)" width="(\d+)" height="(\d+)"/g)) {
  const canvas = elements.get(match[1]);
  canvas.width = canvas.clientWidth = Number(match[2]);
  canvas.height = canvas.clientHeight = Number(match[3]);
}
elements.get('data').textContent = payload;
elements.get('spacingScale').value = '1';
elements.get('spacingInput').value = '1';
elements.get('noteSize').value = '32';
let callbackId=0;
const videoCallbacks=new Map(),animationCallbacks=new Map();
const video=elements.get('video');
video.requestVideoFrameCallback=callback=>{const id=++callbackId;videoCallbacks.set(id,callback);return id};
video.cancelVideoFrameCallback=id=>videoCallbacks.delete(id);
const dispatch=event=>{for(const handler of video.handlers[event]||[])handler()};
const context = vm.createContext({document: {
  getElementById(id) { assert.ok(elements.has(id), 'missing element '+id); return elements.get(id); },
  createElement: element,
}, URL, Blob, setTimeout,
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
const initialDifferences = evaluate('reviewNotes.map(({note,index})=>difference(targetRange(note),inputRange(matchByNote.get(index)?.match,index)))');
elements.get('delay').value = '30';
elements.get('delay').oninput();
const correctedRows = rows();
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
  assert.equal(elements.get('lanes').height, 680);
  assert.deepEqual(evaluate('({selectedNote,playhead})'), before);
  assert.deepEqual(evaluate('reviewNotes.map(({note})=>targetRange(note))'), targetRanges);
  scaleGeometry.push(evaluate('(()=>{const g=laneGeometry();return g.y(playhead+.1)-g.y(playhead)})()'));
}
assert.ok(scaleGeometry[0]<scaleGeometry[1] && scaleGeometry[1]<scaleGeometry[2]);
if(initialRows.length)assert.ok([...noteFonts].every(font=>['bold 20px system-ui','bold 32px system-ui'].includes(font)));
elements.get('spacingInput').value = '1.01';elements.get('spacingInput').oninput();
assert.equal(elements.get('spacingScale').value,'1.01');
assert.ok(Math.abs(evaluate('(()=>{const g=laneGeometry();return g.y(playhead+.1)-g.y(playhead)})()')/scaleGeometry[1]-1.01)<1e-8);
const beforeSize=evaluate('({playhead,span:laneGeometry().to-laneGeometry().from})');
for(const size of [16,64,32]){elements.get('noteSize').value=String(size);elements.get('noteSize').oninput();assert.equal(evaluate('noteSize()'),size);assert.deepEqual(evaluate('({playhead,span:laneGeometry().to-laneGeometry().from})'),beforeSize)}
elements.get('spacingScale').value = '1';elements.get('spacingScale').oninput();
if (initialRows.length) {
  elements.get('events').children[0].onclick();
  // Test hit coordinates after CSS scaling, including a click on the input band.
  const canvas = elements.get('lanes');
  canvas.clientWidth = canvas.width / 2;
  canvas.clientHeight = canvas.height / 2;
  const before = evaluate('selectedNote');
  const position = evaluate('(()=>{const g=laneGeometry(),n=data.notes[selectedNote];return {x:g.x(n.lane),y:g.y(n.target_seconds)}})()');
  canvas.onclick({clientX: position.x*canvas.clientWidth/canvas.width, clientY: position.y*canvas.clientHeight/canvas.height});
  assert.equal(evaluate('selectedNote'), before);
  const inputPosition = evaluate('(()=>{const g=laneGeometry(),n=data.notes[selectedNote],input=inputRange(matchByNote.get(selectedNote)?.match,selectedNote);return input?{x:g.x(n.lane),y:g.y((input[0]+input[1])/2)}:null})()');
  if (inputPosition) canvas.onclick({clientX: inputPosition.x*canvas.clientWidth/canvas.width, clientY: inputPosition.y*canvas.clientHeight/canvas.height});
  assert.equal(evaluate('selectedNote'), before);
  elements.get('nextNote').onclick();
  elements.get('previousNote').onclick();
  assert.equal(evaluate('selectedNote'), before);
  elements.get('position').value = '12';
  elements.get('position').oninput();
  assert.equal(evaluate('playhead'), 12);
  assert.equal(elements.get('chartPosition').textContent, '0:12.000');
}

elements.get('center').onclick();
elements.get('next').onclick();
elements.get('previous').onclick();
elements.get('excluded').checked = true;
elements.get('excluded').onchange();
elements.get('spacingScale').value = '8';elements.get('spacingScale').oninput();
const tableRowBeforePlayback=elements.get('events').children[0];
video.currentTime=12.1;video.paused=false;dispatch('play');dispatch('play');
assert.equal(videoCallbacks.size,1,'only one frame clock should run');
let [id,callback]=videoCallbacks.entries().next().value;videoCallbacks.delete(id);callback(0,{mediaTime:12.125});
assert.equal(evaluate('playhead'),12.125);
assert.equal(elements.get('chartPosition').textContent,'0:12.125');
video.playbackRate=.5;
[id,callback]=videoCallbacks.entries().next().value;videoCallbacks.delete(id);callback(0,{mediaTime:12.25});
assert.equal(evaluate('playhead'),12.25,'use presented media time, independently of playback speed');
video.currentTime=12.25;video.paused=true;dispatch('pause');assert.equal(videoCallbacks.size,0);
video.currentTime=14.125;dispatch('seeked');assert.equal(evaluate('playhead'),14.125);
video.requestVideoFrameCallback=undefined;video.paused=false;dispatch('play');assert.equal(animationCallbacks.size,1);
video.currentTime=14.25;
[id,callback]=animationCallbacks.entries().next().value;animationCallbacks.delete(id);callback(0);
assert.equal(evaluate('playhead'),14.25);
video.paused=true;dispatch('pause');assert.equal(animationCallbacks.size,0);
assert.equal(elements.get('events').children[0],tableRowBeforePlayback,'playback must not rebuild the note table');
assert.deepEqual(evaluate('data'), data, 'embedded evidence changed');
console.log(JSON.stringify({initialRows, correctedRows, details, targetRanges, initialInputs,
  initialDifferences, correctedInputs, correctedDifferences, verticalGeometry, verticalNotes}));
