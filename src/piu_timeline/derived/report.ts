/** Pure HTML presentation. The input document has already been analyzed. */
import {readFileSync} from 'node:fs';
const resource = name => readFileSync(new URL(`../play/${name}`, import.meta.url), 'utf8');
const template = resource('report.html').replace('__STYLE__', () => resource('report.css') + '\n' + resource('inspector/workspace.css'))
  .replace('__SCRIPT__', () => ['report-evidence.js', 'inspector/navigation.js', 'inspector/provenance.js', 'inspector/overlay.js', 'report.js'].map(resource).join('\n'));
const escape = (value: string) => value.replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#x27;'}[c]));

export function render(dataJSON: string, song: string, chart: string, media: string): string {
  const parts = {TITLE: escape(`${song} · ${chart}`), MEDIA: escape(media),
    DATA: dataJSON.replace(/[<>&]/g, c => ({'<': '\\u003c', '>': '\\u003e', '&': '\\u0026'}[c]))};
  return template.replace(/__(TITLE|MEDIA|DATA)__/g, (_match, name) => parts[name]);
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
