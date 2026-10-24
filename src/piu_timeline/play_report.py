"""Self-contained, local HTML review of video-derived timing evidence."""
import html
import json
import os
import re
from pathlib import Path
from urllib.parse import quote


def write_report(data, path, final_directory=None):
    from .play_holds import presentation
    data = presentation(data)
    from .play_ranges import timing_ranges, counter_frame_ranges
    ranges = timing_ranges(data)
    frames = path.with_name('frames.jsonl')
    if ranges['counts'].get('unknown') and frames.is_file():
        ranges = timing_ranges({**data, 'counter_frame_events': counter_frame_ranges(frames)})
    data = {**data, 'timing_ranges': ranges}
    final_directory = Path(final_directory or path.parent)
    media = quote(os.path.relpath(data['media']['path'], final_directory), safe='/')
    encoded = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    title = html.escape(f"{data.get('song') or 'Unknown song'} · {data.get('chart') or 'Unknown chart'}")
    parts = {'TITLE': title, 'MEDIA': html.escape(media, quote=True), 'DATA': encoded}
    content = re.sub(r'__(TITLE|MEDIA|DATA)__', lambda match: parts[match[1]], TEMPLATE)
    path.write_text(content, encoding='utf-8')
    path.with_name('timing-ranges.json').write_text(json.dumps(data['timing_ranges'], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_index(document, root):
    """List every metadata segment, including failures and incomplete analyses."""
    rows = []
    for number, segment in enumerate(document['segments'], 1):
        relative = f'segment-{number:03}'
        analysis = root / relative / 'analysis.json'
        title = html.escape(f"{segment.get('song') or 'Unknown song'} · {segment.get('chart') or 'Unknown chart'}")
        if analysis.is_file():
            from .play_holds import presentation
            data = presentation(json.loads(analysis.read_text()))
            coverage = data['coverage']
            cells = (f'<a href="{relative}/report.html">{title}</a>', str(coverage['visible_note_heads']),
                     str(coverage.get('long_notes', 0)), str(coverage['timed_note_heads']), str(coverage['matched_combo_updates']),str(coverage.get('judgment_only_note_heads',0)),
                     f"{100*data['combo_readable_fraction']:.0f}%", str(data['play_analysis_version']))
        else:
            cells = (title, 'Unavailable', 'Unavailable', 'Unavailable', 'Unavailable', 'Unavailable', 'Unavailable', 'Unavailable')
        rows.append('<tr><td>'+str(number)+'</td>'+''.join('<td>'+cell+'</td>' for cell in cells)+'</tr>')
    path = root / 'index.html'
    path.write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Play timing reports</title><style>body{font:16px/1.6 system-ui;max-width:1200px;margin:40px auto;padding:20px;background:#101719;color:#e5efeb}a{color:#9cddbe}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #314448}.scroll{overflow:auto}
</style>
<h1>Play timing reports</h1><p>Each report compares visible note trajectories with observed combo and judgment refreshes. A chord is one judged row and may contain several heads. Counts are partial reconstruction, not a complete chart or physical switch measurement. Open a report for excluded motion and unassigned counter evidence.</p>
<div class="scroll"><table><thead><tr><th>Segment</th><th>Play</th><th>Reconstructed heads</th><th>Long notes</th><th>Heads with tap timing</th><th>Matched combo refreshes</th><th>Judgment-only timed heads</th><th>Readable counter frames</th><th>Analyzer version</th></tr></thead><tbody>'''
                    + ''.join(rows) + '</tbody></table></div></html>', encoding='utf-8')
    return path


TEMPLATE = r'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · Play timing</title>
<style>
:root{color-scheme:dark;--bg:#101719;--panel:#182326;--edge:#314448;--ink:#e5efeb;--muted:#9cb1b1;--green:#9cddbe;--blue:#75bdea;--amber:#f1c478}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,sans-serif}main{max-width:1440px;margin:auto;padding:32px}h1{font-size:clamp(24px,4vw,40px);font-weight:600;letter-spacing:-.04em;margin:8px 0}h2{font-size:18px;font-weight:600;margin:0 0 14px}.eyebrow{font-size:12px;letter-spacing:.14em;color:var(--green);text-transform:uppercase}.muted,small{color:var(--muted)}a{color:var(--green)}.panel{background:var(--panel);border:1px solid var(--edge);padding:22px;border-radius:12px;margin:18px 0}.grid{display:grid;grid-template-columns:1.15fr 1fr;gap:20px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.stat{padding:16px;background:var(--panel);border:1px solid var(--edge);border-radius:10px}.stat strong{display:block;font-size:27px;color:var(--green)}label{display:block;margin:12px 0}input,button,select,textarea{background:#102023;color:var(--ink);border:1px solid #486267;border-radius:5px;padding:8px;font:inherit}button{cursor:pointer}input[type=range]{width:min(360px,80%);vertical-align:middle}video{width:100%;max-height:430px;background:#080d0e}canvas{display:block;width:100%;height:290px;touch-action:none}.chart{position:relative}.chart small{display:block;margin-top:8px}.warning{border-left:3px solid var(--amber);padding:10px 15px;background:#2a2920}table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:9px;text-align:left;border-bottom:1px solid var(--edge)}tbody tr{cursor:pointer}tbody tr:hover{background:#21373b}.scroll{max-height:360px;overflow:auto}.preview{position:relative}.preview img{width:100%;display:block}.preview canvas{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}textarea{width:100%;min-height:180px;font:12px/1.5 monospace}.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center}.pill{display:inline-block;border:1px solid var(--edge);border-radius:20px;padding:3px 10px;font-size:12px;color:var(--muted)}@media(max-width:850px){main{padding:18px}.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}.panel{padding:15px}}
.playback-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px;align-items:start}.playback-grid>.panel{min-width:0}.video-panel{position:sticky;top:18px}.playback-grid video{max-height:70vh}.chart-controls input[type=range]{width:150px}.chart-controls input[type=number]{width:90px}@media(max-width:1000px){.playback-grid{grid-template-columns:1fr}.video-panel{position:static}}
</style>
<main>
<div class="eyebrow">Video evidence / experimental play analysis</div><h1>__TITLE__</h1>
<p class="muted">Visible note trajectories compared with confirmed combo and judgment display changes. Source media and original frame timestamps are preserved.</p>
<p class="warning">Combo and judgment refreshes are input-time proxies. MISS is failure evidence and has no press timestamp. Physical switch timing and display latency are not measured. Offsets include display latency until you supply an external correction. No authoritative chart file is loaded. Long-note recognition is sustained-state evidence; hold ticks are not new presses.</p>
<div class="stats" id="stats"></div>
<div class="playback-grid"><section class="panel video-panel"><h2>Original recording</h2><video id="video" controls preload="metadata" src="__MEDIA__"></video>
<label>Choose the original file if this browser cannot open its relative path <input id="file" type="file" accept="video/*,.mkv"></label><small>The file stays in this browser. Unsupported codecs may require another browser. Nothing is uploaded or re-encoded.</small>
<div class="row"><button id="begin">Go to play start</button><button id="previous">Previous match</button><button id="next">Next match</button><span id="clock" class="pill"></span></div></section>
<section class="panel chart"><div class="row chart-controls"><h2>Vertical note chart</h2><label>Spacing <input id="spacingScale" type="range" min="0.05" max="16" step="0.01" value="1"> <input id="spacingInput" type="number" min="0.05" max="16" step="0.01" value="1" aria-label="Exact note spacing multiplier"> <output id="spacingValue">1.00×</output></label><label>Note size <input id="noteSize" type="range" min="16" max="64" step="1" value="32"> <output id="noteSizeValue">32 px</output></label><label><input id="excluded" type="checkbox"> Include excluded track endpoints</label></div>
<p class="muted">Earlier ↑ · later ↓. White ring: target. Amber point: input estimate. Solid range: matched; dashed range: possible. Long blue bodies: holds; amber strips: sustained recognition. Conditional neighbor bounds appear only in the table. The green line follows video playback.</p>
<div class="row"><button id="previousNote">Previous note</button><button id="nextNote">Next note</button><span id="chartPosition" class="pill"></span></div>
<label>Recording position <input id="position" type="range" step="0.001" style="width:100%"></label>
<div style="overflow-x:auto"><canvas id="lanes" width="1000" height="680" style="height:680px" aria-label="Vertical note chart: time increases downward, lanes from left to right"></canvas></div><small>Click an arrow or input range to select the note and seek the recording. Scroll through time with the recording-position slider, or play the video to follow the chart. White outlines mark the selected note. Gray crosses are excluded endpoints, not fitted timings. Long bodies are holds; amber spans show recognized held states, not repeated presses. Rolls and unreliable motion remain unresolved.</small></section>
</div>
<details class="panel"><summary>How to read the vertical chart</summary><p class="muted">Read from top to bottom: earlier notes above, later notes below. Columns follow the original lane order. Note size and spacing are independent. Play the video on the left to follow the same recording position in this chart. White points mark fitted judgment targets; blue bands show their uncertainty. Amber points and solid outlines show matched input ranges; dashed outlines show alternative refresh ranges, not confirmed inputs. Points at interval centers are visual guides, not subframe measurements. An amber mark above its arrow is early; below is late. The green line follows the recording.</p></details>
<section class="panel"><h2>Timing evidence</h2><label>Display latency correction: <output id="delayValue"></output> ms<br><input id="delay" type="range" min="-500" max="500" step="1"></label>
<button id="center">Center observed median (relative alignment)</button><p class="muted">Positive correction subtracts a presumed display delay. Centering the median is a visualization aid, not a physical latency calibration. Associations stay fixed; use <code>--display-delay-ms</code> to rerun them.</p>
<div id="quality"></div><p><a href="analysis.json">Analysis JSON</a> · <a href="timing-ranges.json">Per-note timing ranges</a> · <a href="holds.json">Long-note geometry and held-state evidence</a> · <a href="frames.jsonl">Native-frame observations</a> · <a href="evidence/bootstrap.json">Digit-template evidence</a> · <a href="judgments.jsonl">Judgment observations</a> · <a href="evidence/judgments/bootstrap.json">Word-template evidence</a></p></section>
<section class="panel chart"><h2>Observed timing offsets</h2><canvas id="timing" width="1200" height="290"></canvas><small>Each bar compares the input estimate with the note target range, including both frame-bracket and fitted-target uncertainty. Blue: earlier; amber: later; green: overlapping ranges. Click to select a note and seek the recording. This is display-based evidence, not a judgment-window score.</small></section>
<section class="panel chart"><h2>Selected note: target vs input</h2><p class="muted">Select a note in the table or chart. Blue is the video-estimated target range; amber is the input estimate from a display refresh, after the latency correction above. Both use the same time axis, centered on the fitted target. These are uncertainty ranges, not game judgment windows or authoritative chart timestamps.</p><canvas id="comparison" width="1200" height="180" style="height:180px"></canvas><div id="comparisonDetails" aria-live="polite"></div></section>
<section class="panel"><h2>Note timing comparison</h2><p class="muted">Times are absolute recording positions. Input − target includes uncertainty in both ranges: negative is early, positive is late. Overlapping ranges do not establish an early/late result. Unmatched notes show alternative observed refresh ranges or conditional bounds from neighboring processed rows; these do not establish an input assignment. When evidence is absent, the input stays unconfirmed; a possible MISS never supplies one. Chord heads share a refresh bracket; aggregate brackets can span several rows.</p><div class="scroll"><table><thead><tr><th>Note / lane</th><th>Target range (video estimate)</th><th>Input range (display estimate)</th><th>Input − target</th><th>Evidence / judgment</th></tr></thead><tbody id="events"></tbody></table></div></section>
<section class="panel"><h2>Coverage and exclusions</h2><div id="exclusions"></div><ul id="limitations"></ul></section>
<section class="panel"><h2>Observed combo updates, including unassigned evidence</h2><p class="muted">One increment represents a judged row. Chords share that row; counter jumps can contain several rows or hold ticks. An unassigned update is still observed evidence. Resets do not identify missed presses.</p><div class="scroll"><table><thead><tr><th>Observed bracket</th><th>Counter</th><th>Rows advanced</th><th>Association</th></tr></thead><tbody id="comboEvents"></tbody></table></div></section>
<section class="panel"><h2>Observed judgments, including counter-free evidence</h2><p class="muted">Word changes, reappearance after a confirmed blank, and animation restarts can establish display refreshes before combo 4 or after a break. A persistent word is not counted repeatedly. MISS is failure evidence, never a press timestamp.</p><div class="scroll"><table><thead><tr><th>Observed bracket</th><th>Judgment</th><th>Refresh evidence</th><th>Association</th></tr></thead><tbody id="judgmentEvents"></tbody></table></div></section>
<details class="panel"><summary>Inspect or correct calibration</summary><p>Check receptor centers and combo crop against the original game panel. Download an edited layout and rerun with <code>--layout layout.json</code>. Geometry changes require reanalysis.</p><div class="preview"><img id="preview" src="preview.png" alt="Original gameplay calibration frame"><canvas id="overlay" width="1300" height="730"></canvas></div><textarea id="layout" spellcheck="false"></textarea><button id="download">Download layout.json</button><span id="layoutError"></span></details>
</main><script id="data" type="application/json">__DATA__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id),video=$('video');
let playhead=data.start_seconds,selected=-1,objectUrl=null;
const matches=data.matches,delay=$('delay');delay.value=data.display_delay_correction_ms||0;
const fmt=t=>{const ms=Math.round(Math.abs(t)*1000),m=Math.floor(ms/60000);return (t<0?'-':'')+m+':'+((ms%60000)/1000).toFixed(3).padStart(6,'0')};
const matchByNote=new Map(matches.map((m,i)=>[m.note,{match:m,index:i}]));
const rangeByNote=data.timing_ranges?.notes||{};
const holds=data.hold_analysis?.holds||[],holdById=new Map(holds.map(hold=>[hold.id,hold]));
const holdFor=note=>note?.note_type==='hold'?holdById.get(note.hold_id):null;
const possibleMissNotes=new Set((data.miss_candidates||[]).map(candidate=>candidate.note));
const reviewNotes=data.notes.map((note,index)=>({note,index})).filter(({note})=>note.status==='estimated').sort((a,b)=>a.note.target_seconds-b.note.target_seconds);
let selectedNote=matches[0]?.note??reviewNotes[0]?.index??null;
if(selectedNote!==null)playhead=data.notes[selectedNote].target_seconds;
const targetRange=note=>Number.isFinite(note.target_seconds)&&Number.isFinite(note.prediction_uncertainty_seconds)
  ?[note.target_seconds-note.prediction_uncertainty_seconds,note.target_seconds+note.prediction_uncertainty_seconds]:null;
const observedRange=m=>{
  if(!m||m.judgment_label==='MISS')return null;
  const lo=m.observation_lower_seconds??m.combo_lower_seconds,hi=m.observation_upper_seconds??m.combo_upper_seconds;
  return Number.isFinite(lo)&&Number.isFinite(hi)&&lo<=hi?[lo,hi]:null;
};
const inputIntervals=(m,index=m?.note)=>{
const observed=observedRange(m),ranges=observed?[observed]:(rangeByNote[index]?.input_ranges||[]);
return ranges.map(range=>range.map(t=>t-Number(delay.value)/1000));
};
const inputRange=(m,index=m?.note)=>{const ranges=inputIntervals(m,index);return ranges.length?[ranges[0][0],ranges.at(-1)[1]]:null};
const difference=(target,input)=>target&&input?[1000*(input[0]-target[1]),1000*(input[1]-target[0])]:null;
const offset=m=>difference(targetRange(data.notes[m.note]),inputRange(m))??[NaN,NaN];
const formatRange=range=>range?range.map(fmt).join(' … '):'Unconfirmed';
const formatDifference=range=>range?range.map(v=>(v>0?'+':'')+v.toFixed(1)).join(' … ')+' ms':'Unconfirmed';
const alignment=range=>!range?'Unconfirmed':range[1]<0?'Earlier than target range':range[0]>0?'Later than target range':'Overlaps target range';
const mid=m=>(m.raw_offset_lower_ms+m.raw_offset_upper_ms)/2;
const median=a=>{const b=[...a].sort((x,y)=>x-y);return b.length?(b[Math.floor((b.length-1)/2)]+b[Math.ceil((b.length-1)/2)])/2:0};
function text(tag,value,parent){const node=document.createElement(tag);node.textContent=value;parent.appendChild(node);return node}
for(const [name,value] of [['Result judgments (whole song)',data.result_reference?.total??'Unknown'],['Reconstructed note heads',data.notes.filter(n=>n.status==='estimated').length],['Heads with timing evidence',matches.length],['Matched display refreshes',new Set(matches.map(m=>m.combo_event!=null?'combo:'+m.combo_event:'judgment:'+m.judgment_event)).size]]){const node=text('div','',$('stats'));node.className='stat';text('strong',value,node);text('span',name,node)}
text('p','Timing ranges: '+Object.entries(data.timing_ranges?.counts||{}).map(([status,count])=>status+': '+count).join(' / '),$('quality'));
const coverage=text('p','Partial reconstruction: '+matches.length+' note heads have timing evidence. '+(data.result_reference?'The whole-song result contains '+data.result_reference.total+' judgments, including hold ticks; these are not the same unit as visible note heads.':'The complete chart/input count is unknown.')+' Missing matches are analysis gaps, not absent player inputs.',$('quality'));coverage.className='warning';
text('p','Long notes: '+holds.length+'. Observed sustained-state spans: '+holds.reduce((total,hold)=>total+hold.input.segments.length,0)+'. Hold ticks are not independent presses; physical release is not measured.',$('quality'));
text('p','Native frames: '+data.frame_count+'. Combo readable: '+Math.round(100*data.combo_readable_fraction)+'%. Matched heads can share a combo refresh for a chord.',$('quality'));
text('p','Bootstrap OCR: '+data.bootstrap.ocr_images+' small images; all remaining combo reads use digit templates.',$('quality'));
text('p','Unlearned digits: '+(data.bootstrap.missing_digits.join(', ')||'none')+'. Median source frame interval: '+(1000*(data.median_frame_interval_seconds||0)).toFixed(1)+' ms.',$('quality'));
if(!matches.length){const p=text('p','No unambiguous matches. Check calibration and template coverage. This does not mean there were no inputs.',$('quality'));p.className='warning'}
for(const [reason,count] of Object.entries(data.excluded_notes))text('p',reason.replaceAll('_',' ')+': '+count,$('exclusions'));
const comboReasons={};for(const e of data.combo_events)if(e.status==='excluded')comboReasons[e.reason]=(comboReasons[e.reason]||0)+1;
for(const [reason,count] of Object.entries(comboReasons))text('p',reason.replaceAll('_',' ')+': '+count,$('exclusions'));
for(const e of data.combo_events){const row=text('tr','',$('comboEvents'));text('td',fmt(e.lower_seconds)+' … '+fmt(e.upper_seconds),row);text('td',e.before+' → '+e.after,row);text('td',e.delta>0?e.delta:'Reset',row);text('td',(e.reason||e.status).replaceAll('_',' '),row);row.onclick=()=>seek(e.upper_seconds)}
for(const e of data.judgment_events||[]){const row=text('tr','',$('judgmentEvents'));text('td',fmt(e.lower_seconds)+' … '+fmt(e.upper_seconds),row);text('td',e.label,row);text('td',e.trigger.replaceAll('_',' '),row);const missed=(data.miss_candidates||[]).filter(m=>data.judgment_events[m.judgment_event]===e);text('td',(e.reason||e.status).replaceAll('_',' ')+(missed.length?' / possible note lanes: '+missed.map(m=>data.layout.lanes[data.notes[m.note].lane].name||String(data.notes[m.note].lane+1)).join(', '):''),row);row.onclick=()=>seek(e.upper_seconds)}
text('p','Labeled timing heads: '+(data.coverage?.judgment_labeled_note_heads??matches.filter(m=>m.judgment_label).length)+'. Judgment unknown: '+(data.coverage?.unlabeled_timed_note_heads??matches.filter(m=>!m.judgment_label).length)+'. Labels from post-combo word frames: '+(data.coverage?.combo_frame_labeled_note_heads||0)+'.',$('quality'));
text('p','Judgment-only timed heads: '+(data.coverage?.judgment_only_note_heads||0)+'. Learned words: '+(data.judgment_template_labels||[]).join(', ')+'. Unlearned: '+((data.judgment_missing_labels||[]).join(', ')||'none')+'. New judgment OCR crops: '+(data.judgment_bootstrap_ocr_images||0)+'.',$('quality'));
for(const limitation of data.limitations)text('li',limitation,$('limitations'));
function seek(t,index=-1,noteIndex=null){playhead=t;selected=index;if(noteIndex!==null)selectedNote=noteIndex;else if(index>=0)selectedNote=matches[index].note;try{video.currentTime=t}catch(_){}draw()}
$('file').onchange=()=>{if(objectUrl)URL.revokeObjectURL(objectUrl);if($('file').files[0]){objectUrl=URL.createObjectURL($('file').files[0]);stopPlaybackClock();video.src=objectUrl;video.load()}};
$('begin').onclick=()=>seek(data.start_seconds);$('previous').onclick=()=>{if(matches.length){selected=Math.max(0,selected-1);seek(matches[selected].target_seconds,selected)}};
$('next').onclick=()=>{if(matches.length){selected=Math.min(matches.length-1,selected+1);seek(matches[selected].target_seconds,selected)}};
let playbackHandle=null,playbackMode=null;
function updatePlayback(time){if(Number.isFinite(time)){playhead=time;drawPlayback()}}
function stopPlaybackClock(){
if(playbackHandle!==null){if(playbackMode==='video')video.cancelVideoFrameCallback(playbackHandle);else cancelAnimationFrame(playbackHandle)}
playbackHandle=null;
}
function startPlaybackClock(){
if(video.paused||video.ended||playbackHandle!==null)return;
if(typeof video.requestVideoFrameCallback==='function'){
playbackMode='video';playbackHandle=video.requestVideoFrameCallback((_,frame)=>{playbackHandle=null;updatePlayback(frame.mediaTime);startPlaybackClock()});
}else{
playbackMode='animation';playbackHandle=requestAnimationFrame(()=>{playbackHandle=null;updatePlayback(video.currentTime);startPlaybackClock()});
}}
video.addEventListener('loadedmetadata',()=>{video.currentTime=playhead;draw()});
video.addEventListener('play',startPlaybackClock);
for(const event of ['pause','ended'])video.addEventListener(event,()=>{stopPlaybackClock();updatePlayback(video.currentTime)});
for(const event of ['seeking','seeked'])video.addEventListener(event,()=>{updatePlayback(video.currentTime);startPlaybackClock()});
video.addEventListener('timeupdate',()=>{if(video.paused||typeof video.requestVideoFrameCallback!=='function')updatePlayback(video.currentTime)});
function background(canvas){const c=canvas.getContext('2d');c.clearRect(0,0,canvas.width,canvas.height);c.font='12px system-ui';c.fillStyle='#9cb1b1';c.strokeStyle='#314448';return c}
function timing(){const canvas=$('timing'),c=background(canvas),w=canvas.width,h=canvas.height,p=60;
const values=matches.flatMap(offset).filter(Number.isFinite),range=Math.max(100,...values.map(Math.abs));const x=t=>p+(w-2*p)*(t-data.start_seconds)/(data.end_seconds-data.start_seconds),y=v=>h/2-(h/2-25)*v/range;
for(const v of [-range,0,range]){c.strokeStyle='#314448';c.beginPath();c.moveTo(p,y(v));c.lineTo(w-10,y(v));c.stroke();c.fillStyle='#9cb1b1';c.fillText(v.toFixed(0)+' ms',0,y(v)+4)}
for(const [i,m] of matches.entries()){const [lo,hi]=offset(m);if(!Number.isFinite(lo)||!Number.isFinite(hi))continue;c.strokeStyle=hi<0?'#75bdea':lo>0?'#f1c478':'#9cddbe';c.lineWidth=i===selected?4:2;c.beginPath();c.moveTo(x(m.target_seconds),y(lo));c.lineTo(x(m.target_seconds),y(hi));c.stroke();c.fillStyle=c.strokeStyle;c.fillRect(x(m.target_seconds)-2,y((lo+hi)/2)-2,4,4)}
c.strokeStyle='#9cddbe';c.lineWidth=1;c.beginPath();c.moveTo(x(playhead),0);c.lineTo(x(playhead),h);c.stroke();c.fillStyle='#9cb1b1';c.fillText(fmt(data.start_seconds),p,h-2);c.fillText(fmt(data.end_seconds),w-85,h-2);
canvas.onclick=e=>{const t=data.start_seconds+((e.clientX-canvas.getBoundingClientRect().left)/canvas.clientWidth*w-p)/(w-2*p)*(data.end_seconds-data.start_seconds);if(matches.length){let i=0;for(let j=1;j<matches.length;j++)if(Math.abs(matches[j].target_seconds-t)<Math.abs(matches[i].target_seconds-t))i=j;seek(matches[i].target_seconds,i)}}}
function laneGeometry(){
const canvas=$('lanes'),left=95,right=canvas.width-20,top=58,bottom=canvas.height-32;
const pixelsPerSecond=700*(Number($('spacingScale').value)||1),span=(bottom-top)/pixelsPerSecond/2;
const from=playhead-span,to=playhead+span,laneWidth=(right-left)/data.layout.lanes.length;
return {left,right,top,bottom,from,to,laneWidth,x:lane=>left+(lane+.5)*laneWidth,y:t=>top+(t-from)/(to-from)*(bottom-top)};
}
function lanes(){
const canvas=$('lanes'),minimumWidth=(115+data.layout.lanes.length*Math.max(40,noteSize()+12))+'px';if(canvas.style.minWidth!==minimumWidth)canvas.style.minWidth=minimumWidth;if(canvas.width!==canvas.clientWidth)canvas.width=canvas.clientWidth;
const c=background(canvas),g=laneGeometry(),w=canvas.width,h=canvas.height;
const symbols=['↙','↖','●','↗','↘'];
for(const [i,lane] of data.layout.lanes.entries()){
const left=g.left+i*g.laneWidth;
c.fillStyle=i%2?'#142124':'#192a2e';c.fillRect(left,g.top,g.laneWidth,g.bottom-g.top);
c.strokeStyle='#314448';c.lineWidth=1;c.beginPath();c.moveTo(left,g.top);c.lineTo(left,g.bottom);c.stroke();
c.fillStyle='#e5efeb';c.textAlign='center';c.font='13px system-ui';c.fillText(lane.name||String(i+1),g.x(i),24);
c.fillStyle=lane.color==='blue'?'#75bdea':lane.color==='yellow'?'#f1c478':'#e89cba';c.font='bold 20px system-ui';c.fillText(symbols[i%5],g.x(i),47);
}
c.textAlign='left';c.font='12px system-ui';
const tick=(g.to-g.from)<=.5?.025:(g.to-g.from)<=1?.1:(g.to-g.from)<=3?.25:(g.to-g.from)<=6?.5:1;
for(let t=Math.ceil(g.from/tick)*tick;t<=g.to;t+=tick){const y=g.y(t);c.strokeStyle='#314448';c.lineWidth=1;c.beginPath();c.moveTo(g.left,y);c.lineTo(g.right,y);c.stroke();c.fillStyle='#9cb1b1';c.fillText(fmt(t),0,y+4)}
c.strokeStyle='#9cddbe';c.lineWidth=2;c.beginPath();c.moveTo(g.left,g.y(playhead));c.lineTo(g.right,g.y(playhead));c.stroke();
const visible=t=>t>=g.from&&t<=g.to;
for(const hold of holds){
const start=hold.start_censored?hold.start_range[1]:(hold.start_range[0]+hold.start_range[1])/2;
const end=hold.end_range?(hold.end_range[0]+hold.end_range[1])/2:hold.last_body_seconds;
if(end<g.from||start>g.to)continue;
const x=g.x(hold.lane),bodyWidth=Math.max(8,noteSize()*.4),y1=Math.max(g.top,g.y(start)),y2=Math.min(g.bottom,g.y(end));
c.fillStyle='#245c76';c.fillRect(x-bodyWidth/2,y1,bodyWidth,Math.max(2,y2-y1));
c.strokeStyle='#75bdea';c.lineWidth=2;c.strokeRect(x-bodyWidth/2,y1,bodyWidth,Math.max(2,y2-y1));
if(visible(end)){c.fillStyle='#75bdea';c.fillRect(x-noteSize()*.4,g.y(end)-2,noteSize()*.8,4);if(hold.end_censored){c.font='12px system-ui';c.fillText('?',x+noteSize()*.45,g.y(end)+4)}}
const envelope=hold.input.recognition_envelope;
if(envelope){const lower=envelope[0]-Number(delay.value)/1000,upper=envelope[1]-Number(delay.value)/1000;
if(upper>=g.from&&lower<=g.to){c.strokeStyle='#b59762';c.lineWidth=3;c.setLineDash([4,4]);c.beginPath();c.moveTo(x+bodyWidth/2+6,Math.max(g.top,g.y(lower)));c.lineTo(x+bodyWidth/2+6,Math.min(g.bottom,g.y(upper)));c.stroke();c.setLineDash([])}}
for(const state of hold.input.segments){const lower=state.lower_seconds-Number(delay.value)/1000,upper=state.upper_seconds-Number(delay.value)/1000;
if(upper<g.from||lower>g.to)continue;
c.fillStyle='#f1c478';c.fillRect(x+bodyWidth/2+4,Math.max(g.top,g.y(lower)),5,Math.max(2,Math.min(g.bottom,g.y(upper))-Math.max(g.top,g.y(lower))));
}
}

const band=(range,x,width,filled,color)=>{if(!range||range[1]<g.from||range[0]>g.to)return;
const y1=Math.max(g.top,g.y(range[0])),y2=Math.min(g.bottom,g.y(range[1])),height=Math.max(2,y2-y1);
c.fillStyle=color;c.strokeStyle=color;c.lineWidth=2;if(filled)c.fillRect(x-width/2,y1,width,height);else c.strokeRect(x-width/2,y1,width,height);
};
for(const [index,note] of data.notes.entries()){
const t=note.target_seconds??note.points.at(-1)?.[0],x=g.x(note.lane),size=noteSize(),width=size+10;
if(note.status!=='estimated'){
if($('excluded').checked&&Number.isFinite(t)&&visible(t)){c.fillStyle='#647371';c.font='18px system-ui';c.textAlign='center';c.fillText('×',x,g.y(t)+6)}continue;
}
const target=targetRange(note),hold=holdFor(note),bounded=rangeByNote[index]?.status==='bounded',input=hold||bounded?null:inputRange(matchByNote.get(index)?.match,index);
if(!visible(t)&&(!input||input[1]<g.from||input[0]>g.to))continue;
band(target,x,width,true,'#244f66');
if(input){
c.strokeStyle='#f1c478';c.lineWidth=1;c.beginPath();c.moveTo(x,Math.max(g.top,Math.min(g.bottom,g.y(t))));c.lineTo(x,Math.max(g.top,Math.min(g.bottom,g.y((input[0]+input[1])/2))));c.stroke();
const possible=!matchByNote.has(index);c.setLineDash(possible?[5,4]:[]);
for(const range of inputIntervals(matchByNote.get(index)?.match,index)){
band(range,x,width+6,false,'#f1c478');}
c.setLineDash([]);
}
if(visible(t)){
const lane=data.layout.lanes[note.lane];c.fillStyle=lane.color==='blue'?'#75bdea':lane.color==='yellow'?'#f1c478':'#e89cba';c.textAlign='center';c.font='bold '+size+'px system-ui';c.fillText(hold?.start_censored?'?':symbols[note.lane%5],x,g.y(t)+size*.32);
if(!hold?.start_censored){c.strokeStyle='#ffffff';c.lineWidth=2;c.beginPath();c.arc(x,g.y(t),6,0,Math.PI*2);c.stroke();}
if(index===selectedNote){c.strokeStyle='#ffffff';c.lineWidth=2;c.strokeRect(x-width/2-6,g.y(t)-size*.55,width+12,size*1.1)}
}
for(const range of hold||bounded?[]:inputIntervals(matchByNote.get(index)?.match,index)){
const middle=(range[0]+range[1])/2;if(visible(middle)){c.fillStyle='#f1c478';c.beginPath();c.arc(x,g.y(middle),3,0,Math.PI*2);if(matchByNote.has(index))c.fill();else{c.strokeStyle='#f1c478';c.lineWidth=1;c.stroke()}}}
}
c.textAlign='left';c.font='12px system-ui';c.fillStyle='#9cddbe';c.fillText('Now '+fmt(playhead),g.left+6,g.y(playhead)-8);
canvas.onclick=e=>{
const rect=canvas.getBoundingClientRect(),px=(e.clientX-rect.left)/canvas.clientWidth*w,py=(e.clientY-rect.top)/canvas.clientHeight*h;
if(px<g.left||px>=g.right||py<g.top||py>g.bottom)return;
const lane=Math.floor((px-g.left)/g.laneWidth),t=g.from+(py-g.top)/(g.bottom-g.top)*(g.to-g.from);
const candidates=reviewNotes.filter(({note})=>note.lane===lane).map(item=>{
const ranges=inputIntervals(matchByNote.get(item.index)?.match,item.index);
const hold=holdFor(item.note),holdDistance=hold?Math.max((hold.start_censored?hold.start_range[1]:hold.start_range[0])-t,0,t-(hold.end_range?.[1]??hold.last_body_seconds)):Infinity;
const distance=Math.min(Math.abs(item.note.target_seconds-t),holdDistance,...ranges.map(range=>Math.max(range[0]-t,0,t-range[1])));
return {...item,distance};
}).filter(item=>item.distance<(g.to-g.from)*.035).sort((a,b)=>a.distance-b.distance||Math.abs(a.note.target_seconds-t)-Math.abs(b.note.target_seconds-t));
const closest=candidates[0];
if(closest)seek(closest.note.target_seconds,matchByNote.get(closest.index)?.index??-1,closest.index);else seek(t);
};
}
function noteSize(){return Number($('noteSize').value)||32}
function setSpacing(value){
if(!Number.isFinite(value))return;
const scale=Math.max(.05,Math.min(16,value)).toFixed(2);
$('spacingScale').value=scale;$('spacingInput').value=scale;$('spacingValue').textContent=scale+'×';draw();
}
$('spacingScale').oninput=()=>setSpacing(Number($('spacingScale').value));
$('spacingInput').oninput=()=>{if($('spacingInput').value.trim())setSpacing(Number($('spacingInput').value))};
$('noteSize').oninput=()=>{$('noteSizeValue').textContent=noteSize()+' px';draw()};
$('position').min=data.start_seconds;$('position').max=data.end_seconds;
$('position').oninput=()=>seek(Number($('position').value));
function stepNote(direction){
const current=reviewNotes.findIndex(item=>item.index===selectedNote);
const index=Math.max(0,Math.min(reviewNotes.length-1,current+direction));
const item=reviewNotes[index];if(item)seek(item.note.target_seconds,matchByNote.get(item.index)?.index??-1,item.index);
}
$('previousNote').onclick=()=>stepNote(-1);$('nextNote').onclick=()=>stepNote(1);
function comparison(){
const canvas=$('comparison'),c=background(canvas),w=canvas.width,p=180,right=w-35,center=(p+right)/2;
$('comparisonDetails').replaceChildren();
const note=data.notes[selectedNote];
if(!note){c.fillText('No supported target ranges to compare.',p,70);return}
const match=matchByNote.get(selectedNote)?.match,hold=holdFor(note),target=hold?[hold.start_censored?hold.start_range[1]:hold.start_range[0],hold.end_range?.[1]??hold.last_body_seconds]:targetRange(note),input=inputRange(match,selectedNote),delta=difference(target,input);
const extent=Math.max(100,...[...(target||[]),...(input||[])].map(t=>Math.abs(1000*(t-note.target_seconds))))*1.15;
const x=t=>center+1000*(t-note.target_seconds)/extent*(right-p)/2;
for(const ms of [-extent,0,extent]){const px=center+ms/extent*(right-p)/2;c.strokeStyle='#314448';c.lineWidth=1;c.beginPath();c.moveTo(px,15);c.lineTo(px,135);c.stroke();c.fillStyle='#9cb1b1';c.fillText(ms.toFixed(1)+' ms',px-25,160)}
for(const [label,range,color,y] of [['Target (video)',target,'#75bdea',45],['Input (display)',input,'#f1c478',105]]){
c.fillStyle=color;c.fillText(label,5,y+4);
if(range){c.strokeStyle=color;c.lineWidth=8;c.setLineDash(!hold&&!match&&label==='Input (display)'?[5,4]:[]);
for(const part of label==='Input (display)'?inputIntervals(match,selectedNote):[range]){c.beginPath();c.moveTo(x(part[0]),y);c.lineTo(x(part[1]),y);c.stroke();for(const t of part)c.fillRect(x(t)-1,y-9,2,18)}c.setLineDash([])}
else c.fillText('Unconfirmed — no press timestamp',p,y+4);
}
text('p','Note '+(selectedNote+1)+' / '+(data.layout.lanes[note.lane].name||String(note.lane+1))+' · Target: '+formatRange(target)+' · Input: '+(inputIntervals(match,selectedNote).map(formatRange).join(' ∪ ')||'Unconfirmed'),$('comparisonDetails'));
if(hold){text('p','Long note / sustained recognition. Start: '+(hold.start_censored?'before first body contact (censored)':formatRange(hold.start_range))+' · End: '+(hold.end_range?formatRange(hold.end_range):'Unconfirmed / body ends outside reliable tracking'),$('comparisonDetails'));text('p','Holding is sufficient. Recognition spans do not represent repeated presses. Physical press and release times remain unmeasured.',$('comparisonDetails'));return}
const differences=inputIntervals(match,selectedNote).map(range=>difference(target,range));
text('p','Input − target: '+(differences.map(formatDifference).join(' ∪ ')||'Unconfirmed')+' · '+(differences.length>1?'Alternative intervals':alignment(delta)),$('comparisonDetails'));
if(rangeByNote[selectedNote]?.rejected_candidates?.length)text('p','Rejected nearby refreshes: '+rangeByNote[selectedNote].rejected_candidates.map(reason=>reason.replaceAll('_',' ')).join('; '),$('comparisonDetails'));
const aggregateCapacity=Math.max(1,...(rangeByNote[selectedNote]?.alternatives||[]).map(event=>event.aggregate_row_capacity||1));if(aggregateCapacity>1)text('p','Counter evidence advances up to '+aggregateCapacity+' judged rows in one observation bracket. The aggregate bracket is shared; individual input times are unresolved.',$('comparisonDetails'));
const alternativeRows=Math.max(1,...(rangeByNote[selectedNote]?.alternatives||[]).map(event=>event.alternative_rows||1));if(alternativeRows>1)text('p','One refresh remains compatible with '+alternativeRows+' neighboring rows within source-frame and fitting uncertainty. These are alternatives, not separate input assignments.',$('comparisonDetails'));
if(!match)text('p',rangeByNote[selectedNote]?.status==='possible'?'Possible refresh ranges only: association is unresolved. Separate intervals are alternatives, not a continuous input window.':rangeByNote[selectedNote]?.status==='bounded'?'Conditional bounds from neighboring processed rows. A press is not established; chart-row input order is assumed.':'Input unknown: '+(rangeByNote[selectedNote]?.reason||'no matched evidence').replaceAll('_',' '),$('comparisonDetails'));
if(match?.aggregate_row_count>1)text('p','Aggregate refresh bracket shared by several rows; individual press times are unresolved.',$('comparisonDetails'));
}
function table(){
$('events').replaceChildren();
for(const {note,index} of reviewNotes){
const linked=matchByNote.get(index),m=linked?.match,target=targetRange(note),input=inputRange(m,index),delta=difference(target,input),row=text('tr','',$('events'));
const hold=holdFor(note);
if(hold){
text('td','HOLD #'+(hold.id+1)+' / '+(data.layout.lanes[note.lane].name||String(note.lane+1)),row);
text('td','Start: '+(hold.start_censored?'already visible / uncertain':formatRange(hold.start_range))+' · End: '+(hold.end_range?formatRange(hold.end_range):'Unconfirmed'),row);
text('td',inputIntervals(m,index).map(formatRange).join(' ∪ ')||'Held state unconfirmed',row);
text('td','Sustained state; no repeated presses',row);text('td','Receptor/body evidence · physical release unknown',row);
row.onclick=()=>seek(note.target_seconds,-1,index);continue;
}
text('td','#'+(index+1)+' / '+(data.layout.lanes[note.lane].name||String(note.lane+1)),row);
text('td',formatRange(target),row);text('td',inputIntervals(m,index).map(formatRange).join(' ∪ ')||'Unconfirmed',row);const differences=inputIntervals(m,index).map(range=>difference(target,range));text('td',(differences.map(formatDifference).join(' ∪ ')||'Unconfirmed')+' / '+(differences.length>1?'Alternative intervals':alignment(delta)),row);
const e=m?.combo_event!=null?data.combo_events[m.combo_event]:null;
const possibleMiss=possibleMissNotes.has(index);
text('td',m?(e?e.before+' → '+e.after:'Judgment only')+(m.judgment_label?' / '+m.judgment_label+(m.judgment_label_source==='post_combo_frames'?' (word frames)':''):' / Judgment unknown')+(m.aggregate_row_count>1?' (aggregate row bracket)':m.row_note_count>1?' (shared chord bracket)':''):possibleMiss?'Possible MISS / no press timestamp':rangeByNote[index]?.status==='possible'?'Possible refresh ranges / association unresolved':rangeByNote[index]?.status==='bounded'?'Conditional bounds between processed rows / press unconfirmed':'Input unknown / '+(rangeByNote[index]?.reason||'no_nearby_positive_refresh').replaceAll('_',' '),row);
row.onclick=()=>seek(note.target_seconds,linked?.index??-1,index);
}}
function drawPlayback(){$('position').value=playhead;$('chartPosition').textContent=fmt(playhead);$('clock').textContent=fmt(playhead);lanes()}
function draw(){$('delayValue').textContent=delay.value;drawPlayback();timing();comparison()}
delay.oninput=()=>{table();draw()};$('center').onclick=()=>{delay.value=Math.round(median(matches.map(mid)));table();draw()};$('excluded').onchange=draw;
$('layout').value=JSON.stringify(data.layout,null,2);$('download').onclick=()=>{try{const value=JSON.parse($('layout').value),url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='layout.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('layoutError').textContent=''}catch(e){$('layoutError').textContent=e.message}};
function overlay(){const canvas=$('overlay');canvas.width=$('preview').naturalWidth;canvas.height=$('preview').naturalHeight;const c=background(canvas),w=canvas.width,h=canvas.height;c.strokeStyle='#9cddbe';c.lineWidth=2;c.beginPath();c.moveTo(0,data.layout.receptor_y*h);c.lineTo(w,data.layout.receptor_y*h);c.stroke();for(const lane of data.layout.lanes){c.beginPath();c.moveTo(lane.x*w,data.layout.receptor_y*h);c.lineTo(lane.x*w,h*.95);c.stroke()}const [x,y,rw,rh]=data.layout.combo_roi;c.strokeStyle='#f1c478';c.strokeRect(x*w,y*h,rw*w,rh*h);if(data.judgment_roi){const [jx,jy,jw,jh]=data.judgment_roi;c.strokeStyle='#75bdea';c.strokeRect(jx*w,jy*h,jw*w,jh*h)}}
$('preview').onload=overlay;if($('preview').complete&&$('preview').naturalWidth)overlay();table();draw();
</script></html>'''
