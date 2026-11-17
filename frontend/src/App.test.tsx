import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";

const auth = vi.hoisted(() => ({ isLoaded: true, isSignedIn: false }));

vi.mock("@clerk/react", () => ({
  useAuth: () => auth,
  SignIn: () => <div data-testid="clerk-sign-in" />,
  UserButton: () => <button type="button" data-testid="clerk-user-button" />,
}));

vi.mock("./pages/PortfoliosPage", () => ({
  default: () => <h1>Portfolios</h1>,
}));

vi.mock("./pages/PortfolioDetailPage", () => ({
  default: () => <h1>Portfolio detail</h1>,
}));

afterEach(cleanup);

function renderApp(signedIn: boolean, path = "/") {
  auth.isSignedIn = signedIn;
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

test("the / route renders the Findipend heading", () => {
  renderApp(true);

  const heading = screen.getByRole("heading", { level: 1 });
  expect(heading.textContent).toBe("Findipend");
});

test("a signed-out visitor sees Clerk's sign-in and not the home heading", () => {
  renderApp(false);

  expect(screen.getByTestId("clerk-sign-in")).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "Findipend" })).toBeNull();
  expect(screen.queryByTestId("clerk-user-button")).toBeNull();
});

test("a signed-in user sees the home heading and a user button", () => {
  renderApp(true);

  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Findipend");
  expect(screen.getByTestId("clerk-user-button")).toBeTruthy();
  expect(screen.queryByTestId("clerk-sign-in")).toBeNull();
});

test("the /portfolios route renders the portfolios page", () => {
  renderApp(true, "/portfolios");

  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Portfolios");
});

test("the /portfolios/:id route renders the portfolio detail page", () => {
  renderApp(true, "/portfolios/7");

  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Portfolio detail");
});
