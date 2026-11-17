import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import HomePage from "./HomePage";

const auth = vi.hoisted(() => ({ getToken: async () => "mock-token" }));
vi.mock("@clerk/react", () => ({ useAuth: () => auth }));

const fetchMock = vi.fn<typeof fetch>();
const API = "https://api.example.test";

beforeEach(() => {
  vi.stubEnv("VITE_API_BASE_URL", API);
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

/** The README example: lots of $30k and $50k BTC, lot A sold for $60k, BTC now $60k. */
const btc = {
  ...{ asset_id: "bitcoin", asset_name: "Bitcoin", asset_symbol: "btc", quantity: "1" },
  ...{ total_invested_usd: "80000", cost_basis_usd: "50000", average_buy_price_usd: "50000", realized_pnl_usd: "30000" },
  ...{ price_usd: "60000", price_as_of: "2026-11-17T10:00:00Z", price_unavailable: false },
  ...{ market_value_usd: "60000", unrealized_pnl_usd: "10000", total_pnl_usd: "40000" },
};
const summary = {
  ...{ total_invested_usd: "80000", cost_basis_usd: "50000", realized_pnl_usd: "30000", market_value_usd: "60000" },
  ...{ unrealized_pnl_usd: "10000", total_pnl_usd: "40000", partial: false, assets: [btc] },
};

function renderPage(body: unknown) {
  fetchMock.mockImplementation(async (url) => {
    if (url !== `${API}/api/v1/summary`) throw new Error(`unexpected ${String(url)}`);
    return new Response(JSON.stringify(body), { status: 200 });
  });
  render(<HomePage />);
}

/** Each widget as [label, value element]. */
async function widgets() {
  const list = await screen.findByRole("list", { name: "Summary" });
  return within(list).getAllByRole("listitem").map((item) => {
    const [label, value] = item.children;
    return [label.textContent, value] as const;
  });
}

/** Cell texts of each body row of the table named `name`. */
async function rows(name: string) {
  const table = await screen.findByRole("table", { name });
  return within(table.querySelector("tbody")!)
    .queryAllByRole("row")
    .map((row) => within(row).getAllByRole("cell").map((cell) => cell.textContent));
}

test("the overview shows the README example's totals in the five widgets", async () => {
  renderPage(summary);

  expect((await widgets()).map(([label, value]) => [label, value.textContent])).toEqual([
    ["Total invested", "$80,000.00"],
    ["Cost basis", "$50,000.00"],
    ["Realized P&L", "+$30,000.00"],
    ["Unrealized P&L", "+$10,000.00"],
    ["Total P&L", "+$40,000.00"],
  ]);
  expect(await rows("Assets")).toEqual([
    ["BTC", "1", "$50,000.00", "$60,000.00", "$60,000.00", "+$30,000.00", "+$10,000.00", "+$40,000.00"],
  ]);
});

test("a negative P&L renders with a minus sign and the loss style, a positive one with the profit style", async () => {
  renderPage({ ...summary, realized_pnl_usd: "-1234.565", unrealized_pnl_usd: "0", total_pnl_usd: "250.5" });

  const [, , realized, unrealized, total] = await widgets();
  expect(realized[1].textContent).toBe("-$1,234.57");
  expect(realized[1].className).toContain("text-red-600");
  expect(realized[1].className).not.toContain("text-green-600");
  expect(total[1].textContent).toBe("+$250.50");
  expect(total[1].className).toContain("text-green-600");
  expect(total[1].className).not.toContain("text-red-600");
  expect(unrealized[1].textContent).toBe("$0.00");
  expect(unrealized[1].className).not.toMatch(/text-(red|green)-600/);
});

test("an asset whose price is unavailable shows 'price unavailable' and no unrealized value", async () => {
  const eth = {
    ...btc, asset_id: "ethereum", asset_name: "Ethereum", asset_symbol: "eth", average_buy_price_usd: "2000", cost_basis_usd: "2000",
    ...{ realized_pnl_usd: "0", price_usd: null, price_as_of: null, price_unavailable: true },
    ...{ market_value_usd: null, unrealized_pnl_usd: null, total_pnl_usd: null },
  };
  const stale = { ...eth, asset_symbol: "sol", price_as_of: "2026-11-16T09:30:00Z" };
  renderPage({ ...summary, partial: true, assets: [btc, eth, stale] });

  const [, ethRow, solRow] = await rows("Assets");
  expect(ethRow).toEqual(["ETH", "1", "$2,000.00", "price unavailable", "", "$0.00", "", ""]);
  expect(solRow[3]).toBe("price unavailable (last price 2026-11-16T09:30:00Z)");
  expect(solRow[6]).toBe("");
});
