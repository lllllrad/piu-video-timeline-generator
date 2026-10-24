// Execute the shipped inline report code with observable DOM/canvas substitutes.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(process.argv[2], 'utf8');
const payload = html.match(/<script id="data" type="application\/json">(.*?)<\/script>/s)[1];
const runtime = html.match(/<script>\s*(.*?)<\/script>/s)[1];
function element(tag) {
  return {tag, children: [], textContent: '', value: '', width: 1200, height: 350,
    clientWidth: 1200, clientHeight: 350, complete: false, files: [],
    appendChild(node) { this.children.push(node); return node; },
    replaceChildren() { this.children = []; }, addEventListener() {},
    getBoundingClientRect() { return {left: 0, top: 0}; },
    getContext() {
      return new Proxy({}, {get: (object, key) => object[key] ?? ((...args) => {
        for (const value of args) if (typeof value === 'number') assert.ok(Number.isFinite(value), key+' has invalid geometry');
      })});
    }
  };
}
const elements = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(match => [match[1], element(match[1])]));
elements.get('data').textContent = payload;
elements.get('zoom').value = '3';
const context = vm.createContext({document: {
  getElementById(id) { assert.ok(elements.has(id), 'missing element '+id); return elements.get(id); },
  createElement: element,
}, URL, Blob, setTimeout});
vm.runInContext(runtime, context, {timeout: 10000});
const evaluate = expression => JSON.parse(vm.runInContext('JSON.stringify('+expression+')', context));
const rows = () => elements.get('events').children.map(row => row.children.map(cell => cell.textContent));
const initialRows = rows();
const data = JSON.parse(payload);
assert.equal(initialRows.length, data.notes.filter(note => note.status === 'estimated').length);
const targetRanges = evaluate('reviewNotes.map(({note})=>targetRange(note))');
const initialInputs = evaluate('reviewNotes.map(({index})=>inputRange(matchByNote.get(index)?.match))');
const initialDifferences = evaluate('reviewNotes.map(({note,index})=>difference(targetRange(note),inputRange(matchByNote.get(index)?.match)))');
elements.get('delay').value = '30';
elements.get('delay').oninput();
const correctedRows = rows();
const correctedInputs = evaluate('reviewNotes.map(({index})=>inputRange(matchByNote.get(index)?.match))');
const correctedDifferences = evaluate('reviewNotes.map(({note,index})=>difference(targetRange(note),inputRange(matchByNote.get(index)?.match)))');
const details = [];
for (const index of [...new Set([0, initialRows.length - 1])]) {
  if (!elements.get('events').children[index]) continue;
  elements.get('events').children[index].onclick();
  details.push(elements.get('comparisonDetails').children.map(node => node.textContent));
}
if (initialRows.length) {
  elements.get('events').children[0].onclick();
  // The selected target is centered in its lane chart; clicking must retain it.
  const lane = evaluate('data.notes[selectedNote].lane');
  const before = evaluate('selectedNote');
  elements.get('lanes').onclick({clientX: (70+1200)/2, clientY: 15+lane*(350-25)/data.layout.lanes.length});
  assert.equal(evaluate('selectedNote'), before);
}
elements.get('center').onclick();
elements.get('next').onclick();
elements.get('previous').onclick();
elements.get('excluded').checked = true;
elements.get('excluded').onchange();
elements.get('zoom').value = '8';
elements.get('zoom').onchange();
assert.deepEqual(evaluate('data'), data, 'embedded evidence changed');
console.log(JSON.stringify({initialRows, correctedRows, details, targetRanges, initialInputs,
  initialDifferences, correctedInputs, correctedDifferences}));
