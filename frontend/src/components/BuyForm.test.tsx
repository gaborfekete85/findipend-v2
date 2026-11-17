import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import BuyForm from "./BuyForm";

vi.mock("@clerk/react", () => ({ useAuth: () => ({ getToken: async () => "mock-token" }) }));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function renderForm() {
  render(<BuyForm portfolioId={1} onSaved={() => {}} />);
  const input = (label: string) => screen.getByLabelText(label) as HTMLInputElement;
  return { total: input("Total (USD)"), fee: input("Fee (USD)"), date: input("Trade date") };
}

test.each([
  ["1000", "1.00"],
  ["2500.50", "2.50"],
  ["123.45", "0.12"],
  ["5", "0.01"],
  ["4", "0.00"],
  ["", ""],
])("typing total %j pre-fills fee %j (0.1 percent, rounded half up to cents)", (total, fee) => {
  const form = renderForm();

  fireEvent.change(form.total, { target: { value: total } });

  expect(form.fee.value).toBe(fee);
});

test("after the user edits fee to 0, changing total no longer changes fee", () => {
  const form = renderForm();

  fireEvent.change(form.total, { target: { value: "1000" } });
  fireEvent.change(form.total, { target: { value: "2000" } });
  expect(form.fee.value).toBe("2.00");

  for (const fee of ["0", ""]) {
    fireEvent.change(form.fee, { target: { value: fee } });
    for (const total of ["3000", ""]) {
      fireEvent.change(form.total, { target: { value: total } });
      expect(form.fee.value).toBe(fee);
    }
  }
});

test.each([
  [new Date(2026, 2, 5, 0, 30), "2026-03-05"],
  [new Date(2026, 2, 5, 23, 30), "2026-03-05"],
  [new Date(2027, 0, 1, 0, 5), "2027-01-01"],
])("trade date defaults to today's local date (%s)", (now, expected) => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(now);

  expect(renderForm().date.value).toBe(expected);
});

test("the portfolio and buy ids are passed through encodeURIComponent in the save path", async () => {
  const fetchMock = vi.fn<typeof fetch>(async () => new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetchMock);
  const buy = { id: "2/x" as unknown as number, asset_id: "bitcoin", asset_name: "Bitcoin", asset_symbol: "btc" };
  const amounts = { quantity: "1", total_usd: "10", fee_usd: "0", trade_date: "2026-01-02", comment: null };
  render(<BuyForm portfolioId="1/.." buy={{ ...buy, ...amounts }} onSaved={() => {}} />);

  fireEvent.click(screen.getByRole("button", { name: "Save buy" }));

  await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/v1\/portfolios\/1%2F\.\.\/buys\/2%2Fx$/);
});
