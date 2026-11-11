/** Pure HTML presentation. The input document has already been analyzed. */
import {readFileSync,statSync,openSync,readSync,writeSync,closeSync} from 'node:fs';
import {basename,dirname} from 'node:path';
import {StringDecoder}from 'node:string_decoder';
const resource = name => readFileSync(new URL(`../play/${name}`, import.meta.url), 'utf8');
const template = resource('report.html').replace('__STYLE__', () => resource('report.css') + '\n' + resource('inspector/workspace.css'))
  .replace('__SCRIPT__', () => ['report-evidence.js', 'inspector/warning-groups.js', 'inspector/navigation.js', 'inspector/provenance.js', 'inspector/overlay.js', 'report.js'].map(resource).join('\n'));
const escape = (value: string) => value.replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#x27;'}[c]));

export function render(dataJSON: string, song: string, chart: string, media: string): string {
  const parts = {TITLE: escape(`${song} · ${chart}`), MEDIA: escape(media),
    DATA: dataJSON.replace(/[<>&]/g, c => ({'<': '\\u003c', '>': '\\u003e', '&': '\\u0026'}[c]))};
  return template.replace(/__(TITLE|MEDIA|DATA)__/g, (_match, name) => parts[name]);
}

/** Copy prepared JSON into HTML in bounded chunks; no analysis or giant JS string. */
export function renderFile(dataPath:string,outputPath:string,song:string,chart:string,media:string):void{
  const [before,after]=template.split('__DATA__').map(part=>part.replace(/__(TITLE|MEDIA)__/g,
    (_match,name)=>name==='TITLE'?escape(`${song} · ${chart}`):escape(media)));
  const source=openSync(dataPath,'r');let target:number;
  const bytes=Buffer.alloc(65536),decoder=new StringDecoder('utf8');
  const write=(text:string)=>{
    const encoded=Buffer.from(text);let offset=0;
    while(offset<encoded.length)offset+=writeSync(target,encoded,offset,encoded.length-offset);
  };
  const safe=(text:string)=>text.replace(/[<>&]/g,c=>({'<':'\\u003c','>':'\\u003e','&':'\\u0026'}[c]));
  try{
    target=openSync(outputPath,'wx');
    write(before);
    for(;;){const count=readSync(source,bytes,0,bytes.length,null);if(!count)break;write(safe(decoder.write(bytes.subarray(0,count))));}
    write(safe(decoder.end()));write(after);
  }finally{closeSync(source);if(target!==undefined)closeSync(target);}
}

