import { useAuth } from "@clerk/react";
import { type FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../api/client";
import { addQuantities, defaultFee, fifo, isAmount, sumsTo } from "../money";
import { type Buy, Field, today } from "./BuyForm";

/** A sell as the API returns it: the buy fields plus the lots it draws from. */
export type Sell = Buy & { allocations: { id: number; buy_id: number; quantity: string; realized_pnl_usd: string }[] };
type Lot = Buy & { unsold: string };
type Asset = Pick<Buy, "asset_id" | "asset_name" | "asset_symbol">;

const message = (e: unknown) => (e instanceof Error ? e.message : "Request failed");

/** Creates a sell, or edits `sell` when given. The lot table is a FIFO pre-fill the user can edit. */
export default function SellForm({ portfolioId, sell, onSaved }: { portfolioId: string | number; sell?: Sell; onSaved: () => void }) {
  const { getToken } = useAuth();
  // What the sell being edited takes from each lot now; it counts as available again while editing.
  const own: Record<number, string> = Object.fromEntries((sell?.allocations ?? []).map((a) => [a.buy_id, a.quantity]));
  const base = `/api/v1/portfolios/${encodeURIComponent(portfolioId)}`;
  const [assets, setAssets] = useState<Asset[]>(sell ? [sell] : []);
  const [assetId, setAssetId] = useState(sell?.asset_id ?? "");
  const [quantity, setQuantity] = useState(sell?.quantity ?? "");
  const [total, setTotal] = useState(sell?.total_usd ?? "");
  const [fee, setFee] = useState<string | null>(sell?.fee_usd ?? null);
  const [tradeDate, setTradeDate] = useState(() => sell?.trade_date ?? today());
  const [comment, setComment] = useState(sell?.comment ?? "");
  const [lots, setLots] = useState<Lot[]>([]);
  // Lot id → quantity once the user edits the table (or the sell's own allocations); null follows FIFO.
  const [edited, setEdited] = useState<Record<number, string> | null>(sell ? own : null);
  const [error, setError] = useState("");
  const shownFee = fee ?? defaultFee(total);
  const asset = assets.find((a) => a.asset_id === assetId);

  // Assets with open lots; a sell being edited keeps its own asset even if it emptied every lot.
  useEffect(() => {
    apiFetch<Lot[]>(`${base}/lots?open=true`, getToken).then((open) => {
      const byId = new Map<string, Asset>(sell ? [[sell.asset_id, sell]] : []);
      for (const lot of open) byId.set(lot.asset_id, lot);
      setAssets([...byId.values()]);
    }, (e: unknown) => setError(message(e)));
  }, [base, getToken, sell]);

  useEffect(() => {
    if (!assetId || !tradeDate) return;
    let stale = false;
    const query = new URLSearchParams({ asset_id: assetId, as_of: tradeDate });
    apiFetch<Lot[]>(`${base}/lots?${query}`, getToken)
      .then((found) => !stale && setLots(found), (e: unknown) => !stale && setError(message(e)));
    return () => void (stale = true);
  }, [base, getToken, assetId, tradeDate]);

  const open = lots
    .map((lot) => ({ lot, available: addQuantities([lot.unsold, own[lot.id] ?? ""]) ?? "0" }))
    .filter((row) => row.available !== "0");
  const prefill = fifo(open.map((row) => row.available), quantity);
  const values = open.map((row, i) => (edited ? (edited[row.lot.id] ?? "") : prefill[i]));
  const ready = !!asset && sumsTo(values, quantity) && isAmount(total) && isAmount(shownFee);

  function allocate(index: number, value: string) {
    setEdited(Object.fromEntries(open.map((row, i) => [row.lot.id, i === index ? value : values[i]])));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!asset || !ready) return;
    setError("");
    const allocations = open
      .map((row, i) => ({ buy_id: row.lot.id, quantity: values[i] }))
      .filter((a) => addQuantities([a.quantity]) !== "0");
    const body = {
      ...{ asset_id: asset.asset_id, asset_name: asset.asset_name, asset_symbol: asset.asset_symbol, quantity },
      ...{ total_usd: total, fee_usd: shownFee, trade_date: tradeDate, comment: comment || null, allocations },
    };
    try {
      const headers = { "Content-Type": "application/json" };
      const path = `${base}/sells${sell ? `/${encodeURIComponent(sell.id)}` : ""}`;
      await apiFetch(path, getToken, { method: sell ? "PUT" : "POST", headers, body: JSON.stringify(body) });
      onSaved();
    } catch (e) {
      setError(message(e));
    }
  }

  return (
    <form aria-label="Sell" onSubmit={submit} className="space-y-2 rounded border p-4">
      <label className="block">
        Asset
        <select value={assetId} onChange={(e) => (setAssetId(e.target.value), setEdited(null))} className="mt-1 block w-full rounded border px-2 py-1">
          <option value="">Choose an open position</option>
          {assets.map((a) => (
            <option key={a.asset_id} value={a.asset_id}>{`${a.asset_name} (${a.asset_symbol.toUpperCase()})`}</option>
          ))}
        </select>
      </label>
      <Field label="Quantity" inputMode="decimal" value={quantity} onChange={(e) => (setQuantity(e.target.value), setEdited(null))} />
      <Field label="Total (USD)" inputMode="decimal" value={total} onChange={(e) => setTotal(e.target.value)} />
      <Field label="Fee (USD)" inputMode="decimal" value={shownFee} onChange={(e) => setFee(e.target.value)} />
      <Field label="Trade date" type="date" value={tradeDate} onChange={(e) => (setTradeDate(e.target.value), setEdited(null))} />
      <Field label="Comment" value={comment} onChange={(e) => setComment(e.target.value)} />
      {asset && (
        <table aria-label="Lots" className="w-full text-left">
          <thead>
            <tr>{["Lot", "Bought", "Available", "Sell from lot"].map((h) => <th key={h} className="px-2">{h}</th>)}</tr>
          </thead>
          <tbody>
            {open.map(({ lot, available }, i) => (
              <tr key={lot.id} className="border-t">
                {[lot.id, lot.trade_date, available].map((text, j) => <td key={j} className="px-2">{text}</td>)}
                <td className="px-2">
                  <input aria-label={`Allocation from lot ${lot.id}`} inputMode="decimal" value={values[i]}
                    onChange={(e) => allocate(i, e.target.value)} className="w-full rounded border px-2 py-1" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      <button type="submit" disabled={!ready} className="rounded bg-blue-600 px-3 py-1 text-white disabled:opacity-50">
        Save sell
      </button>
    </form>
  );
}
