import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import BuyForm from "./BuyForm";

const auth = vi.hoisted(() => ({ getToken: async () => "mock-token" }));
vi.mock("@clerk/react", () => ({ useAuth: () => auth }));

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

function renderForm() {
  render(<BuyForm portfolioId={1} onSaved={() => {}} />);
  return {
    total: screen.getByLabelText("Total (USD)") as HTMLInputElement,
    fee: screen.getByLabelText("Fee (USD)") as HTMLInputElement,
    date: screen.getByLabelText("Trade date") as HTMLInputElement,
  };
}

test.each([
  ["1000", "1.00"],
  ["2500.50", "2.50"],
  ["123.45", "0.12"],
  ["5", "0.01"],
  ["4", "0.00"],
  ["0", "0.00"],
  ["", ""],
])("typing total %j pre-fills fee %j (0.1 percent, rounded to cents)", (total, fee) => {
  const form = renderForm();

  fireEvent.change(form.total, { target: { value: total } });

  expect(form.fee.value).toBe(fee);
});

test("after the user edits fee to 0, changing total no longer changes fee", () => {
  const form = renderForm();

  fireEvent.change(form.total, { target: { value: "1000" } });
  expect(form.fee.value).toBe("1.00");
  fireEvent.change(form.total, { target: { value: "2000" } });
  expect(form.fee.value).toBe("2.00");

  fireEvent.change(form.fee, { target: { value: "0" } });
  fireEvent.change(form.total, { target: { value: "3000" } });
  expect(form.fee.value).toBe("0");
  fireEvent.change(form.total, { target: { value: "" } });
  expect(form.fee.value).toBe("0");
});

test.each([
  [new Date(2026, 2, 5, 0, 30), "2026-03-05"],
  [new Date(2026, 2, 5, 23, 30), "2026-03-05"],
  [new Date(2026, 11, 31, 12, 0), "2026-12-31"],
  [new Date(2027, 0, 1, 0, 5), "2027-01-01"],
])("trade date defaults to today's local date (%s)", (now, expected) => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(now);

  const form = renderForm();

  expect(form.date.value).toBe(expected);
});
