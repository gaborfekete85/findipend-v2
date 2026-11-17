import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import PortfolioDetailPage from "./PortfolioDetailPage";

// Clerk memoizes getToken, so the mock hands out one stable function too.
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

const json = (status: number, body: unknown) => () => new Response(JSON.stringify(body), { status });

function buy(id: number, overrides: Record<string, unknown> = {}) {
  return {
    ...{ id, portfolio_id: 1, asset_id: "bitcoin", asset_name: "Bitcoin", asset_symbol: "btc" },
    ...{ quantity: "1.000000000000000000", total_usd: "30000.00000000", fee_usd: "30.00000000" },
    ...{ trade_date: "2026-01-02", comment: null, created_at: "", updated_at: "" },
    ...overrides,
  };
}

/** Renders `entry` (default /portfolios/1). Each "METHOD path" answers from its queue; the last answer repeats. */
function renderPage(routes: Record<string, (() => Response)[]>, entry = "/portfolios/1") {
  routes["GET /api/v1/portfolios/1"] = [json(200, { id: 1, name: "Long term" })];
  fetchMock.mockImplementation(async (url, init) => {
    const queue = routes[`${init?.method ?? "GET"} ${String(url).replace(API, "")}`];
    return (queue.length > 1 ? queue.shift()! : queue[0])();
  });
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/portfolios/:id" element={<PortfolioDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function sent(method: string, path: string) {
  return fetchMock.mock.calls
    .filter(([url, init]) => init?.method === method && url === `${API}${path}`)
    .map(([, init]) => ({ body: JSON.parse(String(init!.body)), type: new Headers(init!.headers).get("Content-Type") }));
}

/** Cell texts of each history row, without the actions column. */
async function historyRows() {
  const body = (await screen.findByRole("table", { name: "Transaction history" })).querySelector("tbody")!;
  return within(body)
    .queryAllByRole("row")
    .map((row) => within(row).getAllByRole("cell").slice(0, -1).map((cell) => cell.textContent));
}

test("submitting the buy form posts every field as a string and the buy appears in the history", async () => {
  const created = buy(5, { quantity: "0.5", total_usd: "1000.00000000", fee_usd: "1.00000000", trade_date: "2026-11-10", comment: "first" });
  renderPage({
    "GET /api/v1/portfolios/1/buys": [json(200, []), json(200, [created])],
    "GET /api/v1/assets?query=bit": [json(200, [{ id: "bitcoin", symbol: "btc", name: "Bitcoin" }, { id: "bitcoin-cash", symbol: "bch", name: "Bitcoin Cash" }])],
    "POST /api/v1/portfolios/1/buys": [json(201, created)],
  });
  expect(await historyRows()).toEqual([]);

  fireEvent.click(screen.getByRole("button", { name: "Add buy" }));
  const form = screen.getByRole("form", { name: "Buy" });
  const type = (label: string, value: string) => fireEvent.change(within(form).getByLabelText(label), { target: { value } });
  type("Search asset", "bit");
  fireEvent.click(await within(form).findByRole("button", { name: "Bitcoin (BTC)" }));
  type("Quantity", "0.5");
  type("Total (USD)", "1000");
  type("Trade date", "2026-11-10");
  type("Comment", "first");
  fireEvent.click(within(form).getByRole("button", { name: "Save buy" }));

  await vi.waitFor(async () => expect(await historyRows()).toEqual([["2026-11-10", "Buy", "BTC", "0.5", "$1,000.00", "$1.00", "first"]]));
  expect(sent("POST", "/api/v1/portfolios/1/buys")).toEqual([
    {
      body: { asset_id: "bitcoin", asset_name: "Bitcoin", asset_symbol: "btc", quantity: "0.5", total_usd: "1000", fee_usd: "1.00", trade_date: "2026-11-10", comment: "first" },
      type: "application/json",
    },
  ]);
  expect(screen.queryByRole("form", { name: "Buy" })).toBeNull();
});

