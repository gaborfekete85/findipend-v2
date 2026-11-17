/**
 * `value` ÷ 10^shift rounded half up to cents, as [dollars, "cc"]; null if `value` is not a decimal.
 * BigInt keeps it exact: money never goes through a float.
 */
function toCents(value: string, shift: number): [bigint, string] | null {
  if (!/^\d+(\.\d+)?$/.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  const scale = 10n ** BigInt(fraction.length + shift);
  const cents = (BigInt(whole + fraction) * 200n + scale) / (2n * scale);
  return [cents / 100n, String(cents % 100n).padStart(2, "0")];
}

/** The default fee, 0.1% of `total` in cents ("1000" → "1.00"); "" while total is not a number. */
export function defaultFee(total: string): string {
  const cents = toCents(total, 3);
  return cents ? `${cents[0]}.${cents[1]}` : "";
}

/** A USD decimal string for display, rounded to cents: "1234.56789" → "$1,234.57", "-5" → "-$5.00". */
export function usd(value: string): string {
  const sign = value.startsWith("-") ? "-" : "";
  const cents = toCents(value.slice(sign.length), 0);
  return cents ? `${sign}$${cents[0].toLocaleString("en-US")}.${cents[1]}` : value;
}

const PLACES = 18; // quantities have up to 18 decimal places

/** A quantity as a count of 10^-18 units; blank is 0; null unless a decimal with at most 18 places. */
function units(value: string): bigint | null {
  if (value.trim() === "") return 0n;
  const match = /^(\d+)(?:\.(\d{1,18}))?$/.exec(value.trim());
  return match ? BigInt(match[1] + (match[2] ?? "").padEnd(PLACES, "0")) : null;
}

/** Units back to a plain decimal string without trailing zeros: 3 * 10^17 → "0.3". */
function plain(count: bigint): string {
  const digits = count.toString().padStart(PLACES + 1, "0");
  const fraction = digits.slice(-PLACES).replace(/0+$/, "");
  return digits.slice(0, -PLACES) + (fraction ? `.${fraction}` : "");
}

/** Exact sum of quantities (blank counts as 0) as a plain string; null if any is not a decimal. */
export function addQuantities(values: string[]): string | null {
  const counts = values.map(units);
  return counts.includes(null) ? null : plain(counts.reduce<bigint>((sum, count) => sum + count!, 0n));
}

/** True when `parts` sum exactly to `total` and `total` is above 0. Compared as decimals, never floats. */
export function sumsTo(parts: string[], total: string): boolean {
  const sum = addQuantities(parts);
  const target = units(total);
  return sum !== null && !!target && units(sum) === target;
}

/** FIFO pre-fill: draws `quantity` from each available amount in order; "" where nothing is drawn. */
export function fifo(available: string[], quantity: string): string[] {
  let left = units(quantity) ?? 0n;
  return available.map((amount) => {
    const lot = units(amount) ?? 0n;
    const take = left < lot ? left : lot;
    left -= take;
    return take > 0n ? plain(take) : "";
  });
}
