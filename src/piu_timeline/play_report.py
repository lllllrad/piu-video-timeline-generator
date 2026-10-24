"""Self-contained, local HTML review of video-derived timing evidence."""
import html
import json
import os
import re
from pathlib import Path
from urllib.parse import quote


def write_report(data, path, final_directory=None):
    final_directory = Path(final_directory or path.parent)
    media = quote(os.path.relpath(data['media']['path'], final_directory), safe='/')
    encoded = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    title = html.escape(f"{data.get('song') or 'Unknown song'} · {data.get('chart') or 'Unknown chart'}")
    parts = {'TITLE': title, 'MEDIA': html.escape(media, quote=True), 'DATA': encoded}
    content = re.sub(r'__(TITLE|MEDIA|DATA)__', lambda match: parts[match[1]], TEMPLATE)
    path.write_text(content, encoding='utf-8')


TEMPLATE = r'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · Play timing</title>
<style>
:root{color-scheme:dark;--bg:#101719;--panel:#182326;--edge:#314448;--ink:#e5efeb;--muted:#9cb1b1;--green:#9cddbe;--blue:#75bdea;--amber:#f1c478}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,sans-serif}main{max-width:1440px;margin:auto;padding:32px}h1{font-size:clamp(24px,4vw,40px);font-weight:600;letter-spacing:-.04em;margin:8px 0}h2{font-size:18px;font-weight:600;margin:0 0 14px}.eyebrow{font-size:12px;letter-spacing:.14em;color:var(--green);text-transform:uppercase}.muted,small{color:var(--muted)}a{color:var(--green)}.panel{background:var(--panel);border:1px solid var(--edge);padding:22px;border-radius:12px;margin:18px 0}.grid{display:grid;grid-template-columns:1.15fr 1fr;gap:20px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.stat{padding:16px;background:var(--panel);border:1px solid var(--edge);border-radius:10px}.stat strong{display:block;font-size:27px;color:var(--green)}label{display:block;margin:12px 0}input,button,select,textarea{background:#102023;color:var(--ink);border:1px solid #486267;border-radius:5px;padding:8px;font:inherit}button{cursor:pointer}input[type=range]{width:min(360px,80%);vertical-align:middle}video{width:100%;max-height:430px;background:#080d0e}canvas{display:block;width:100%;height:290px;touch-action:none}.chart{position:relative}.chart small{display:block;margin-top:8px}.warning{border-left:3px solid var(--amber);padding:10px 15px;background:#2a2920}table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:9px;text-align:left;border-bottom:1px solid var(--edge)}tbody tr{cursor:pointer}tbody tr:hover{background:#21373b}.scroll{max-height:360px;overflow:auto}.preview{position:relative}.preview img{width:100%;display:block}.preview canvas{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}textarea{width:100%;min-height:180px;font:12px/1.5 monospace}.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center}.pill{display:inline-block;border:1px solid var(--edge);border-radius:20px;padding:3px 10px;font-size:12px;color:var(--muted)}@media(max-width:850px){main{padding:18px}.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}.panel{padding:15px}}
</style>
<main>
<div class="eyebrow">Video evidence / experimental play analysis</div><h1>__TITLE__</h1>
<p class="muted">Visible note trajectories compared with confirmed combo display changes. Source media and original frame timestamps are preserved.</p>
<p class="warning">Combo refresh is an input-time proxy. Physical switch timing and display latency are not measured. Offsets include display latency until you supply an external correction. No authoritative chart file is loaded.</p>
<div class="stats" id="stats"></div>
<div class="grid"><section class="panel"><h2>Original recording</h2><video id="video" controls preload="metadata" src="__MEDIA__"></video>
<label>Choose the original file if this browser cannot open its relative path <input id="file" type="file" accept="video/*,.mkv"></label><small>The file stays in this browser. Unsupported codecs may require another browser. Nothing is uploaded or re-encoded.</small>
<div class="row"><button id="begin">Go to play start</button><button id="previous">Previous match</button><button id="next">Next match</button><span id="clock" class="pill"></span></div></section>
<section class="panel"><h2>Timing evidence</h2><label>Display latency correction: <output id="delayValue"></output> ms<br><input id="delay" type="range" min="-500" max="500" step="1"></label>
<button id="center">Center observed median (relative alignment)</button><p class="muted">Positive correction subtracts a presumed display delay. Centering the median is a visualization aid, not a physical latency calibration. Associations stay fixed; use <code>--display-delay-ms</code> to rerun them.</p>
<div id="quality"></div><p><a href="analysis.json">Analysis JSON</a> · <a href="frames.jsonl">Native-frame observations</a> · <a href="evidence/bootstrap.json">Digit-template evidence</a></p></section></div>
<section class="panel chart"><h2>Observed timing offsets</h2><canvas id="timing" width="1200" height="290"></canvas><small>Each bar spans the last old-combo frame to the first new-combo frame. Blue: earlier than the fitted crossing; amber: later. Click to seek the recording. The table also reports fitted-target uncertainty. This is display-based evidence, not a judgment-window score.</small></section>
<section class="panel chart"><div class="row"><h2>Reconstructed visible chart</h2><label>Window <select id="zoom"><option value="3">±3 seconds</option><option value="8">±8 seconds</option><option value="15">±15 seconds</option></select></label><label><input id="excluded" type="checkbox"> Include excluded track endpoints</label></div><canvas id="lanes" width="1200" height="350"></canvas><small>Columns show fitted receptor-crossing times; rows show lanes. Only supported visible note heads are reconstructed. Holds, rolls and unreliable motion are not scored.</small></section>
<div class="grid"><section class="panel"><h2>Matched note heads</h2><div class="scroll"><table><thead><tr><th>Target</th><th>Lane</th><th>Fit uncertainty</th><th>Offset interval</th><th>Combo</th></tr></thead><tbody id="events"></tbody></table></div></section>
<section class="panel"><h2>Coverage and exclusions</h2><div id="exclusions"></div><ul id="limitations"></ul></section></div>
<details class="panel"><summary>Inspect or correct calibration</summary><p>Check receptor centers and combo crop against the original game panel. Download an edited layout and rerun with <code>--layout layout.json</code>. Geometry changes require reanalysis.</p><div class="preview"><img id="preview" src="preview.png" alt="Original gameplay calibration frame"><canvas id="overlay" width="1300" height="730"></canvas></div><textarea id="layout" spellcheck="false"></textarea><button id="download">Download layout.json</button><span id="layoutError"></span></details>
</main><script id="data" type="application/json">__DATA__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id),video=$('video');
let playhead=data.start_seconds,selected=-1,objectUrl=null;
const matches=data.matches,delay=$('delay');delay.value=data.display_delay_correction_ms||0;
const fmt=t=>{const m=Math.floor(t/60);return m+':'+(t-m*60).toFixed(3).padStart(6,'0')};
const offset=m=>[(m.raw_offset_lower_ms-Number(delay.value)),(m.raw_offset_upper_ms-Number(delay.value))];
const mid=m=>(m.raw_offset_lower_ms+m.raw_offset_upper_ms)/2;
const median=a=>{const b=[...a].sort((x,y)=>x-y);return b.length?(b[Math.floor((b.length-1)/2)]+b[Math.ceil((b.length-1)/2)])/2:0};
function text(tag,value,parent){const node=document.createElement(tag);node.textContent=value;parent.appendChild(node);return node}
for(const [name,value] of [['Result judgments (whole song)',data.result_reference?.total??'Unknown'],['Reconstructed note heads',data.notes.filter(n=>n.status==='estimated').length],['Heads with timing evidence',matches.length],['Matched combo refreshes',new Set(matches.map(m=>m.combo_event)).size]]){const node=text('div','',$('stats'));node.className='stat';text('strong',value,node);text('span',name,node)}
const coverage=text('p','Partial reconstruction: '+matches.length+' note heads have timing evidence. '+(data.result_reference?'The whole-song result contains '+data.result_reference.total+' judgments, including hold ticks; these are not the same unit as visible note heads.':'The complete chart/input count is unknown.')+' Missing matches are analysis gaps, not absent player inputs.',$('quality'));coverage.className='warning';
text('p','Native frames: '+data.frame_count+'. Combo readable: '+Math.round(100*data.combo_readable_fraction)+'%. Matched heads can share a combo refresh for a chord.',$('quality'));
text('p','Bootstrap OCR: '+data.bootstrap.ocr_images+' small images; all remaining combo reads use digit templates.',$('quality'));
text('p','Unlearned digits: '+(data.bootstrap.missing_digits.join(', ')||'none')+'. Median source frame interval: '+(1000*(data.median_frame_interval_seconds||0)).toFixed(1)+' ms.',$('quality'));
if(!matches.length){const p=text('p','No unambiguous matches. Check calibration and template coverage. This does not mean there were no inputs.',$('quality'));p.className='warning'}
for(const [reason,count] of Object.entries(data.excluded_notes))text('p',reason.replaceAll('_',' ')+': '+count,$('exclusions'));
const comboReasons={};for(const e of data.combo_events)if(e.status==='excluded')comboReasons[e.reason]=(comboReasons[e.reason]||0)+1;
for(const [reason,count] of Object.entries(comboReasons))text('p',reason.replaceAll('_',' ')+': '+count,$('exclusions'));
for(const limitation of data.limitations)text('li',limitation,$('limitations'));
function seek(t,index=-1){playhead=t;selected=index;try{video.currentTime=t}catch(_){}draw()}
$('file').onchange=()=>{if(objectUrl)URL.revokeObjectURL(objectUrl);if($('file').files[0]){objectUrl=URL.createObjectURL($('file').files[0]);video.src=objectUrl;video.load()}};
$('begin').onclick=()=>seek(data.start_seconds);$('previous').onclick=()=>{if(matches.length){selected=Math.max(0,selected-1);seek(matches[selected].target_seconds,selected)}};
$('next').onclick=()=>{if(matches.length){selected=Math.min(matches.length-1,selected+1);seek(matches[selected].target_seconds,selected)}};
video.addEventListener('loadedmetadata',()=>{video.currentTime=playhead});video.addEventListener('timeupdate',()=>{playhead=video.currentTime;draw()});
function background(canvas){const c=canvas.getContext('2d');c.clearRect(0,0,canvas.width,canvas.height);c.font='12px system-ui';c.fillStyle='#9cb1b1';c.strokeStyle='#314448';return c}
function timing(){const canvas=$('timing'),c=background(canvas),w=canvas.width,h=canvas.height,p=60;
const values=matches.flatMap(offset),range=Math.max(100,...values.map(Math.abs));const x=t=>p+(w-2*p)*(t-data.start_seconds)/(data.end_seconds-data.start_seconds),y=v=>h/2-(h/2-25)*v/range;
for(const v of [-range,0,range]){c.strokeStyle='#314448';c.beginPath();c.moveTo(p,y(v));c.lineTo(w-10,y(v));c.stroke();c.fillStyle='#9cb1b1';c.fillText(v.toFixed(0)+' ms',0,y(v)+4)}
for(const [i,m] of matches.entries()){const [lo,hi]=offset(m);c.strokeStyle=(lo+hi)/2<0?'#75bdea':'#f1c478';c.lineWidth=i===selected?4:2;c.beginPath();c.moveTo(x(m.target_seconds),y(lo));c.lineTo(x(m.target_seconds),y(hi));c.stroke();c.fillStyle=c.strokeStyle;c.fillRect(x(m.target_seconds)-2,y((lo+hi)/2)-2,4,4)}
c.strokeStyle='#9cddbe';c.lineWidth=1;c.beginPath();c.moveTo(x(playhead),0);c.lineTo(x(playhead),h);c.stroke();c.fillStyle='#9cb1b1';c.fillText(fmt(data.start_seconds),p,h-2);c.fillText(fmt(data.end_seconds),w-85,h-2);
canvas.onclick=e=>{const t=data.start_seconds+((e.clientX-canvas.getBoundingClientRect().left)/canvas.clientWidth*w-p)/(w-2*p)*(data.end_seconds-data.start_seconds);if(matches.length){let i=0;for(let j=1;j<matches.length;j++)if(Math.abs(matches[j].target_seconds-t)<Math.abs(matches[i].target_seconds-t))i=j;seek(matches[i].target_seconds,i)}}}
function lanes(){const canvas=$('lanes'),c=background(canvas),w=canvas.width,h=canvas.height,p=70,span=Number($('zoom').value),x=t=>p+(t-(playhead-span))/(2*span)*(w-p),step=(h-25)/data.layout.lanes.length;
for(let i=0;i<data.layout.lanes.length;i++){const y=15+step*i;c.fillStyle='#9cb1b1';c.fillText(data.layout.lanes[i].name||String(i+1),2,y+4);c.strokeStyle='#314448';c.beginPath();c.moveTo(p,y);c.lineTo(w,y);c.stroke()}
for(const note of data.notes){const t=note.target_seconds??note.points.at(-1)?.[0];if(t<playhead-span||t>playhead+span||note.status!=='estimated'&&!$('excluded').checked)continue;const y=15+note.lane*step;c.fillStyle=note.status!=='estimated'?'#647371':data.layout.lanes[note.lane].color==='blue'?'#75bdea':data.layout.lanes[note.lane].color==='yellow'?'#f1c478':'#e89cba';c.beginPath();c.arc(x(t),y,5,0,Math.PI*2);c.fill()}
c.strokeStyle='#9cddbe';c.beginPath();c.moveTo(x(playhead),0);c.lineTo(x(playhead),h);c.stroke();c.fillStyle='#9cb1b1';c.fillText(fmt(playhead-span),p,h-2);c.fillText(fmt(playhead+span),w-85,h-2);
canvas.onclick=e=>seek(playhead-span+((e.clientX-canvas.getBoundingClientRect().left)/canvas.clientWidth*w-p)/(w-p)*2*span)}
function table(){$('events').replaceChildren();for(const [i,m] of matches.entries()){const row=text('tr','',$('events')),[lo,hi]=offset(m);text('td',fmt(m.target_seconds),row);text('td',data.layout.lanes[data.notes[m.note].lane].name||String(data.notes[m.note].lane+1),row);text('td','±'+(1000*data.notes[m.note].prediction_uncertainty_seconds).toFixed(1)+' ms',row);text('td',lo.toFixed(1)+' … '+hi.toFixed(1)+' ms',row);const e=data.combo_events[m.combo_event];text('td',e.before+' → '+e.after+(m.row_note_count>1?' (shared chord bracket)':''),row);row.onclick=()=>seek(m.target_seconds,i)}}
function draw(){$('clock').textContent=fmt(playhead);$('delayValue').textContent=delay.value;timing();lanes()}
delay.oninput=()=>{table();draw()};$('center').onclick=()=>{delay.value=Math.round(median(matches.map(mid)));table();draw()};$('zoom').onchange=draw;$('excluded').onchange=draw;
$('layout').value=JSON.stringify(data.layout,null,2);$('download').onclick=()=>{try{const value=JSON.parse($('layout').value),url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='layout.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('layoutError').textContent=''}catch(e){$('layoutError').textContent=e.message}};
function overlay(){const canvas=$('overlay');canvas.width=$('preview').naturalWidth;canvas.height=$('preview').naturalHeight;const c=background(canvas),w=canvas.width,h=canvas.height;c.strokeStyle='#9cddbe';c.lineWidth=2;c.beginPath();c.moveTo(0,data.layout.receptor_y*h);c.lineTo(w,data.layout.receptor_y*h);c.stroke();for(const lane of data.layout.lanes){c.beginPath();c.moveTo(lane.x*w,data.layout.receptor_y*h);c.lineTo(lane.x*w,h*.95);c.stroke()}const [x,y,rw,rh]=data.layout.combo_roi;c.strokeStyle='#f1c478';c.strokeRect(x*w,y*h,rw*w,rh*h)}
$('preview').onload=overlay;if($('preview').complete&&$('preview').naturalWidth)overlay();table();draw();
</script></html>'''
