import { render, screen } from "@testing-library/react";
import { App } from "./App";
import { NAV } from "./nav";

test("renders all nine V12 sidebar entries in order", () => {
  globalThis.fetch = vi.fn(() => Promise.reject(new Error("offline"))) as unknown as typeof fetch;
  render(<App />);
  const labels = screen.getAllByRole("button").map((b) => b.textContent);
  expect(labels).toEqual(NAV.map((n) => n.label));
});
