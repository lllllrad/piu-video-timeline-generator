/** Preserve opaque integer provenance; only measured coordinates use Number. */
const native = JSON as typeof JSON & {rawJSON: (text: string) => unknown};

export function parseData(text: string): any {
  return JSON.parse(text, (_key, value, context?: {source?: string}) => {
    if (typeof value === 'number' && !Number.isSafeInteger(value) && /^-?\d+$/.test(context?.source ?? '')) return BigInt(context.source);
    if (typeof value === 'number' && !Number.isFinite(value)) throw new Error('Nonfinite analysis input');
    return value;
  });
}
export function stringifyData(value: unknown): string {
  return JSON.stringify(value, (_key, item) => {
    if (typeof item === 'bigint') return native.rawJSON(item.toString());
    if (typeof item === 'number' && !Number.isFinite(item)) throw new Error('Nonfinite analysis output');
    return item;
  });
}
