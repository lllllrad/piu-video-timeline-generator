/** Render a prepared report without running any analysis stage. */
import {statSync, renameSync, unlinkSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
import {renderShellFile} from './report.ts';

const [source, destination] = process.argv.slice(2);
let pending: string | null = null;
try {
  if (!source || !destination || process.argv.length !== 4 || !destination.endsWith('.html') || resolve(source) === resolve(destination)) {
    throw new Error('Usage: render INPUT.json OUTPUT.html');
  }
  if(!statSync(source).isFile())throw new Error('Prepared input must be a file');
  pending = resolve(dirname(destination), `.report-${randomUUID()}.tmp`);
  renderShellFile(source,pending,'Play evidence','', '');
  renameSync(pending,destination);pending=null;
} catch (error) {
  if (pending) { try { unlinkSync(pending); } catch {} }
  process.stderr.write(`Report rendering failed: ${error.message}\n`); process.exitCode = 1;
}
