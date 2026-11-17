import { usd } from "../money";

/** Totals from the summary endpoints; decimal strings. */
export type Summary = {
  total_invested_usd: string;
  cost_basis_usd: string;
  realized_pnl_usd: string;
  unrealized_pnl_usd: string;
  total_pnl_usd: string;
};

/** One asset's position and P&L; price fields are null when there is no price. */
export type Position = Summary & {
  asset_id: string;
  asset_symbol: string;
  quantity: string;
  price_usd: string | null;
  price_as_of: string | null;
  price_unavailable: boolean;
  market_value_usd: string | null;
  unrealized_pnl_usd: string | null;
  total_pnl_usd: string | null;
};

/** A P&L value with its sign and the profit or loss style; blank when null. */
export function Pnl({ value, className = "" }: { value: string | null; className?: string }) {
  if (value === null) return null;
  const negative = value.startsWith("-");
  const positive = !negative && /[1-9]/.test(value);
  const style = negative ? "text-red-600" : positive ? "text-green-600" : "";
  return <span className={`${className} ${style}`.trim()}>{positive ? `+${usd(value)}` : usd(value)}</span>;
}

export default function SummaryWidgets({ summary }: { summary: Summary }) {
  const value = "block text-lg font-semibold";
  const widgets = [
    ["Total invested", <span className={value}>{usd(summary.total_invested_usd)}</span>],
    ["Cost basis", <span className={value}>{usd(summary.cost_basis_usd)}</span>],
    ["Realized P&L", <Pnl value={summary.realized_pnl_usd} className={value} />],
    ["Unrealized P&L", <Pnl value={summary.unrealized_pnl_usd} className={value} />],
    ["Total P&L", <Pnl value={summary.total_pnl_usd} className={value} />],
  ] as const;
  return (
    <ul aria-label="Summary" className="grid grid-cols-2 gap-4 sm:grid-cols-5">
      {widgets.map(([label, widget]) => (
        <li key={label} className="rounded border p-3">
          <span className="block text-sm text-gray-500">{label}</span>
          {widget}
        </li>
      ))}
    </ul>
  );
}

export function PositionsTable({ name, positions }: { name: string; positions: Position[] }) {
  return (
    <div className="overflow-x-auto">
      <table aria-label={name} className="w-full text-left">
        <thead>
          <tr>
            {["Asset", "Quantity", "Cost basis", "Price", "Market value", "Realized P&L", "Unrealized P&L", "Total P&L"].map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.asset_id} className="border-t">
              <td>{p.asset_symbol.toUpperCase()}</td>
              <td>{p.quantity}</td>
              <td>{usd(p.cost_basis_usd)}</td>
              <td>{p.price_unavailable ? `price unavailable${p.price_as_of ? ` (last price ${p.price_as_of})` : ""}` : p.price_usd && usd(p.price_usd)}</td>
              <td>{p.market_value_usd && usd(p.market_value_usd)}</td>
              <td><Pnl value={p.realized_pnl_usd} /></td>
              <td><Pnl value={p.unrealized_pnl_usd} /></td>
              <td><Pnl value={p.total_pnl_usd} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
