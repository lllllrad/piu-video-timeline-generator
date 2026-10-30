/** Content identity, including opaque integers and relocatable segment references. */
import {createHash} from 'node:crypto';
import {stringifyData} from './json.ts';

function canonical(value: unknown, artifactRoot?: string): unknown {
  if (typeof value === 'string' && artifactRoot && value.startsWith(artifactRoot)) {
    return '@segment/' + value.slice(artifactRoot.length);
  }
  if (Array.isArray(value)) return value.map(item => canonical(item, artifactRoot));
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key], artifactRoot)]));
  }
  return value;
}

export function fingerprint(value: unknown, artifactRoot?: string): string {
  return createHash('sha256').update(stringifyData(canonical(value, artifactRoot))).digest('hex');
}
