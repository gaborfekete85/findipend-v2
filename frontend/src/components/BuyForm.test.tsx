import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import BuyForm from "./BuyForm";

vi.mock("@clerk/react", () => ({ useAuth: () => ({ getToken: async () => "mock-token" }) }));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
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