test("editing a buy sends a PUT with the new values and keeps its own fee", async () => {
  const edited = buy(1, { quantity: "2" });
  renderPage({
    "GET /api/v1/portfolios/1/buys": [json(200, [buy(1)]), json(200, [edited])],
    "PUT /api/v1/portfolios/1/buys/1": [json(200, edited)],
  });
  await historyRows();

  fireEvent.click(screen.getByRole("button", { name: "Edit buy 1" }));
  const form = screen.getByRole("form", { name: "Buy" });
  fireEvent.change(within(form).getByLabelText("Quantity"), { target: { value: "2" } });
  fireEvent.change(within(form).getByLabelText("Total (USD)"), { target: { value: "60000" } });
  fireEvent.click(within(form).getByRole("button", { name: "Save buy" }));

  await vi.waitFor(async () => expect((await historyRows())[0][3]).toBe("2"));
  expect(sent("PUT", "/api/v1/portfolios/1/buys/1").map((r) => r.body)).toEqual([
    { asset_id: "bitcoin", asset_name: "Bitcoin", asset_symbol: "btc", quantity: "2", total_usd: "60000", fee_usd: "30.00000000", trade_date: "2026-01-02", comment: null },
  ]);
});

test("deleting a buy that the API rejects with 409 shows the API's message and keeps the row", async () => {
  const conflict = "Lot 2 is allocated to sell 7; delete or re-allocate that sell first";
  const eth = { asset_symbol: "eth", total_usd: "1234.56789000", fee_usd: "1.00500000", trade_date: "2026-03-04", comment: "dip" };
  renderPage({
    "GET /api/v1/portfolios/1/buys": [json(200, [buy(1), buy(2, eth)])],
    "DELETE /api/v1/portfolios/1/buys/2": [json(409, { detail: conflict })],
    "DELETE /api/v1/portfolios/1/buys/1": [() => new Response(null, { status: 204 })],
  });
  // The history shows USD rounded half up to 2 decimals.
  const rows = [
    ["2026-01-02", "Buy", "BTC", "1.000000000000000000", "$30,000.00", "$30.00", ""],
    ["2026-03-04", "Buy", "ETH", "1.000000000000000000", "$1,234.57", "$1.01", "dip"],
  ];
  expect(await historyRows()).toEqual(rows);
  expect(await screen.findByRole("heading", { level: 1, name: "Long term" })).toBeTruthy();

  fireEvent.click(screen.getByRole("button", { name: "Delete buy 2" }));
  expect((await screen.findByRole("alert")).textContent).toBe(conflict);
  expect(await historyRows()).toEqual(rows);

  fireEvent.click(screen.getByRole("button", { name: "Delete buy 1" }));
  await vi.waitFor(async () => expect((await historyRows()).map((row) => row[0])).toEqual(["2026-03-04"]));
  expect(screen.queryByRole("alert")).toBeNull();
});

test.each(["/portfolios/abc", "/portfolios/1%2F..%2F..%2Fsummary", "/portfolios/1.5", "/portfolios/-1"])(
  "opening %s shows a not-found message and sends no API request",
  async (entry) => {
    renderPage({}, entry);

    expect((await screen.findByRole("alert")).textContent).toBe("Portfolio not found");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Add buy" })).toBeNull();
  },
);

test("buy ids are passed through encodeURIComponent when building paths", async () => {
  // The API types ids as numbers; a non-numeric one still cannot leave its path segment.
  renderPage({
    "GET /api/v1/portfolios/1/buys": [json(200, [buy("9/../x" as unknown as number)])],
    "DELETE /api/v1/portfolios/1/buys/9%2F..%2Fx": [() => new Response(null, { status: 204 })],
  });
  await historyRows();

  fireEvent.click(screen.getByRole("button", { name: "Delete buy 9/../x" }));

  await vi.waitFor(() => expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "DELETE")).toHaveLength(1));
  expect(fetchMock.mock.calls.map(([url, init]) => `${init?.method ?? "GET"} ${String(url).replace(API, "")}`)).toContain(
    "DELETE /api/v1/portfolios/1/buys/9%2F..%2Fx",
  );
});
