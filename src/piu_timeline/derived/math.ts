/** Small deterministic numerical operations on saved observations. No pixel I/O. */
export function median(values: number[]): number {
  if (!values.length) throw new Error('Median requires observations');
  const sorted = [...values].sort((a, b) => a - b), i = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[i] : (sorted[i - 1] + sorted[i]) / 2;
}
export const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);
export const mean = (a: number[]) => sum(a) / a.length;
export const rms = (a: number[]) => Math.sqrt(mean(a.map(x => x * x)));
export const std = (a: number[]) => { const center = mean(a); return rms(a.map(x => x - center)); };
export const maximum = (a: number[]) => a.reduce((best, x) => Math.max(best, x), -Infinity);
export function linear(x: number[], y: number[]): [number, number] {
  if (x.length !== y.length || x.length < 2) throw new Error('Linear fit requires paired observations');
  const mx = mean(x), my = mean(y), dx = x.map(v => v - mx);
  const variance = sum(dx.map(v => v * v));
  if (variance <= 0) throw new Error('Linear fit requires distinct coordinates');
  const slope = sum(dx.map((v, i) => v * (y[i] - my))) / variance;
  return [slope, my - slope * mx];
}
export const entries = <T>(obj: Record<string, T>): [number, T][] => Object.entries(obj).map(([k, v]) => [Number(k), v]);
export const pairs = <T>(items: T[]): [T, T][] => items.slice(1).map((item, i) => [items[i], item]);
export function compare(a: number[], b: number[]): number {
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] - b[i];
  return 0;
}
export function equal(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every(k => Object.hasOwn(b, k) && equal(a[k], b[k]));
}
export function lowerBound(a: number[], value: number): number {
  let lo = 0, hi = a.length;
  while (lo < hi) { const mid = (lo + hi) >>> 1; if (a[mid] < value) lo = mid + 1; else hi = mid; }
  return lo;
}
export function upperBound(a: number[], value: number): number {
  let lo = 0, hi = a.length;
  while (lo < hi) { const mid = (lo + hi) >>> 1; if (a[mid] <= value) lo = mid + 1; else hi = mid; }
  return lo;
}
