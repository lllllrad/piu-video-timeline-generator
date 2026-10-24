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
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,sans-serif}main{margin:auto;padding:12px}h1{font-size:clamp(24px,4vw,40px);font-weight:600;letter-spacing:-.04em;margin:8px 0}h2{font-size:18px;font-weight:600;margin:0 0 14px}.eyebrow{font-size:12px;letter-spacing:.14em;color:var(--green);text-transform:uppercase}.muted,small{color:var(--muted)}a{color:var(--green)}.panel{background:var(--panel);border:1px solid var(--edge);padding:22px;border-radius:12px;margin:18px 0}.grid{display:grid;grid-template-columns:1.15fr 1fr;gap:20px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.stat{padding:16px;background:var(--panel);border:1px solid var(--edge);border-radius:10px}.stat strong{display:block;font-size:27px;color:var(--green)}label{display:block;margin:12px 0}input,button,select,textarea{background:#102023;color:var(--ink);border:1px solid #486267;border-radius:5px;padding:8px;font:inherit}button{cursor:pointer}input[type=range]{width:min(360px,80%);vertical-align:middle}video{width:100%;max-height:430px;background:#080d0e}svg{display:block;width:100%;height:290px;touch-action:none;overflow:hidden;font-family:system-ui,sans-serif}svg text{pointer-events:none}svg [data-note]{cursor:pointer}.chart{position:relative}.chart small{display:block;margin-top:8px}.warning{border-left:3px solid var(--amber);padding:10px 15px;background:#2a2920}table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:9px;text-align:left;border-bottom:1px solid var(--edge)}tbody tr{cursor:pointer}tbody tr:hover{background:#21373b}.scroll{max-height:360px;overflow:auto}.preview{position:relative}.preview img{width:100%;display:block}.preview svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}textarea{width:100%;min-height:180px;font:12px/1.5 monospace}.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center}.pill{display:inline-block;border:1px solid var(--edge);border-radius:20px;padding:3px 10px;font-size:12px;color:var(--muted)}@media(max-width:850px){main{padding:8px}.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}.panel{padding:15px}}
.playback-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;align-items:start}.playback-grid>.panel{min-width:0;padding:12px}.playback-grid>.chart{padding:8px}.chart-controls{gap:8px}.chart-controls label{display:flex;flex-wrap:wrap;align-items:center;gap:4px;max-width:100%;min-width:0;margin:4px 0}.chart-viewport{width:100%;min-width:0}.video-panel input[type=file]{max-width:100%}.video-panel{position:sticky;top:18px}.playback-grid video{max-height:70vh}.chart-controls input[type=range]{width:150px}.chart-controls input[type=number]{width:90px}@media(max-width:1000px){.playback-grid{grid-template-columns:1fr}.video-panel{position:static}}
</style>
<main>
<div class="eyebrow">Video evidence / experimental play analysis</div><h1>__TITLE__</h1>
<p class="muted">Visible note trajectories compared with confirmed combo and judgment display changes. Source media and original frame timestamps are preserved.</p>
<p class="warning">Combo and judgment refreshes are input-time proxies. MISS is failure evidence and has no press timestamp. Physical switch timing and display latency are not measured. Offsets include display latency until you supply an external correction. No authoritative chart file is loaded. Long-note recognition is sustained-state evidence; hold ticks are not new presses.</p>
<div class="stats" id="stats"></div>
<div class="playback-grid"><section class="panel video-panel"><h2>Original recording</h2><video id="video" controls preload="metadata" src="__MEDIA__"></video>
<label>Choose the original file if this browser cannot open its relative path <input id="file" type="file" accept="video/*,.mkv"></label><small>The file stays in this browser. Unsupported codecs may require another browser. Nothing is uploaded or re-encoded.</small>
<div class="row"><button id="begin">Go to play start</button><button id="previous">Previous match</button><button id="next">Next match</button><span id="clock" class="pill"></span></div></section>
<section class="panel chart"><div class="row chart-controls"><h2>Vertical note chart</h2><label>Spacing <input id="spacingScale" type="range" min="0.05" max="16" step="0.01" value="1"> <input id="spacingInput" type="number" min="0.05" max="16" step="0.01" value="1" aria-label="Exact note spacing multiplier"> <output id="spacingValue">1.00×</output></label><label>Note size <input id="noteSize" type="range" min="8" max="64" step="1" value="24"> <output id="noteSizeValue">24 px</output></label><label><input id="excluded" type="checkbox"> Include excluded track endpoints</label><label><input id="candidates" type="checkbox"> Show candidate connections</label></div>
<p class="muted">Earlier ↑ · later ↓. Fixed colored squares: notes. Lime left: chart target range. Magenta right: input range. Matched inputs are shown by default; candidate connections are optional (early ≤250 ms, late ≤500 ms). Long bodies: holds; magenta strips: sustained recognition. Conditional neighbor bounds appear only in the table. The green line follows video playback.</p>
<div class="row"><button id="previousNote">Previous note</button><button id="nextNote">Next note</button><span id="chartPosition" class="pill"></span></div>
<label>Recording position <input id="position" type="range" step="0.001" style="width:100%"></label>
<div class="chart-viewport"><svg id="lanes" viewBox="0 0 1000 680" role="img" style="height:680px" aria-label="Vertical note chart: time increases downward, lanes from left to right"></svg></div><small><span style="color:#b6ff59">● Left: chart target range</span> · <span style="color:#ff70dd">● Right: input range (optional dashed connections = candidates)</span><br>Click a note or input range to select the note and seek the recording. Scroll through time with the recording-position slider, or play the video to follow the chart. White outlines mark the selected note. Gray crosses are excluded endpoints, not fitted timings. Long bodies are holds; magenta spans show recognized held states, not repeated presses. Rolls and unreliable motion remain unresolved.</small></section>
</div>
<details class="panel"><summary>How to read the vertical chart</summary><p class="muted">Read from top to bottom: earlier notes above, later notes below. Columns follow the original lane order. Note size and spacing are independent. Notes fit the available width automatically so all lanes and both timing ranges remain visible; the size label indicates when fitting reduces your chosen size. Play the video on the left to follow the same recording position in this chart. Colored squares retain a fixed size as spacing changes. Lime points and capped lines on the left show chart target ranges. Magenta points and capped lines on the right show input ranges. Enable Show candidate connections to see dashed links from notes to alternative input ranges, limited to 250 ms early and 500 ms late. Unlinked candidate windows and hold envelopes are hidden. Both ranges remain visible when their times overlap. Points at interval centers are visual guides, not subframe measurements. A magenta mark above its note is early; below is late. The green line follows the recording.</p></details>
<section class="panel"><h2>Timing evidence</h2><label>Display latency correction: <output id="delayValue"></output> ms<br><input id="delay" type="range" min="-500" max="500" step="1"></label>
<button id="center">Center observed median (relative alignment)</button><p class="muted">Positive correction subtracts a presumed display delay. Centering the median is a visualization aid, not a physical latency calibration. Associations stay fixed; use <code>--display-delay-ms</code> to rerun them.</p>
<div id="quality"></div><p><a href="analysis.json">Analysis JSON</a> · <a href="timing-ranges.json">Per-note timing ranges</a> · <a href="holds.json">Long-note geometry and held-state evidence</a> · <a href="frames.jsonl">Native-frame observations</a> · <a href="evidence/bootstrap.json">Digit-template evidence</a> · <a href="judgments.jsonl">Judgment observations</a> · <a href="evidence/judgments/bootstrap.json">Word-template evidence</a></p></section>
<section class="panel chart"><h2>Observed timing offsets</h2><svg id="timing" viewBox="0 0 1200 290" role="img"></svg><small>Each bar compares the input estimate with the note target range, including both frame-bracket and fitted-target uncertainty. Blue: earlier; amber: later; green: overlapping ranges. Click to select a note and seek the recording. This is display-based evidence, not a judgment-window score.</small></section>
<section class="panel chart"><h2>Selected note: target vs input</h2><p class="muted">Select a note in the table or chart. Lime is the video-estimated target range; magenta is the input estimate from a display refresh, after the latency correction above. Both use the same time axis, centered on the fitted target. These are uncertainty ranges, not game judgment windows or authoritative chart timestamps.</p><svg id="comparison" viewBox="0 0 1200 180" role="img" style="height:180px"></svg><div id="comparisonDetails" aria-live="polite"></div></section>
<section class="panel"><h2>Note timing comparison</h2><p class="muted">Times are absolute recording positions. Input − target includes uncertainty in both ranges: negative is early, positive is late. Overlapping ranges do not establish an early/late result. Unmatched notes show alternative observed refresh ranges or conditional bounds from neighboring processed rows; these do not establish an input assignment. When evidence is absent, the input stays unconfirmed; a possible MISS never supplies one. Chord heads share a refresh bracket; aggregate brackets can span several rows.</p><div class="scroll"><table><thead><tr><th>Note / lane</th><th>Target range (video estimate)</th><th>Input range (display estimate)</th><th>Input − target</th><th>Evidence / judgment</th></tr></thead><tbody id="events"></tbody></table></div></section>
<section class="panel"><h2>Coverage and exclusions</h2><div id="exclusions"></div><ul id="limitations"></ul></section>
<section class="panel"><h2>Observed combo updates, including unassigned evidence</h2><p class="muted">One increment represents a judged row. Chords share that row; counter jumps can contain several rows or hold ticks. An unassigned update is still observed evidence. Resets do not identify missed presses.</p><div class="scroll"><table><thead><tr><th>Observed bracket</th><th>Counter</th><th>Rows advanced</th><th>Association</th></tr></thead><tbody id="comboEvents"></tbody></table></div></section>
<section class="panel"><h2>Observed judgments, including counter-free evidence</h2><p class="muted">Word changes, reappearance after a confirmed blank, and animation restarts can establish display refreshes before combo 4 or after a break. A persistent word is not counted repeatedly. MISS is failure evidence, never a press timestamp.</p><div class="scroll"><table><thead><tr><th>Observed bracket</th><th>Judgment</th><th>Refresh evidence</th><th>Association</th></tr></thead><tbody id="judgmentEvents"></tbody></table></div></section>
<details class="panel"><summary>Inspect or correct calibration</summary><p>Check receptor centers and combo crop against the original game panel. Download an edited layout and rerun with <code>--layout layout.json</code>. Geometry changes require reanalysis.</p><div class="preview"><img id="preview" src="preview.png" alt="Original gameplay calibration frame"><svg id="overlay" viewBox="0 0 1300 730" role="img"></svg></div><textarea id="layout" spellcheck="false"></textarea><button id="download">Download layout.json</button><span id="layoutError"></span></details>
</main><script id="data" type="application/json">__DATA__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id),video=$('video');
let playhead=data.start_seconds,selected=-1,objectUrl=null;
const matches=data.matches.filter(match=>data.timing_ranges?.notes?.[match.note]?.status==='matched'),delay=$('delay');delay.value=data.display_delay_correction_ms||0;
const fmt=t=>{const ms=Math.round(Math.abs(t)*1000),m=Math.floor(ms/60000);return (t<0?'-':'')+m+':'+((ms%60000)/1000).toFixed(3).padStart(6,'0')};
const matchByNote=new Map(matches.map((m,i)=>[m.note,{match:m,index:i}]));
const rangeByNote=data.timing_ranges?.notes||{};
const targetColor='#b6ff59',inputColor='#ff70dd';
const notePalette={blue:['#267bcc','#83caff'],red:['#c63c52','#ff9da9'],yellow:['#d8a600','#ffe476']};
const holds=data.hold_analysis?.holds||[],holdById=new Map(holds.map(hold=>[hold.id,hold]));
const holdFor=note=>note?.note_type==='hold'?holdById.get(note.hold_id):null;
const possibleMissNotes=new Set((data.miss_candidates||[]).map(candidate=>candidate.note));
const reviewNotes=data.notes.map((note,index)=>({note,index})).filter(({note})=>note.status==='estimated').sort((a,b)=>a.note.target_seconds-b.note.target_seconds);
let selectedNote=matches[0]?.note??reviewNotes[0]?.index??null;
if(selectedNote!==null)playhead=data.notes[selectedNote].target_seconds;
const targetRange=note=>Number.isFinite(note.target_seconds)&&Number.isFinite(note.prediction_uncertainty_seconds)
  ?[note.target_seconds-note.prediction_uncertainty_seconds,note.target_seconds+note.prediction_uncertainty_seconds]:null;
