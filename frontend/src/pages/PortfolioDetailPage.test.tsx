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

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function buy(id: number, overrides: Record<string, unknown> = {}) {
  return {
    id,
    portfolio_id: 1,
    asset_id: "bitcoin",
    asset_name: "Bitcoin",
    asset_symbol: "btc",
    quantity: "1.000000000000000000",
    total_usd: "30000.00000000",
    fee_usd: "30.00000000",
    trade_date: "2026-01-02",
    comment: null,
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-01T10:00:00Z",
    ...overrides,
  };
}

type Handler = () => Response;

/** Answers each "METHOD path" from a queue; the last response in a queue repeats. */
function mockApi(routes: Record<string, Handler[]>) {
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input).replace(API, "");
    const key = `${init?.method ?? "GET"} ${url}`;
    const queue = routes[key];
    if (!queue) throw new Error(`unexpected request ${key}`);
    return (queue.length > 1 ? queue.shift()! : queue[0])();
  });
}

function requests(method: string, path: string) {
  return fetchMock.mock.calls
    .filter(([url, init]) => (init?.method ?? "GET") === method && String(url) === `${API}${path}`)
    .map(([, init]) => ({
      body: init?.body === undefined ? undefined : JSON.parse(String(init.body)),
      contentType: new Headers(init?.headers).get("Content-Type"),
      auth: new Headers(init?.headers).get("Authorization"),
    }));
}

