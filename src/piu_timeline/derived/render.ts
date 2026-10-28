/** Render a prepared report without running any analysis stage. */
import {readFileSync, writeFileSync, renameSync, unlinkSync} from 'node:fs';
import {dirname, relative, resolve, sep} from 'node:path';
import {randomUUID} from 'node:crypto';
import {render} from './report.ts';

const [source, destination] = process.argv.slice(2);
let pending: string | null = null;
try {
  if (!source || !destination || process.argv.length !== 4 || !destination.endsWith('.html') || resolve(source) === resolve(destination)) {
    throw new Error('Usage: render INPUT.json OUTPUT.html');
  }
  const serialized = readFileSync(source, 'utf8'), data = JSON.parse(serialized);
  const media = relative(dirname(resolve(destination)), data.media.path).split(sep).map(part => encodeURIComponent(part).replace(/[!'()*]/g, c => '%' + c.charCodeAt(0).toString(16).toUpperCase())).join('/');
  const html = render(serialized, data.song || 'Unknown song', data.chart || 'Unknown chart', media);
  pending = resolve(dirname(destination), `.report-${randomUUID()}.tmp`);
  writeFileSync(pending, html, {flag: 'wx'}); renameSync(pending, destination); pending = null;
} catch (error) {
  if (pending) { try { unlinkSync(pending); } catch {} }
  process.stderr.write(`Report rendering failed: ${error.message}\n`); process.exitCode = 1;
}
