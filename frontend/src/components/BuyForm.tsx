import { useAuth } from "@clerk/react";
import { type FormEvent, type InputHTMLAttributes, useEffect, useState } from "react";
import { apiFetch } from "../api/client";
import { defaultFee } from "../money";

type Asset = { id: string; symbol: string; name: string };

/** A buy as the API returns it; amounts are decimal strings. */
export type Buy = { id: number; asset_id: string; asset_name: string; asset_symbol: string } & {
  quantity: string; total_usd: string; fee_usd: string; trade_date: string; comment: string | null;
};

/** Today in the user's time zone, as YYYY-MM-DD. */
export function today() {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function Field({ label, ...input }: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block">
      {label}
      <input {...input} className="mt-1 block w-full rounded border px-2 py-1" />
    </label>
  );
}

const label = (asset: Asset) => `${asset.name} (${asset.symbol.toUpperCase()})`;

/** Creates a buy, or edits `buy` when given. */
export default function BuyForm({ portfolioId, buy, onSaved }: { portfolioId: string | number; buy?: Buy; onSaved: () => void }) {
  const { getToken } = useAuth();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Asset[]>([]);
  const [asset, setAsset] = useState<Asset | null>(
    buy ? { id: buy.asset_id, name: buy.asset_name, symbol: buy.asset_symbol } : null,
  );
  const [quantity, setQuantity] = useState(buy?.quantity ?? "");
  const [total, setTotal] = useState(buy?.total_usd ?? "");
  // Null while the fee follows the total; an existing buy keeps its own fee.
  const [fee, setFee] = useState<string | null>(buy?.fee_usd ?? null);
  const [tradeDate, setTradeDate] = useState(() => buy?.trade_date ?? today());
  const [comment, setComment] = useState(buy?.comment ?? "");
  const [error, setError] = useState("");
  const shownFee = fee ?? defaultFee(total);

  useEffect(() => {
    if (!query) return;
    let stale = false;
    apiFetch<Asset[]>(`/api/v1/assets?query=${encodeURIComponent(query)}`, getToken)
      .then((found) => !stale && setResults(found))
      .catch((e: unknown) => !stale && setError(e instanceof Error ? e.message : "Search failed"));
    return () => {
      stale = true;
    };
  }, [query, getToken]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!asset) return setError("Choose an asset");
    setError("");
    const body = {
      ...{ asset_id: asset.id, asset_name: asset.name, asset_symbol: asset.symbol, quantity, total_usd: total },
      ...{ fee_usd: shownFee, trade_date: tradeDate, comment: comment || null },
    };
    const path = `/api/v1/portfolios/${encodeURIComponent(portfolioId)}/buys${buy ? `/${encodeURIComponent(buy.id)}` : ""}`;
    try {
      const headers = { "Content-Type": "application/json" };
      await apiFetch(path, getToken, { method: buy ? "PUT" : "POST", headers, body: JSON.stringify(body) });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    }
  }

  return (
    <form aria-label="Buy" onSubmit={submit} className="space-y-2 rounded border p-4">
      <Field label="Search asset" value={query} onChange={(e) => setQuery(e.target.value)} />
      {query &&
        results.map((found) => (
          <button key={found.id} type="button" onClick={() => (setAsset(found), setQuery(""))} className="block">
            {label(found)}
          </button>
        ))}
      <p>Asset: {asset ? label(asset) : "none chosen"}</p>
      <Field label="Quantity" inputMode="decimal" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
      <Field label="Total (USD)" inputMode="decimal" value={total} onChange={(e) => setTotal(e.target.value)} />
      <Field label="Fee (USD)" inputMode="decimal" value={shownFee} onChange={(e) => setFee(e.target.value)} />
      <Field label="Trade date" type="date" value={tradeDate} onChange={(e) => setTradeDate(e.target.value)} />
      <Field label="Comment" value={comment} onChange={(e) => setComment(e.target.value)} />
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      <button type="submit" className="rounded bg-blue-600 px-3 py-1 text-white">
        Save buy
      </button>
    </form>
  );
}
