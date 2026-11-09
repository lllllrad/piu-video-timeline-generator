/** Preserve opaque integer provenance; only measured coordinates use Number. */
const native = JSON as typeof JSON & {rawJSON: (text: string) => unknown};

/** Native reviver source contexts retain a parse tree for every property. Avoid
 * that amplification: protect only unsafe integer tokens, then parse normally.
 * A NUL prefix absent from decoded input strings makes markers unambiguous.
 */
export function parseData(text: string): any {
  let zeros = 1;
  while (text.includes('\\u0000'.repeat(zeros))) zeros++;
  const prefix = '\0'.repeat(zeros) + 'integer:';
  const integers = new Map<string, bigint>(), pieces: string[] = [];
  const number = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y;
  let copied = 0;
  for (let i = 0; i < text.length;) {
    const code = text.charCodeAt(i);
    if (code === 34) {
      i++;
      while (i < text.length) {
        const next = text.charCodeAt(i++);
        if (next === 92) i++;
        else if (next === 34) break;
      }
    } else if (code === 45 || code >= 48 && code <= 57) {
      number.lastIndex = i;
      const match = number.exec(text);
      if (!match) { i++; continue; }
      const token = match[0];
      let after = number.lastIndex;
      while (/[ \t\r\n]/.test(text[after] ?? '')) after++;
      // A number used as an unquoted property name must remain invalid JSON.
      if (text[after] !== ':' && /^-?\d{16,}$/.test(token) && !Number.isSafeInteger(Number(token))) {
        const marker = prefix + integers.size;
        integers.set(marker, BigInt(token));
        pieces.push(text.slice(copied, i), JSON.stringify(marker));
        copied = number.lastIndex;
      }
      i = number.lastIndex;
    } else i++;
  }
  if (integers.size) pieces.push(text.slice(copied));
  const parsed = JSON.parse(integers.size ? pieces.join('') : text);
  function scalar(value: any): any {
    if (typeof value === 'string' && integers.has(value)) return integers.get(value);
    if (typeof value === 'number' && !Number.isFinite(value)) throw new Error('Nonfinite analysis input');
    return value;
  }
  const root = scalar(parsed), stack = root && typeof root === 'object' ? [root] : [];
  while (stack.length) {
    const parent = stack.pop();
    for (const key of Object.keys(parent)) {
      const value = scalar(parent[key]);
      parent[key] = value;
      if (value && typeof value === 'object') stack.push(value);
    }
  }
  return root;
}
export function stringifyData(value: unknown): string {
  return JSON.stringify(value, (_key, item) => {
    if (typeof item === 'bigint') return native.rawJSON(item.toString());
    if (typeof item === 'number' && !Number.isFinite(item)) throw new Error('Nonfinite analysis output');
    return item;
  });
}
