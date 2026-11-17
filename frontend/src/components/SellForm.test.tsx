import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import SellForm from "./SellForm";

const auth = vi.hoisted(() => ({ getToken: async () => "mock-token" }));
vi.mock("@clerk/react", () => ({ useAuth: () => auth }));

const API = "https://api.example.test";
const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => (vi.stubEnv("VITE_API_BASE_URL", API), vi.stubGlobal("fetch", fetchMock)));
afterEach(() => (cleanup(), vi.unstubAllEnvs(), vi.unstubAllGlobals(), fetchMock.mockReset()));

function lot(id: number, unsold: string, trade_date: string) {
  return {
    ...{ id, portfolio_id: 1, asset_id: "bitcoin", asset_name: "Bitcoin", asset_symbol: "btc", unsold },
    ...{ quantity: unsold, total_usd: "1000.00000000", fee_usd: "1.00000000", trade_date, comment: null },
  };
}

const input = (name: string) => screen.getByLabelText(name) as HTMLInputElement;
const type = (name: string, value: string) => fireEvent.change(input(name), { target: { value } });
const submit = () => screen.getByRole("button", { name: "Save sell" }) as HTMLButtonElement;

/** Serves GET .../lots with `lots` and POST .../sells with `post`; renders the form, picks Bitcoin, waits for the lots. */
async function open(lots: ReturnType<typeof lot>[], post = () => new Response("{}", { status: 201 })) {
  fetchMock.mockImplementation(async (url, init) => {
    const { pathname } = new URL(String(url));
    if (init?.method === "POST" && pathname === "/api/v1/portfolios/1/sells") return post();
    return new Response(pathname === "/api/v1/portfolios/1/lots" ? JSON.stringify(lots) : null, { status: 200 });
  });
  render(<SellForm portfolioId={1} onSaved={() => {}} />);
  await screen.findByRole("option", { name: "Bitcoin (BTC)" });
  fireEvent.change(input("Asset"), { target: { value: "bitcoin" } });
  type("Trade date", "2026-11-10");
  await screen.findByLabelText(`Allocation from lot ${lots[0].id}`);
}

test("with open lots 0.5 (older) and 1.0 (newer), quantity 0.8 pre-fills 0.5 and 0.3 oldest first", async () => {
  await open([lot(1, "0.5", "2026-01-01"), lot(2, "1", "2026-02-01")]);

  type("Quantity", "0.8");

  expect([input("Allocation from lot 1").value, input("Allocation from lot 2").value]).toEqual(["0.5", "0.3"]);
  const lotsUrls = fetchMock.mock.calls.map(([url]) => new URL(String(url))).filter((u) => u.searchParams.has("asset_id"));
  expect(Object.fromEntries(lotsUrls.at(-1)!.searchParams)).toEqual({ asset_id: "bitcoin", as_of: "2026-11-10" });
});

test.each([
  ["0.2", false],
  ["0.4", false],
  ["0.3", true],
  ["", false],
])("allocations 0.5 + %j against quantity 0.8: submit enabled is %s", async (second, enabled) => {
  await open([lot(1, "0.5", "2026-01-01"), lot(2, "1", "2026-02-01")]);
  type("Quantity", "0.8");

  type("Allocation from lot 2", second);

  expect(submit().disabled).toBe(!enabled);
});

test.each([
  [["0.1", "0.2", "0.5"]],
  [["0.5", "0.2", "0.1"]], // 0.5 + 0.2 + 0.1 is 0.7999999999999999 in floats
  [["0.000000000000000001", "0.799999999999999999", "0"]],
])("allocations %j sum exactly to 0.8 and enable submit", async (unsold) => {
  await open(unsold.map((q, i) => lot(i + 1, q === "0" ? "1" : q, `2026-01-0${i + 1}`)));
  type("Quantity", "0.8");
  unsold.forEach((q, i) => type(`Allocation from lot ${i + 1}`, q));

  expect(submit().disabled).toBe(false);
});

test("submitting posts string quantities with allocations [{buy_id, quantity}]; a 409 shows the API message", async () => {
  const conflict = "Lot 2 has only 0.2 unsold";
  await open([lot(1, "0.5", "2026-01-01"), lot(2, "1", "2026-02-01")], () =>
    new Response(JSON.stringify({ detail: conflict }), { status: 409 }),
  );
  type("Quantity", "0.8");
  type("Total (USD)", "48000");
  type("Fee (USD)", "48");
  type("Comment", "trim");

  fireEvent.click(submit());

  expect((await screen.findByRole("alert")).textContent).toBe(conflict);
  const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(posts.map(([, init]) => JSON.parse(String(init!.body)))).toEqual([
    {
      ...{ asset_id: "bitcoin", asset_name: "Bitcoin", asset_symbol: "btc", quantity: "0.8", total_usd: "48000" },
      ...{ fee_usd: "48", trade_date: "2026-11-10", comment: "trim" },
      allocations: [{ buy_id: 1, quantity: "0.5" }, { buy_id: 2, quantity: "0.3" }],
    },
  ]);
});
