import { useAuth } from "@clerk/react";
import { Fragment, useCallback, useEffect, useState } from "react";
import { useParams } from "react-router";
import { apiFetch } from "../api/client";
import BuyForm, { type Buy } from "../components/BuyForm";
import SellForm, { type Sell } from "../components/SellForm";
import SummaryWidgets, { PositionsTable, type Position, type Summary } from "../components/SummaryWidgets";
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
  const [sells, setSells] = useState<Sell[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [positions, setPositions] = useState<{ open: Position[]; closed: Position[] } | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<{ kind: "buy" | "sell"; tx?: Buy } | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const path = `/api/v1/portfolios/${encodeURIComponent(id)}`;

  // P&L changes with every buy or sell, so it reloads with the history and after a delete.
  const loadPnl = useCallback(() => {
    apiFetch<Summary>(`${path}/summary`, getToken).then(setSummary, (e: unknown) => setError(message(e)));
    apiFetch<{ open: Position[]; closed: Position[] }>(`${path}/positions`, getToken).then(setPositions, (e: unknown) => setError(message(e)));
  }, [path, getToken]);

  const loadHistory = useCallback(() => {
    apiFetch<Buy[]>(`${path}/buys`, getToken).then(setBuys, (e: unknown) => setError(message(e)));
    apiFetch<Sell[]>(`${path}/sells`, getToken).then(setSells, (e: unknown) => setError(message(e)));
    loadPnl();
  }, [path, getToken, loadPnl]);

  useEffect(() => {
    apiFetch<{ name: string }>(path, getToken).then((p) => setName(p.name), (e: unknown) => setError(message(e)));
    loadHistory();
  }, [path, getToken, loadHistory]);

  async function remove(kind: "buy" | "sell", txId: number) {
    setError("");
    try {
      await apiFetch<void>(`${path}/${kind}s/${encodeURIComponent(txId)}`, getToken, { method: "DELETE" });
      if (kind === "buy") setBuys((list) => (list ?? []).filter((b) => b.id !== txId));
      else setSells((list) => list.filter((s) => s.id !== txId));
      loadPnl();
    } catch (e) {
      setError(message(e));
    }
  }

  const saved = () => (setEditing(null), loadHistory());
  const toggle = (kind: "buy" | "sell") => setEditing(editing ? null : { kind });
  // Buys before sells on the same date: a sell can only draw from lots bought on or before it.
  const history = [
    ...(buys ?? []).map((tx) => ({ kind: "buy" as const, tx })),
    ...sells.map((tx) => ({ kind: "sell" as const, tx })),
  ].sort((a, b) => a.tx.trade_date.localeCompare(b.tx.trade_date));
  const lotDate = (buyId: number) => buys?.find((b) => b.id === buyId)?.trade_date;

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-8">
      <h1 className="text-3xl font-bold">{name}</h1>
      {summary && <SummaryWidgets summary={summary} />}
      {positions && (
        <>
          <PositionsTable name="Open positions" positions={positions.open} />
          <PositionsTable name="Closed positions" positions={positions.closed} />
        </>
      )}
      {editing?.kind === "buy" && <BuyForm key={editing.tx?.id ?? "new"} portfolioId={id} buy={editing.tx} onSaved={saved} />}
      {editing?.kind === "sell" && <SellForm key={editing.tx?.id ?? "new"} portfolioId={id} sell={editing.tx as Sell | undefined} onSaved={saved} />}
      <button type="button" onClick={() => toggle("buy")} className="mr-2 rounded border px-3 py-1">
        {editing ? "Cancel" : "Add buy"}
      </button>
      {!editing && <button type="button" onClick={() => toggle("sell")} className="rounded border px-3 py-1">Add sell</button>}
      {error && <p role="alert" className="text-red-600">{error}</p>}
      {buys && (
        <div className="overflow-x-auto">
          <table aria-label="Transaction history" className="w-full text-left">
            <thead>
              <tr>
                {["Date", "Type", "Asset", "Quantity", "Total", "Fee", "Comment", ""].map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.map(({ kind, tx }) => (
                <Fragment key={`${kind}-${tx.id}`}>
                  <tr className="border-t">
                    {[tx.trade_date, kind === "buy" ? "Buy" : "Sell", tx.asset_symbol.toUpperCase(), tx.quantity, usd(tx.total_usd), usd(tx.fee_usd), tx.comment]
                      .map((text, i) => <td key={i}>{text}</td>)}
                    <td className="space-x-2">
                      {kind === "sell" && (
                        <button type="button" aria-label={`Allocations of sell ${tx.id}`} aria-expanded={expanded === tx.id}
                          onClick={() => setExpanded(expanded === tx.id ? null : tx.id)}>Lots</button>
                      )}
                      <button type="button" aria-label={`Edit ${kind} ${tx.id}`} onClick={() => setEditing({ kind, tx })}>
                        Edit
                      </button>
                      <button type="button" aria-label={`Delete ${kind} ${tx.id}`} onClick={() => remove(kind, tx.id)} className="text-red-600">
                        Delete
                      </button>
                    </td>
                  </tr>
                  {kind === "sell" && expanded === tx.id && (
                    <tr>
                      <td colSpan={8}>
                        <table aria-label={`Allocations of sell ${tx.id}`} className="sticky left-0 ml-6 text-left text-sm">
                          <thead>
                            <tr>{["Lot", "Quantity", "Realized P&L"].map((h) => <th key={h} className="px-2">{h}</th>)}</tr>
                          </thead>
                          <tbody>
                            {(tx as Sell).allocations.map((a) => (
                              <tr key={a.id}>
                                <td className="px-2">{`Lot ${a.buy_id}${lotDate(a.buy_id) ? ` (${lotDate(a.buy_id)})` : ""}`}</td>
                                <td className="px-2">{a.quantity}</td>
                                <td className="px-2">{usd(a.realized_pnl_usd)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