const inputIntervals=(m,index=m?.note)=>{
const record=rangeByNote[index]||{},note=data.notes[index];
const ranges=record.status==='matched'&&record.observed_input_range?[record.observed_input_range]
 :record.status==='possible'?(record.alternatives||[]).map(event=>[event.lower_seconds,event.upper_seconds])
 :record.status==='bounded'&&record.neighbor_observation_range?[record.neighbor_observation_range]:record.input_ranges||[];
const shifted=ranges.map(range=>range.map(t=>t-Number(delay.value)/1000));
if(holdFor(note))return shifted;
const limits=data.timing_ranges.association_limits_seconds,center=note?.target_seconds;
const clipped=shifted.map(range=>[Math.max(range[0],center-limits.early),Math.min(range[1],center+limits.late)]).filter(range=>range[0]<=range[1]).sort((a,b)=>a[0]-b[0]);
const merged=[];for(const range of clipped){if(merged.length&&range[0]<=merged.at(-1)[1])merged.at(-1)[1]=Math.max(merged.at(-1)[1],range[1]);else merged.push(range)}return merged;
};
const chartInputIntervals=index=>rangeByNote[index]?.status==='bounded'?[]:holdFor(data.notes[index])||matchByNote.has(index)||$('candidates').checked?inputIntervals(matchByNote.get(index)?.match,index):[];
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
let playbackHandle=null,playbackMode=null,playbackWaiting=false,playbackSeeking=false;
function updatePlayback(time){if(Number.isFinite(time)){playhead=time;drawPlayback()}}
function stopPlaybackClock(){
if(playbackHandle!==null){if(playbackMode==='video')video.cancelVideoFrameCallback(playbackHandle);else cancelAnimationFrame(playbackHandle)}
playbackHandle=null;cancelChartAnimation();
}
function startPlaybackClock(){
if(video.paused||video.ended||playbackHandle!==null)return;
if(typeof video.requestVideoFrameCallback==='function'){
playbackMode='video';playbackHandle=video.requestVideoFrameCallback((_,frame)=>{playbackHandle=null;updatePlayback(frame.mediaTime);startPlaybackClock()});
}else{
playbackMode='animation';playbackHandle=requestAnimationFrame(()=>{playbackHandle=null;updatePlayback(video.currentTime);startPlaybackClock()});
}}
video.addEventListener('loadedmetadata',()=>{video.currentTime=playhead;draw()});
video.addEventListener('play',()=>{playbackWaiting=false;syncChartMotion(true);startPlaybackClock()});
video.addEventListener('waiting',()=>{playbackWaiting=true;updatePlayback(video.currentTime)});
video.addEventListener('playing',()=>{playbackWaiting=false;updatePlayback(video.currentTime);startPlaybackClock()});
video.addEventListener('ratechange',()=>syncChartMotion(true));
for(const event of ['pause','ended'])video.addEventListener(event,()=>{stopPlaybackClock();updatePlayback(video.currentTime)});
for(const event of ['seeking','seeked'])video.addEventListener(event,()=>{playbackSeeking=event==='seeking';updatePlayback(video.currentTime);syncChartMotion(true);startPlaybackClock()});
video.addEventListener('timeupdate',()=>{if(video.paused||typeof video.requestVideoFrameCallback!=='function')updatePlayback(video.currentTime)});
const SVG_NS='http://www.w3.org/2000/svg';
function svgNode(tag,attrs,parent,label){
const node=document.createElementNS(SVG_NS,tag);
for(const [name,value] of Object.entries(attrs||{}))node.setAttribute(name,String(value));
if(label!==undefined)node.textContent=label;
if(parent)parent.appendChild(node);return node;
}
function svgRoot(id,width,height){const root=$(id);root.replaceChildren();root.setAttribute('viewBox',`0 0 ${width} ${height}`);return root}
const line=(parent,x1,y1,x2,y2,color,width=1,dash=null)=>svgNode('line',{x1,y1,x2,y2,stroke:color,'stroke-width':width,...(dash?{'stroke-dasharray':dash}:{})},parent);
const label=(parent,value,x,y,color='#9cb1b1',size=12,anchor='start')=>svgNode('text',{x,y,fill:color,'font-size':size,'text-anchor':anchor},parent,value);
let chartScene=null,timingPlayhead=null;
function timing(){
const w=1200,h=290,p=60,root=svgRoot('timing',w,h);
const values=matches.flatMap(offset).filter(Number.isFinite),range=Math.max(100,...values.map(Math.abs));
const x=t=>p+(w-2*p)*(t-data.start_seconds)/(data.end_seconds-data.start_seconds),y=v=>h/2-(h/2-25)*v/range;
for(const v of [-range,0,range]){line(root,p,y(v),w-10,y(v),'#314448');label(root,v.toFixed(0)+' ms',0,y(v)+4)}
for(const [i,m] of matches.entries()){
const [lo,hi]=offset(m);if(!Number.isFinite(lo)||!Number.isFinite(hi))continue;
const color=hi<0?'#75bdea':lo>0?'#f1c478':'#9cddbe',group=svgNode('g',{'data-note':m.note},root);
line(group,x(m.target_seconds),y(lo),x(m.target_seconds),y(hi),color,i===selected?4:2);
svgNode('circle',{cx:x(m.target_seconds),cy:y((lo+hi)/2),r:2,fill:color},group);
}
timingPlayhead=line(root,x(playhead),0,x(playhead),h,'#9cddbe');
label(root,fmt(data.start_seconds),p,h-2);label(root,fmt(data.end_seconds),w-85,h-2);
root.onclick=e=>{
const hit=e.target?.closest?.('[data-note]');if(hit){const index=Number(hit.getAttribute('data-note'));seek(data.notes[index].target_seconds,matchByNote.get(index)?.index??-1,index);return}
const rect=root.getBoundingClientRect(),t=data.start_seconds+((e.clientX-rect.left)/root.clientWidth*w-p)/(w-2*p)*(data.end_seconds-data.start_seconds);
if(matches.length){let i=0;for(let j=1;j<matches.length;j++)if(Math.abs(matches[j].target_seconds-t)<Math.abs(matches[i].target_seconds-t))i=j;seek(matches[i].target_seconds,i)}
};
}
function laneGeometry(){
const width=$('lanes').clientWidth||1000,height=680,left=48,right=width-4,top=58,bottom=height-32;
const pps=700*(Number($('spacingScale').value)||1),span=(bottom-top)/pps/2,center=(top+bottom)/2;
const from=playhead-span,to=playhead+span,laneWidth=(right-left)/data.layout.lanes.length;
return {width,height,left,right,top,bottom,center,pps,span,from,to,laneWidth,x:lane=>left+(lane+.5)*laneWidth,y:t=>center+(t-playhead)*pps};
}
function noteSize(){return Math.max(4,Math.min(Number($('noteSize').value)||24,Math.floor(laneGeometry().laneWidth-18)))}
function cancelChartAnimation(){if(chartScene?.animation){chartScene.animation.cancel();chartScene.animation=null}}
function syncChartMotion(force=false){
if(!chartScene)return;
const scene=chartScene,transform=t=>`translateY(${(scene.origin-t)*scene.pps}px)`;
const running=!video.paused&&!video.ended&&!video.seeking&&!playbackWaiting&&!playbackSeeking&&(video.playbackRate||1)>0;
if(!running){cancelChartAnimation();scene.motion.style.transform=transform(playhead);return}
const rate=video.playbackRate||1;
if(!force&&scene.animation&&scene.rate===rate){
const elapsed=scene.animation.currentTime;
if(elapsed!==null){
// Re-anchor the existing browser animation only when it drifts; do not rebuild
// geometry or restart an animation on each video frame.
if(Math.abs(scene.animationStart+elapsed*rate/1000-playhead)>Math.min(.02,6/scene.pps))scene.animation.currentTime=(playhead-scene.animationStart)*1000/rate;
return;
}
}
cancelChartAnimation();scene.motion.style.transform=transform(playhead);
if(typeof scene.motion.animate==='function'){
scene.rate=rate;scene.animationStart=playhead;
scene.animation=scene.motion.animate([{transform:transform(playhead)},{transform:transform(scene.end)}],{duration:Math.max(1,(scene.end-playhead)*1000/rate),easing:'linear',fill:'forwards'});
}
}
function lanes(){
const g=laneGeometry(),size=noteSize(),requested=Number($('noteSize').value)||24;
$('noteSizeValue').textContent=size+' px'+(size<requested?' (fit to width)':'');
// Nearby retained SVG pages bound DOM size and transform distances at every zoom.
const pageSeconds=Math.max(.5,g.span*4),page=Math.floor(playhead/pageSeconds);
const key=JSON.stringify([g.width,size,g.pps,delay.value,Boolean($('excluded').checked),Boolean($('candidates').checked),page]);
if(!chartScene||chartScene.key!==key){
cancelChartAnimation();
const origin=page*pageSeconds,start=origin-g.span-pageSeconds/2,end=origin+2*pageSeconds+g.span;
const root=svgRoot('lanes',g.width,g.height),y=t=>g.center+(t-origin)*g.pps;
for(const [i,lane] of data.layout.lanes.entries()){
svgNode('rect',{x:g.left+i*g.laneWidth,y:g.top,width:g.laneWidth,height:g.bottom-g.top,fill:i%2?'#142124':'#192a2e'},root);
line(root,g.left+i*g.laneWidth,g.top,g.left+i*g.laneWidth,g.bottom,'#314448');
label(root,lane.name||String(i+1),g.x(i),24,'#e5efeb',13,'middle');
label(root,['↙','↖','●','↗','↘'][i%5],g.x(i),47,(notePalette[lane.color]||notePalette.yellow)[1],20,'middle');
}
const defs=svgNode('defs',{},root),clip=svgNode('clipPath',{id:'chartClip'},defs);
svgNode('rect',{x:0,y:g.top,width:g.width,height:g.bottom-g.top},clip);
const viewport=svgNode('g',{'clip-path':'url(#chartClip)'},root),motion=svgNode('g',{id:'chartMotion'},viewport);
motion.style.willChange='transform';motion.style.transformBox='view-box';
const grid=svgNode('g',{'pointer-events':'none'},motion),bodies=svgNode('g',{},motion),notes=svgNode('g',{},motion),ranges=svgNode('g',{},motion);
const tick=g.span*2<=.5?.025:g.span*2<=1?.1:g.span*2<=3?.25:g.span*2<=6?.5:1;
for(let t=Math.ceil(start/tick)*tick;t<=end;t+=tick){line(grid,g.left,y(t),g.right,y(t),'#314448');label(grid,fmt(t),0,y(t)+4,'#9cb1b1',10)}
const intersects=range=>range&&range[1]>=start&&range[0]<=end;
const marker=(range,x,color,index,possible=false)=>{
if(!intersects(range))return;
const group=svgNode('g',{'data-note':index,'data-kind':possible?'candidate-connection':color===targetColor?'target-range':'input-range','data-range-start':range[0],'data-range-end':range[1]},ranges);
if(possible)line(group,g.x(data.notes[index].lane),y(data.notes[index].target_seconds),x,y((range[0]+range[1])/2),color,1,'4 3');
line(group,x,y(Math.max(start,range[0])),x,y(Math.min(end,range[1])),color,3,possible?'4 3':null);
for(const t of range)if(t>=start&&t<=end)line(group,x-3,y(t),x+3,y(t),color,3);
const middle=(range[0]+range[1])/2;if(middle>=start&&middle<=end)svgNode('circle',{cx:x,cy:y(middle),r:3,fill:possible?'none':color,stroke:color,'stroke-width':2},group);
};
for(const hold of holds){
const first=hold.start_censored?hold.start_range[1]:(hold.start_range[0]+hold.start_range[1])/2,last=hold.end_range?(hold.end_range[0]+hold.end_range[1])/2:hold.last_body_seconds;
if(!intersects([first,last]))continue;
const x=g.x(hold.lane),bodyWidth=Math.max(4,size*.4),palette=notePalette[data.layout.lanes[hold.lane].color]||notePalette.yellow;
const group=svgNode('g',{'data-note':hold.display_note,'data-kind':'hold-body'},bodies);
svgNode('rect',{x:x-bodyWidth/2,y:y(Math.max(first,start)),width:bodyWidth,height:Math.max(2,(Math.min(last,end)-Math.max(first,start))*g.pps),fill:palette[0],stroke:palette[1],'stroke-width':2},group);
if(last>=start&&last<=end){line(group,x-size*.4,y(last),x+size*.4,y(last),palette[1],4);if(hold.end_censored)label(group,'?',x+size*.45,y(last)+4,palette[1])}
const shift=Number(delay.value)/1000;
for(const state of hold.input.segments){const lo=Math.max(start,state.lower_seconds-shift),hi=Math.min(end,state.upper_seconds-shift);if(lo<=hi)line(group,x+size/2+5,y(lo),x+size/2+5,y(hi),inputColor,5)}
}
const selectionRects=new Map();
for(const [index,note] of data.notes.entries()){
const t=note.target_seconds??note.points.at(-1)?.[0],x=g.x(note.lane);
if(note.status!=='estimated'){
if($('excluded').checked&&Number.isFinite(t)&&t>=start&&t<=end)label(notes,'×',x,y(t)+6,'#647371',18,'middle');continue;
}
const target=targetRange(note),hold=holdFor(note);
if(t>=start&&t<=end){
const palette=notePalette[data.layout.lanes[note.lane].color]||notePalette.yellow;
const group=svgNode('g',{'data-note':index,'data-kind':'note',role:'button',tabindex:0,'aria-label':'Note '+(index+1)+' at '+fmt(t)},notes);
svgNode('rect',{x:x-size/2,y:y(t)-size/2,width:size,height:size,fill:palette[0],stroke:palette[1],'stroke-width':2,'data-kind':'note-square'},group);
label(group,hold?.start_censored?'?':['↙','↖','●','↗','↘'][note.lane%5],x,y(t)+size*.32,'#ffffff',size,'middle');
selectionRects.set(index,svgNode('rect',{x:x-size/2-3,y:y(t)-size/2-3,width:size+6,height:size+6,fill:'none',stroke:'#ffffff','stroke-width':2,visibility:'hidden'},group));
group.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();seek(t,matchByNote.get(index)?.index??-1,index)}};
}
if(!hold?.start_censored)marker(target,x-size/2-5,targetColor,index);
if(hold?.end_range)marker(hold.end_range,x-size/2-5,targetColor,index);
for(const range of hold?[]:chartInputIntervals(index))marker(range,x+size/2+5,inputColor,index,!matchByNote.has(index));
}
line(root,g.left,g.center,g.right,g.center,'#9cddbe',2);
const now=label(root,'Now '+fmt(playhead),g.left+6,g.center-8,'#9cddbe');
chartScene={key,origin,start,end,pps:g.pps,motion,now,selectionRects,selectedNote:null,animation:null};
root.onclick=e=>{
const hit=e.target?.closest?.('[data-note]');if(hit){const index=Number(hit.getAttribute('data-note'));seek(data.notes[index].target_seconds,matchByNote.get(index)?.index??-1,index);return}
const rect=root.getBoundingClientRect(),px=(e.clientX-rect.left)/root.clientWidth*g.width,py=(e.clientY-rect.top)/root.clientHeight*g.height,current=laneGeometry();
if(px<g.left||px>=g.right||py<g.top||py>g.bottom)return;
const lane=Math.floor((px-g.left)/g.laneWidth),t=playhead+(py-g.center)/g.pps;
const candidates=reviewNotes.filter(({note})=>note.lane===lane).map(item=>{
const intervals=chartInputIntervals(item.index),hold=holdFor(item.note),holdDistance=hold?Math.max((hold.start_censored?hold.start_range[1]:hold.start_range[0])-t,0,t-(hold.end_range?.[1]??hold.last_body_seconds)):Infinity;
return {...item,distance:Math.min(Math.abs(item.note.target_seconds-t),holdDistance,...intervals.map(range=>Math.max(range[0]-t,0,t-range[1])))};
}).filter(item=>item.distance<(current.to-current.from)*.035).sort((a,b)=>a.distance-b.distance||Math.abs(a.note.target_seconds-t)-Math.abs(b.note.target_seconds-t));
const closest=candidates[0];if(closest)seek(closest.note.target_seconds,matchByNote.get(closest.index)?.index??-1,closest.index);else seek(t);
};
}
if(chartScene.selectedNote!==selectedNote){
chartScene.selectionRects.get(chartScene.selectedNote)?.setAttribute('visibility','hidden');
chartScene.selectionRects.get(selectedNote)?.setAttribute('visibility','visible');chartScene.selectedNote=selectedNote;
}
chartScene.now.textContent='Now '+fmt(playhead);syncChartMotion();
}
if(typeof ResizeObserver!=='undefined')new ResizeObserver(()=>lanes()).observe($('lanes'));
function setSpacing(value){
if(!Number.isFinite(value))return;
const scale=Math.max(.05,Math.min(16,value)).toFixed(2);
$('spacingScale').value=scale;$('spacingInput').value=scale;$('spacingValue').textContent=scale+'×';draw();
}
$('spacingScale').oninput=()=>setSpacing(Number($('spacingScale').value));
$('spacingInput').oninput=()=>{if($('spacingInput').value.trim())setSpacing(Number($('spacingInput').value))};
$('noteSize').oninput=()=>draw();
$('position').min=data.start_seconds;$('position').max=data.end_seconds;
$('position').oninput=()=>seek(Number($('position').value));
function stepNote(direction){
const current=reviewNotes.findIndex(item=>item.index===selectedNote);
const index=Math.max(0,Math.min(reviewNotes.length-1,current+direction));
const item=reviewNotes[index];if(item)seek(item.note.target_seconds,matchByNote.get(item.index)?.index??-1,item.index);
}
$('previousNote').onclick=()=>stepNote(-1);$('nextNote').onclick=()=>stepNote(1);
function comparison(){
const w=1200,p=180,right=w-35,center=(p+right)/2,root=svgRoot('comparison',w,180);
$('comparisonDetails').replaceChildren();
const note=data.notes[selectedNote];
if(!note){label(root,'No supported target ranges to compare.',p,70);return}
const match=matchByNote.get(selectedNote)?.match,hold=holdFor(note),target=hold?[hold.start_censored?hold.start_range[1]:hold.start_range[0],hold.end_range?.[1]??hold.last_body_seconds]:targetRange(note),input=hold||match||rangeByNote[selectedNote]?.status==='possible'&&$('candidates').checked?inputRange(match,selectedNote):null,delta=difference(target,input);
const extent=Math.max(100,...[...(target||[]),...(input||[])].map(t=>Math.abs(1000*(t-note.target_seconds))))*1.15;
const x=t=>center+1000*(t-note.target_seconds)/extent*(right-p)/2;
for(const ms of [-extent,0,extent]){const px=center+ms/extent*(right-p)/2;line(root,px,15,px,135,'#314448');label(root,ms.toFixed(1)+' ms',px-25,160)}
for(const [name,range,color,y] of [['Target (video)',target,targetColor,45],['Input (display)',input,inputColor,105]]){
label(root,name,5,y+4,color);
if(range){for(const part of name==='Input (display)'?inputIntervals(match,selectedNote):[range]){
line(root,x(part[0]),y,x(part[1]),y,color,8,!hold&&!match&&name==='Input (display)'?'5 4':null);
for(const t of part)line(root,x(t),y-9,x(t),y+9,color,2);
}}else label(root,'Unconfirmed — no press timestamp',p,y+4,color);
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
function drawPlayback(){$('position').value=playhead;$('chartPosition').textContent=fmt(playhead);$('clock').textContent=fmt(playhead);lanes();if(timingPlayhead){const x=60+1080*(playhead-data.start_seconds)/(data.end_seconds-data.start_seconds);timingPlayhead.setAttribute('x1',x);timingPlayhead.setAttribute('x2',x)}}
function draw(){$('delayValue').textContent=delay.value;drawPlayback();timing();comparison()}
delay.oninput=()=>{table();draw()};$('center').onclick=()=>{delay.value=Math.round(median(matches.map(mid)));table();draw()};$('excluded').onchange=draw;$('candidates').onchange=draw;
$('layout').value=JSON.stringify(data.layout,null,2);$('download').onclick=()=>{try{const value=JSON.parse($('layout').value),url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='layout.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('layoutError').textContent=''}catch(e){$('layoutError').textContent=e.message}};
function overlay(){
const w=$('preview').naturalWidth,h=$('preview').naturalHeight,root=svgRoot('overlay',w,h);
line(root,0,data.layout.receptor_y*h,w,data.layout.receptor_y*h,'#9cddbe',2);
for(const lane of data.layout.lanes)line(root,lane.x*w,data.layout.receptor_y*h,lane.x*w,h*.95,'#9cddbe',2);
for(const [roi,color] of [[data.layout.combo_roi,'#f1c478'],[data.judgment_roi,'#75bdea']])if(roi){const [x,y,rw,rh]=roi;svgNode('rect',{x:x*w,y:y*h,width:rw*w,height:rh*h,fill:'none',stroke:color,'stroke-width':2},root)}
}
$('preview').onload=overlay;if($('preview').complete&&$('preview').naturalWidth)overlay();table();draw();
</script></html>'''
