import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import PortfoliosPage from "./PortfoliosPage";

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

function renderPage() {
  render(
    <MemoryRouter>
      <PortfoliosPage />
    </MemoryRouter>,
  );
}

function portfolio(id: number, name: string) {
  return { id, name, created_at: "2026-11-01T10:00:00Z", updated_at: "2026-11-01T10:00:00Z" };
}

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** The GET list answers with `initial`; every later call gets the next queued response. */
function mockApi(initial: unknown[], ...next: Response[]) {
  fetchMock.mockResolvedValueOnce(jsonResponse(200, initial));
  for (const response of next) fetchMock.mockResolvedValueOnce(response);
}

function call(index: number) {
  const [url, init] = fetchMock.mock.calls[index];
  return {
    url,
    method: init?.method ?? "GET",
    body: init?.body === undefined ? undefined : JSON.parse(String(init.body)),
    contentType: new Headers(init?.headers).get("Content-Type"),
    auth: new Headers(init?.headers).get("Authorization"),
  };
}

async function listedNames() {
  const list = await screen.findByRole("list", { name: "Portfolios" });
  return within(list)
    .getAllByRole("listitem")
    .map((item) => item.querySelector("[data-portfolio-name]")?.textContent);
}

test("renders the portfolios the API returns, by name", async () => {
  mockApi([portfolio(1, "Long term"), portfolio(2, "Trading")]);

  renderPage();

  expect(await listedNames()).toEqual(["Long term", "Trading"]);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(call(0)).toMatchObject({
    url: `${API}/api/v1/portfolios`,
    method: "GET",
    auth: "Bearer mock-token",
  });
});

test("each portfolio name links to its detail page", async () => {
  mockApi([portfolio(1, "Long term"), portfolio(2, "Trading")]);
  renderPage();

  const links = await screen.findAllByRole("link");
  expect(links.map((link) => [link.textContent, link.getAttribute("href")])).toEqual([
    ["Long term", "/portfolios/1"],
    ["Trading", "/portfolios/2"],
  ]);
});

test("submitting a new name posts it and the new portfolio appears in the list", async () => {
  mockApi([portfolio(1, "Long term")], jsonResponse(201, portfolio(3, "Savings")));
  renderPage();
  await screen.findByText("Long term");

  fireEvent.change(screen.getByLabelText("New portfolio name"), { target: { value: "Savings" } });
  fireEvent.click(screen.getByRole("button", { name: "Create" }));

  expect(await screen.findByText("Savings")).toBeTruthy();
  expect(await listedNames()).toEqual(["Long term", "Savings"]);
  expect(call(1)).toEqual({
    url: `${API}/api/v1/portfolios`,
    method: "POST",
    body: { name: "Savings" },
    contentType: "application/json",
    auth: "Bearer mock-token",
  });
});

test.each([
  [409, { detail: "You already have a portfolio named 'Long term'" }, "You already have a portfolio named 'Long term'"],
  [422, { detail: [{ loc: ["body", "name"], msg: "String should have at least 1 character" }] }, "name: String should have at least 1 character"],
])("a %i on create shows its message next to the form and adds nothing", async (status, body, message) => {
  mockApi([portfolio(1, "Long term")], jsonResponse(status, body));
  renderPage();
  await screen.findByText("Long term");

  fireEvent.change(screen.getByLabelText("New portfolio name"), { target: { value: "Long term" } });
  fireEvent.click(screen.getByRole("button", { name: "Create" }));

  const form = screen.getByRole("form", { name: "Create portfolio" });
  expect((await within(form).findByRole("alert")).textContent).toBe(message);
  expect(await listedNames()).toEqual(["Long term"]);
});