export function index(entries): string {
  const rows = entries.map(({number, song, chart, summary}) => {
    const title = escape(`${song || 'Unknown song'} · ${chart || 'Unknown chart'}`), directory = `segment-${String(number).padStart(3, '0')}`;
    const c = summary?.coverage;
    const cells = c ? [`<a href="${directory}/report.html">${title}</a>`, c.visible_note_heads, c.long_notes ?? 0, c.timed_note_heads, c.matched_combo_updates,
      c.judgment_only_note_heads ?? 0, `${Math.round(100 * summary.combo_readable_fraction)}%`, summary.play_analysis_version] : [title, ...Array(7).fill('Unavailable')];
    return `<tr><td>${number}</td>${cells.map((cell, i) => `<td>${i === 0 ? cell : escape(String(cell))}</td>`).join('')}</tr>`;
  });
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Play evidence inspector</title><style>body{font:16px/1.6 system-ui;max-width:1200px;margin:40px auto;padding:20px;background:#101719;color:#e5efeb}
a{color:#9cddbe}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #314448}.scroll{overflow:auto}</style>
<h1>Play evidence inspector</h1><p>Each play compares visible note trajectories with observed combo and judgment refreshes. A chord is one judged row and may contain several heads. Counts are partial reconstruction, not a complete chart or physical switch measurement. Open a play for excluded motion and unassigned counter evidence.</p>
<div class="scroll"><table><thead><tr><th>Segment</th><th>Play</th><th>Reconstructed heads</th><th>Long notes</th><th>Heads with tap timing</th><th>Matched combo refreshes</th><th>Judgment-only timed heads</th><th>Readable counter frames</th><th>Analyzer version</th></tr></thead><tbody>${rows.join('')}</tbody></table></div></html>`;
}

/** Standalone bounded summary; detailed inspection is a separate optional editor. */
export function renderShellFile(dataPath:string,outputPath:string,song:string,chart:string,media:string,provided?:any):void{
 let summary=provided;
 if(!summary){
  // A stale or missing sidecar must never present old metrics as current evidence.
  const path=dirname(dataPath)+'/report-summary.json';
  try{if(statSync(path).mtimeMs>=statSync(dataPath).mtimeMs)summary=JSON.parse(readFileSync(path,'utf8'));}catch{}
 }
 const title=escape(`${song} · ${chart}`),value=(v:unknown)=>escape(v==null?'Unavailable':String(v));
 const source=basename(dirname(dirname(dirname(dataPath)))),segment=Number(basename(dirname(dataPath)).match(/segment-(\d+)/)?.[1])||1;
 const query=`?source=${encodeURIComponent(source)}&segment=${segment}`;
 const command=escape(`just editor '${source.replaceAll("'","'\"'\"'")}' --segment ${segment}`);
 const c=summary?.coverage??{};
 const metrics=[['Visible note heads',c.visible_note_heads],['Long notes',c.long_notes],['Heads with tap timing',c.timed_note_heads],
  ['Matched combo updates',c.matched_combo_updates],['Judgment-only timed heads',c.judgment_only_note_heads],
  ['Readable counter frames',typeof summary?.combo_readable_fraction==='number'?`${(100*summary.combo_readable_fraction).toFixed(1)}%`:null],
  ['Recognition / exclusion warnings',summary?.warning_count],['Analyzer version',summary?.play_analysis_version]];
 const warnings=summary?.warnings??[];
 const warningRows=warnings.map(w=>`<tr><td>${value(w.reason??w.check)}</td><td>${value(w.lane==null?null:w.lane+1)}</td><td>${value(w.visible_start_seconds??w.start_seconds)}</td><td>${value(w.visible_end_seconds??w.end_seconds)}</td></tr>`).join('');
 const body=`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title} · Play report</title><style>body{font:16px/1.6 system-ui;background:#101719;color:#e7efed;max-width:1000px;margin:40px auto;padding:24px}
a{color:#a9dec2;text-underline-offset:3px}code{background:#192226;padding:4px;overflow-wrap:anywhere}h1{font-size:26px}h2{font-size:20px;margin-top:36px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}td,th{padding:10px;text-align:left;border-bottom:1px solid #314448}
th{font-weight:500}.scroll{overflow:auto}::selection{background:#a9dec2;color:#101719}:focus-visible{outline:2px solid #a9dec2;outline-offset:4px}</style>
<main><h1>${title}</h1><p>Original recording interval: ${value(summary?.start_seconds)}–${value(summary?.end_seconds)} seconds.</p>
<p>This report opens without an editor server. Counts describe partial automatic reconstruction; they are not recognition accuracy or independently reviewed chart truth.</p>
<h2>Analysis summary</h2>${summary?'':'<p>Summary unavailable. Regenerate this report from the prepared analysis to populate the summary.</p>'}
<table><tbody>${metrics.map(([label,v])=>`<tr><th scope="row">${label}</th><td>${value(v)}</td></tr>`).join('')}</tbody></table>
<h2>Warnings</h2><p>${value(summary?.warning_count)} saved warnings. Showing ${warnings.length} representative records, capped at 30. Missing times remain unavailable.</p>
${warnings.length?`<div class="scroll"><table><thead><tr><th>Reason / check</th><th>Lane</th><th>Start seconds</th><th>End seconds</th></tr></thead><tbody>${warningRows}</tbody></table></div>`:'<p>No warning examples available in this summary.</p>'}
<h2>Detailed review</h2><p><a id="editor" href="http://127.0.0.1:4180/${escape(query)}">Open interval editor</a> · <a id="recording" href="${escape(media)}">Original recording</a></p>
<p>The editor provides video, chart evidence and saved corrections. Start it with <code>${command}</code>. Use <code>--host ADDRESS</code> for a different bind address, then open that address in your browser.</p>
<p>Original media and timestamps are preserved. This page embeds only the bounded summary above.</p></main>
<script>if(location.protocol==='http:'||location.protocol==='https:'){document.getElementById('editor').href='/'+${JSON.stringify(query).replace(/</g,'\\u003c')};document.getElementById('recording').href='/media'+${JSON.stringify(query).replace(/</g,'\\u003c')};}</script></html>`;
 const target=openSync(outputPath,'wx');try{const bytes=Buffer.from(body);let offset=0;while(offset<bytes.length)offset+=writeSync(target,bytes,offset,bytes.length-offset);}finally{closeSync(target);}
}
