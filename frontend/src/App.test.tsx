import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, test } from "vitest";
import App from "./App";

test("the / route renders the Findipend heading", () => {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <App />
    </MemoryRouter>,
  );

  const heading = screen.getByRole("heading", { level: 1 });
  expect(heading.textContent).toBe("Findipend");
});