const portfolio = { id: 1, name: "Long term", created_at: "2026-11-01T10:00:00Z", updated_at: "2026-11-01T10:00:00Z" };

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/portfolios/1"]}>
      <Routes>
        <Route path="/portfolios/:id" element={<PortfolioDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

/** Cell texts of each history row, without the actions column. */
async function historyRows() {
  const table = await screen.findByRole("table", { name: "Transaction history" });
  const body = table.querySelector("tbody")!;
  return within(body)
    .queryAllByRole("row")
    .map((row) =>
      within(row)
        .getAllByRole("cell")
        .slice(0, -1)
        .map((cell) => cell.textContent),
    );
}

test("shows the portfolio name and its buys, USD rounded to 2 decimals", async () => {
  mockApi({
    "GET /api/v1/portfolios/1": [() => jsonResponse(200, portfolio)],
    "GET /api/v1/portfolios/1/buys": [
      () =>
        jsonResponse(200, [
          buy(1),
          buy(2, {
            asset_id: "ethereum",
            asset_name: "Ethereum",
            asset_symbol: "eth",
            quantity: "2.500000000000000000",
            total_usd: "1234.56789000",
            fee_usd: "1.00500000",
            trade_date: "2026-02-03",
            comment: "dip",
          }),
        ]),
    ],
  });

  renderPage();

  expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe("Long term");
  expect(await historyRows()).toEqual([
    ["2026-01-02", "Buy", "BTC", "1.000000000000000000", "$30,000.00", "$30.00", ""],
    ["2026-02-03", "Buy", "ETH", "2.500000000000000000", "$1,234.57", "$1.01", "dip"],
  ]);
});

test("submitting the buy form posts every field as a string and the buy appears in the history", async () => {
  const created = buy(5, {
    quantity: "0.500000000000000000",
    total_usd: "1000.00000000",
    fee_usd: "1.00000000",
    trade_date: "2026-11-10",
    comment: "first",
  });
  mockApi({
    "GET /api/v1/portfolios/1": [() => jsonResponse(200, portfolio)],
    "GET /api/v1/portfolios/1/buys": [() => jsonResponse(200, []), () => jsonResponse(200, [created])],
    "GET /api/v1/assets?query=bit": [
      () =>
        jsonResponse(200, [
          { id: "bitcoin", symbol: "btc", name: "Bitcoin" },
          { id: "bitcoin-cash", symbol: "bch", name: "Bitcoin Cash" },
        ]),
    ],
    "POST /api/v1/portfolios/1/buys": [() => jsonResponse(201, created)],
  });
  renderPage();
  expect(await historyRows()).toEqual([]);

  fireEvent.click(screen.getByRole("button", { name: "Add buy" }));
  const form = screen.getByRole("form", { name: "Buy" });
  fireEvent.change(within(form).getByLabelText("Search asset"), { target: { value: "bit" } });
  fireEvent.click(await within(form).findByRole("button", { name: "Bitcoin (BTC)" }));
  fireEvent.change(within(form).getByLabelText("Quantity"), { target: { value: "0.5" } });
  fireEvent.change(within(form).getByLabelText("Total (USD)"), { target: { value: "1000" } });
  fireEvent.change(within(form).getByLabelText("Trade date"), { target: { value: "2026-11-10" } });
  fireEvent.change(within(form).getByLabelText("Comment"), { target: { value: "first" } });
  fireEvent.click(within(form).getByRole("button", { name: "Save buy" }));

  await vi.waitFor(async () =>
    expect(await historyRows()).toEqual([
      ["2026-11-10", "Buy", "BTC", "0.500000000000000000", "$1,000.00", "$1.00", "first"],
    ]),
  );
  expect(requests("POST", "/api/v1/portfolios/1/buys")).toEqual([
    {
      body: {
        asset_id: "bitcoin",
        asset_name: "Bitcoin",
        asset_symbol: "btc",
        quantity: "0.5",
        total_usd: "1000",
        fee_usd: "1.00",
        trade_date: "2026-11-10",
        comment: "first",
      },
      contentType: "application/json",
      auth: "Bearer mock-token",
    },
  ]);
  expect(screen.queryByRole("form", { name: "Buy" })).toBeNull();
});

test("a rejected create shows the API's message in the form and adds nothing", async () => {
  mockApi({
    "GET /api/v1/portfolios/1": [() => jsonResponse(200, portfolio)],
    "GET /api/v1/portfolios/1/buys": [() => jsonResponse(200, [])],
    "GET /api/v1/assets?query=btc": [() => jsonResponse(200, [{ id: "bitcoin", symbol: "btc", name: "Bitcoin" }])],
    "POST /api/v1/portfolios/1/buys": [
      () => jsonResponse(422, { detail: [{ loc: ["body", "quantity"], msg: "Input should be greater than 0" }] }),
    ],
  });
  renderPage();
  await historyRows();

  fireEvent.click(screen.getByRole("button", { name: "Add buy" }));
  const form = screen.getByRole("form", { name: "Buy" });
  fireEvent.change(within(form).getByLabelText("Search asset"), { target: { value: "btc" } });
  fireEvent.click(await within(form).findByRole("button", { name: "Bitcoin (BTC)" }));
  fireEvent.change(within(form).getByLabelText("Quantity"), { target: { value: "0" } });
  fireEvent.change(within(form).getByLabelText("Total (USD)"), { target: { value: "10" } });
  fireEvent.click(within(form).getByRole("button", { name: "Save buy" }));

  expect((await within(form).findByRole("alert")).textContent).toBe("quantity: Input should be greater than 0");
  expect(await historyRows()).toEqual([]);
});

test("editing a buy sends a PUT with the changed fields and keeps its fee", async () => {
  const edited = buy(1, { quantity: "2.000000000000000000" });
  mockApi({
    "GET /api/v1/portfolios/1": [() => jsonResponse(200, portfolio)],
    "GET /api/v1/portfolios/1/buys": [() => jsonResponse(200, [buy(1)]), () => jsonResponse(200, [edited])],
    "PUT /api/v1/portfolios/1/buys/1": [() => jsonResponse(200, edited)],
  });
  renderPage();
  await historyRows();

  fireEvent.click(screen.getByRole("button", { name: "Edit buy 1" }));
  const form = screen.getByRole("form", { name: "Buy" });
  fireEvent.change(within(form).getByLabelText("Quantity"), { target: { value: "2" } });
  fireEvent.change(within(form).getByLabelText("Total (USD)"), { target: { value: "60000" } });
  fireEvent.click(within(form).getByRole("button", { name: "Save buy" }));

  await vi.waitFor(async () => expect((await historyRows())[0][3]).toBe("2.000000000000000000"));
  expect(requests("PUT", "/api/v1/portfolios/1/buys/1").map((r) => r.body)).toEqual([
    {
      asset_id: "bitcoin",
      asset_name: "Bitcoin",
      asset_symbol: "btc",
      quantity: "2",
      total_usd: "60000",
      fee_usd: "30.00000000",
      trade_date: "2026-01-02",
      comment: null,
    },
  ]);
});

test("deleting a buy that the API rejects with 409 shows the API's message and keeps the row", async () => {
  mockApi({
    "GET /api/v1/portfolios/1": [() => jsonResponse(200, portfolio)],
    "GET /api/v1/portfolios/1/buys": [() => jsonResponse(200, [buy(1), buy(2, { trade_date: "2026-03-04" })])],
    "DELETE /api/v1/portfolios/1/buys/2": [
      () => jsonResponse(409, { detail: "Lot 2 is allocated to sell 7; delete or re-allocate that sell first" }),
    ],
  });
  renderPage();
  expect((await historyRows()).map((row) => row[0])).toEqual(["2026-01-02", "2026-03-04"]);

  fireEvent.click(screen.getByRole("button", { name: "Delete buy 2" }));

  expect((await screen.findByRole("alert")).textContent).toBe(
    "Lot 2 is allocated to sell 7; delete or re-allocate that sell first",
  );
  expect((await historyRows()).map((row) => row[0])).toEqual(["2026-01-02", "2026-03-04"]);
  expect(requests("DELETE", "/api/v1/portfolios/1/buys/2")).toHaveLength(1);
});

test("deleting a buy the API accepts removes only that row", async () => {
  mockApi({
    "GET /api/v1/portfolios/1": [() => jsonResponse(200, portfolio)],
    "GET /api/v1/portfolios/1/buys": [() => jsonResponse(200, [buy(1), buy(2, { trade_date: "2026-03-04" })])],
    "DELETE /api/v1/portfolios/1/buys/1": [() => new Response(null, { status: 204 })],
  });
  renderPage();
  await historyRows();

  fireEvent.click(screen.getByRole("button", { name: "Delete buy 1" }));

  await vi.waitFor(async () => expect((await historyRows()).map((row) => row[0])).toEqual(["2026-03-04"]));
  expect(screen.queryByRole("alert")).toBeNull();
});
