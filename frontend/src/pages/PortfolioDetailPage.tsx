import { useAuth } from "@clerk/react";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router";
import { apiFetch } from "../api/client";
import BuyForm, { type Buy } from "../components/BuyForm";
import { usd } from "../money";

const message = (e: unknown) => (e instanceof Error ? e.message : "Request failed");

export default function PortfolioDetailPage() {
  const { id = "" } = useParams();
  // A non-numeric id would put attacker-chosen segments into signed-in API paths.
  if (!/^\d+$/.test(id)) return <p role="alert" className="p-8">Portfolio not found</p>;
  return <PortfolioDetail id={id} />;
}

function PortfolioDetail({ id }: { id: string }) {
  const { getToken } = useAuth();
  const [name, setName] = useState("");
  const [buys, setBuys] = useState<Buy[] | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<Buy | "new" | null>(null);
  const path = `/api/v1/portfolios/${encodeURIComponent(id)}`;

  const loadBuys = useCallback(() => {
    apiFetch<Buy[]>(`${path}/buys`, getToken).then(setBuys, (e: unknown) => setError(message(e)));
  }, [path, getToken]);

  useEffect(() => {
    apiFetch<{ name: string }>(path, getToken).then((p) => setName(p.name), (e: unknown) => setError(message(e)));
    loadBuys();
  }, [path, getToken, loadBuys]);

  async function remove(buy: Buy) {
    setError("");
    try {
      await apiFetch<void>(`${path}/buys/${encodeURIComponent(buy.id)}`, getToken, { method: "DELETE" });
      setBuys((list) => (list ?? []).filter((b) => b.id !== buy.id));
    } catch (e) {
      setError(message(e));
    }
  }

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-8">
      <h1 className="text-3xl font-bold">{name}</h1>
      {editing && (
        <BuyForm
          key={editing === "new" ? "new" : editing.id}
          portfolioId={id}
          buy={editing === "new" ? undefined : editing}
          onSaved={() => (setEditing(null), loadBuys())}
        />
      )}
      <button type="button" onClick={() => setEditing(editing ? null : "new")} className="rounded border px-3 py-1">
        {editing ? "Cancel" : "Add buy"}
      </button>
      {error && <p role="alert" className="text-red-600">{error}</p>}
      {buys && (
        <table aria-label="Transaction history" className="w-full text-left">
          <thead>
            <tr>
              {["Date", "Type", "Asset", "Quantity", "Total", "Fee", "Comment", ""].map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {buys.map((buy) => (
              <tr key={buy.id} className="border-t">
                {[buy.trade_date, "Buy", buy.asset_symbol.toUpperCase(), buy.quantity, usd(buy.total_usd), usd(buy.fee_usd), buy.comment]
                  .map((text, i) => <td key={i}>{text}</td>)}
                <td className="space-x-2">
                  <button type="button" aria-label={`Edit buy ${buy.id}`} onClick={() => setEditing(buy)}>
                    Edit
                  </button>
                  <button type="button" aria-label={`Delete buy ${buy.id}`} onClick={() => remove(buy)} className="text-red-600">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
