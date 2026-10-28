/** Exact UCS decimal and beat arithmetic; conversion to seconds is explicit. */
function gcd(a: bigint, b: bigint): bigint { a = a < 0n ? -a : a; while (b) [a, b] = [b, a % b]; return a; }
export class Rational {
  readonly n: bigint;
  readonly d: bigint;
  constructor(n: bigint | number | string = 0, denominator: bigint = 1n) {
    if (typeof n === 'string') {
      const s = n.trim();
      if (/^[+-]?\d+\s*\/\s*[+-]?\d+$/.test(s)) {
        const [a, b] = s.split('/'); n = BigInt(a.trim()); denominator *= BigInt(b.trim());
      } else {
        const m = /^([+-]?)(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:[eE]([+-]?\d+))?$/.exec(s);
        if (!m) throw new Error('Invalid rational number');
        const decimals = m[3] ?? m[4] ?? '', exponent = Number(m[5] ?? 0) - decimals.length;
        if (!Number.isSafeInteger(exponent) || Math.abs(exponent) > 10000) throw new Error('Unsupported rational exponent');
        n = BigInt((m[1] === '-' ? '-' : '') + (m[2] ?? '0') + decimals);
        if (exponent >= 0) n *= 10n ** BigInt(exponent); else denominator *= 10n ** BigInt(-exponent);
      }
    } else n = BigInt(n);
    if (denominator === 0n) throw new Error('Zero rational denominator');
    if (denominator < 0n) { n = -n; denominator = -denominator; }
    const factor = gcd(n, denominator);
    this.n = n / factor; this.d = denominator / factor;
  }
  add(b: Rational): Rational { return new Rational(this.n * b.d + b.n * this.d, this.d * b.d); }
  sub(b: Rational): Rational { return new Rational(this.n * b.d - b.n * this.d, this.d * b.d); }
  mul(b: Rational): Rational { return new Rational(this.n * b.n, this.d * b.d); }
  div(b: Rational): Rational { return new Rational(this.n * b.d, this.d * b.n); }
  cmp(b: Rational): number { const v = this.n * b.d - b.n * this.d; return v < 0n ? -1 : v > 0n ? 1 : 0; }
  number(): number { return Number(this.n) / Number(this.d); }
  integer(): number {
    const n = this.n / this.d;
    if (n > BigInt(Number.MAX_SAFE_INTEGER) || n < BigInt(Number.MIN_SAFE_INTEGER)) throw new Error('UCS row count exceeds integer precision');
    return Number(n);
  }
  ceil(): number { return new Rational(this.n >= 0n ? (this.n + this.d - 1n) / this.d : this.n / this.d).integer(); }
  toString(): string { return this.d === 1n ? String(this.n) : `${this.n}/${this.d}`; }
  toJSON(): string { return this.toString(); }
}
export const q = (n: number | string) => new Rational(n);
export const lcm = (a: number, b: number) => Number(BigInt(a) / gcd(BigInt(a), BigInt(b)) * BigInt(b));
