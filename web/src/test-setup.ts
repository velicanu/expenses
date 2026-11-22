import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom has no canvas or WebGL: every test gets a Plotly that only records what it was asked to draw.
vi.mock("plotly.js-basic-dist-min", () => ({ default: { react: vi.fn(() => Promise.resolve()), purge: vi.fn() } }));

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
});