test("the delete confirm button stays disabled until the exact name is typed, then sends confirm_name", async () => {
  mockApi(
    [portfolio(1, "Long term"), portfolio(2, "Trading")],
    new Response(null, { status: 204 }),
  );
  renderPage();
  await screen.findByText("Trading");

  fireEvent.click(screen.getByRole("button", { name: "Delete Trading" }));
  const dialog = screen.getByRole("dialog", { name: "Delete Trading" });
  const confirm = within(dialog).getByRole("button", { name: "Delete" }) as HTMLButtonElement;
  const input = within(dialog).getByLabelText("Type Trading to confirm");

  expect(confirm.disabled).toBe(true);
  for (const wrong of ["Tradin", "trading", "Trading ", " Trading", "Long term"]) {
    fireEvent.change(input, { target: { value: wrong } });
    expect(confirm.disabled).toBe(true);
  }
  fireEvent.click(confirm);
  expect(fetchMock).toHaveBeenCalledTimes(1);

  fireEvent.change(input, { target: { value: "Trading" } });
  expect(confirm.disabled).toBe(false);
  fireEvent.click(confirm);

  await screen.findByRole("list", { name: "Portfolios" });
  await vi.waitFor(() => expect(screen.queryByText("Trading")).toBeNull());
  expect(await listedNames()).toEqual(["Long term"]);
  expect(call(1)).toEqual({
    url: `${API}/api/v1/portfolios/2`,
    method: "DELETE",
    body: { confirm_name: "Trading" },
    contentType: "application/json",
    auth: "Bearer mock-token",
  });
});

test("renaming sends a PATCH with the new name and the list shows it", async () => {
  mockApi(
    [portfolio(1, "Long term"), portfolio(2, "Trading")],
    jsonResponse(200, portfolio(1, "Retirement")),
  );
  renderPage();
  await screen.findByText("Long term");

  fireEvent.click(screen.getByRole("button", { name: "Rename Long term" }));
  fireEvent.change(screen.getByLabelText("New name for Long term"), { target: { value: "Retirement" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));

  expect(await screen.findByText("Retirement")).toBeTruthy();
  expect(await listedNames()).toEqual(["Retirement", "Trading"]);
  expect(call(1)).toEqual({
    url: `${API}/api/v1/portfolios/1`,
    method: "PATCH",
    body: { name: "Retirement" },
    contentType: "application/json",
    auth: "Bearer mock-token",
  });
});

test("renaming a portfolio while its delete dialog is open makes the dialog expect the new name", async () => {
  mockApi(
    [portfolio(1, "Long term"), portfolio(2, "Trading")],
    jsonResponse(200, portfolio(2, "Swing")),
    new Response(null, { status: 204 }),
  );
  renderPage();
  await screen.findByText("Trading");

  fireEvent.click(screen.getByRole("button", { name: "Delete Trading" }));
  fireEvent.click(screen.getByRole("button", { name: "Rename Trading" }));
  fireEvent.change(screen.getByLabelText("New name for Trading"), { target: { value: "Swing" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await listedNames()).toEqual(["Long term", "Swing"]);

  const dialog = await screen.findByRole("dialog", { name: "Delete Swing" });
  const confirm = within(dialog).getByRole("button", { name: "Delete" }) as HTMLButtonElement;
  const input = within(dialog).getByLabelText("Type Swing to confirm");

  for (const wrong of ["Trading", "", "swing", "Long term"]) {
    fireEvent.change(input, { target: { value: wrong } });
    expect(confirm.disabled).toBe(true);
  }
  fireEvent.change(input, { target: { value: "Swing" } });
  expect(confirm.disabled).toBe(false);
  fireEvent.click(confirm);

  await vi.waitFor(() => expect(screen.queryByText("Swing")).toBeNull());
  expect(await listedNames()).toEqual(["Long term"]);
  expect(call(2)).toEqual({
    url: `${API}/api/v1/portfolios/2`,
    method: "DELETE",
    body: { confirm_name: "Swing" },
    contentType: "application/json",
    auth: "Bearer mock-token",
  });
});

test("renaming a different portfolio leaves the open delete dialog's expected name alone", async () => {
  mockApi(
    [portfolio(1, "Long term"), portfolio(2, "Trading")],
    jsonResponse(200, portfolio(1, "Retirement")),
  );
  renderPage();
  await screen.findByText("Trading");

  fireEvent.click(screen.getByRole("button", { name: "Delete Trading" }));
  fireEvent.click(screen.getByRole("button", { name: "Rename Long term" }));
  fireEvent.change(screen.getByLabelText("New name for Long term"), { target: { value: "Retirement" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await listedNames()).toEqual(["Retirement", "Trading"]);

  const dialog = screen.getByRole("dialog", { name: "Delete Trading" });
  const confirm = within(dialog).getByRole("button", { name: "Delete" }) as HTMLButtonElement;
  const input = within(dialog).getByLabelText("Type Trading to confirm");
  fireEvent.change(input, { target: { value: "Retirement" } });
  expect(confirm.disabled).toBe(true);
  fireEvent.change(input, { target: { value: "Trading" } });
  expect(confirm.disabled).toBe(false);
});
