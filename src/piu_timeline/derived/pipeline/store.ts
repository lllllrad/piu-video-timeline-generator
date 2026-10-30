/** Independent derived artifacts; cached output is never evidence for its own input. */
import {readFileSync, existsSync, mkdirSync, writeFileSync, renameSync, unlinkSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {createHash, randomUUID} from 'node:crypto';
import {parseData, stringifyData} from '../json.ts';

const sorted = (v: any): any => Array.isArray(v) ? v.map(sorted) : v && typeof v === 'object' ?
  Object.fromEntries(Object.keys(v).sort().map(k => [k, sorted(v[k])])) : v;
export const fingerprint = (v: unknown): string => createHash('sha256').update(stringifyData(sorted(v))).digest('hex');
function paths(v: any, before: string, after: string): any {
  if (typeof v === 'string') return v.startsWith(before) ? after + v.slice(before.length) : v;
  if (Array.isArray(v)) return v.map(item => paths(item, before, after));
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, item]) => [k, paths(item, before, after)]));
  return v;
}

/** Hash local implementation dependencies so source changes cannot reuse stale fits. */
export function implementation(module: URL): string {
  const seen = new Set<string>(), modules: [string, string][] = [];
  const visit = (url: URL) => {
    if (seen.has(url.href)) return;
    seen.add(url.href);
    const source = readFileSync(url, 'utf8');
    modules.push([url.pathname.split('/derived/').at(-1), source]);
    for (const match of source.matchAll(/(?:from\s*|import\s*)['"](\.[^'"]+\.(?:ts|json))['"]/g)) visit(new URL(match[1], url));
    // contracts.ts reads this runtime resource rather than importing it.
    if (url.href === new URL('../contracts.ts', import.meta.url).href) visit(new URL('./contracts.json', url));
  };
  visit(module);
  return fingerprint(modules.sort(([a], [b]) => a.localeCompare(b)));
}

export interface StageRecord {stage: string; input: string; producer: string; output: string; reused: boolean}
export class Store {
  readonly records: StageRecord[] = [];
  readonly directory?: string;
  constructor(directory?: string) {this.directory = directory;}

  run<T>(stage: string, producer: string, input: unknown, compute: () => T): T {
    if (!/^[a-z][a-z-]*$/.test(stage)) throw new Error('Invalid stage name');
    const prefix = this.directory ? resolve(this.directory) + '/' : '';
    const normalize = value => prefix ? paths(value, prefix, '@segment/') : value;
    const inputHash = fingerprint(normalize(input)), target = this.directory && resolve(this.directory, 'derived-stages', `${stage}.json`);
    let output: T, reused = false;
    if (target && existsSync(target)) {
      const saved = parseData(readFileSync(target, 'utf8'));
      if (saved.schema !== 1 || saved.stage !== stage || fingerprint(saved.output) !== saved.output_fingerprint) throw new Error(`Corrupt derived stage artifact: ${stage}`);
      if (saved.input_fingerprint === inputHash && saved.producer === producer) {
        output = paths(saved.output, '@segment/', prefix); reused = true;
      }
    }
    if (!reused) {
      // Isolation is part of the stage boundary, even for algorithms with mutable work arrays.
      output = compute();
      if (target) atomicJSON(target, {schema: 1, stage, producer, input_fingerprint: inputHash,
        output_fingerprint: fingerprint(normalize(output)), output: normalize(output)});
    }
    this.records.push({stage, producer, input: inputHash, output: fingerprint(normalize(output)), reused});
    return reused ? output : structuredClone(output);
  }
}

export function atomicJSON(path: string, value: unknown): void {
  const encoded = stringifyData(value);
  mkdirSync(dirname(path), {recursive: true});
  const temporary = `${path}.${randomUUID()}.tmp`;
  try {writeFileSync(temporary, encoded + '\n', {flag: 'wx'}); renameSync(temporary, path);}
  finally {if (existsSync(temporary)) unlinkSync(temporary);}
}

export function artifactCurrent(directory: string, stage: string, producer: string, input: unknown): boolean {
  const path = resolve(directory, 'derived-stages', `${stage}.json`);
  if (!existsSync(path)) return false;
  const saved = parseData(readFileSync(path, 'utf8'));
  if (saved.schema !== 1 || saved.stage !== stage || fingerprint(saved.output) !== saved.output_fingerprint) throw new Error(`Corrupt derived stage artifact: ${stage}`);
  return saved.producer === producer && saved.input_fingerprint === fingerprint(paths(input, resolve(directory) + '/', '@segment/'));
}
