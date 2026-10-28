/** Standalone saved-data entry point: no Python, decoding, OCR, or network. */
import {readFileSync, writeFileSync, renameSync, unlinkSync} from 'node:fs';
import {resolve, dirname, basename} from 'node:path';
import {randomUUID} from 'node:crypto';
import {reconstruct} from './beats/stage.ts';
import {registered} from './tracks.ts';
import {fitMany} from './clocks.ts';
import {estimate} from './speed.ts';
import {parse, text} from './charts/ucs.ts';
import {transcribe} from './charts/transcription.ts';
import {draft} from './charts/draft.ts';
import {parseData, stringifyData} from './json.ts';

export function derive(stage: string, input): unknown {
  if (stage === 'beats') return reconstruct(input);
  if (stage === 'coordinates') return registered(input.tracks, input.timeline, input.height, input.spacing, input.receptor, input.bottom);
  if (stage === 'clocks') return fitMany(input.state, input.tracks, input.receptor, input.layout);
  if (stage === 'speed') return estimate(input);
  if (stage === 'ucs') {
    if (input.chart_observations) {
      const [doc, evidence] = draft(parse(input.timing_text), input.chart_observations, input.alignment, input.extend_constant_tempo ?? false);
      return {ucs_text: text(doc), evidence};
    }
    const [doc, , accepted, failures, proof] = transcribe(parse(input.timing_text), input.endpoints);
    return {ucs_text: text(doc), accepted, failures, proof};
  }
  throw new Error(`Unknown derived stage: ${stage}`);
}

if (process.argv[1] && resolve(process.argv[1]) === resolve(import.meta.filename)) {
  const [stage, source, destination] = process.argv.slice(2);
  let pending: string | null = null;
  try {
    if (!stage || !source || !destination || process.argv.length !== 5) throw new Error('Usage: derive <beats|coordinates|clocks|speed|ucs> INPUT.json OUTPUT.json');
    if (resolve(source) === resolve(destination) || !destination.endsWith('.json')) throw new Error('Output must be a separate JSON artifact');
    const input = parseData(readFileSync(source, 'utf8')), result = derive(stage, input);
    const encoded = stringifyData(result);
    pending = resolve(dirname(destination), `.${basename(destination)}.${randomUUID()}.tmp`);
    writeFileSync(pending, encoded + '\n', {flag: 'wx'});
    renameSync(pending, destination); pending = null;
  } catch (error) {
    if (pending) { try { unlinkSync(pending); } catch {} }
    process.stderr.write(`Derived analysis failed: ${error.message}\n`); process.exitCode = 1;
  }
}
