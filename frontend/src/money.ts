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

/** A USD decimal string for display, rounded to cents: "1234.56789" → "$1,234.57". */
export function usd(value: string): string {
  const cents = toCents(value, 0);
  return cents ? `$${cents[0].toLocaleString("en-US")}.${cents[1]}` : value;
}
