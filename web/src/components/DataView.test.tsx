import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { jsonResponse, mockApi, renderWithClient } from "../test-utils";
import type { Meta } from "../types";
import { DataView } from "./DataView";

const meta: Meta = { min_date: null, max_date: null, count: 0, categories: [], sources: [], colors: {}, plaid_configured: true };
afterEach(() => vi.unstubAllGlobals());

describe("DataView", () => {
  it("uploads the chosen CSVs as `files` and reports saved and rejected ones", async () => {
    const calls = mockApi({
      "GET /api/files": [],
      "GET /api/accounts": [],
      "GET /api/meta": meta,
      "POST /api/files": {
        saved: ["chase.csv: chase"],
        failed: ["notes.csv"],
        pipeline: { ran: true, seconds: 0.4, count: 9 },
      },
    });
    renderWithClient(<DataView meta={meta} />);
    await userEvent.upload(screen.getByLabelText("Choose CSV files"), [
      new File(["a,b"], "chase.csv", { type: "text/csv" }),
      new File(["c,d"], "notes.csv", { type: "text/csv" }),
    ]);
    await screen.findByText("chase.csv: chase");
    expect(screen.getByText("notes.csv")).toBeInTheDocument();
    expect(screen.getByText("Pipeline ran: 9 transactions in 0.4s.")).toBeInTheDocument();

    const post = calls.find((c) => c.method === "POST")!;
    expect((post.body as FormData).getAll("files").map((f) => (f as File).name)).toEqual(["chase.csv", "notes.csv"]);
  });

  it("deletes a file only after confirming, then asks for a pipeline re-run", async () => {
    let files = [{ name: "old.csv", size: 2048, modified: 1700000000 }];
    const calls = mockApi({
      "GET /api/files": () => jsonResponse(files),
      "GET /api/accounts": [],
      "GET /api/meta": meta,
      "DELETE /api/files/old.csv": () => {
        files = [];
        return new Response(null, { status: 204 });
      },
    });
    renderWithClient(<DataView meta={meta} />);
    await screen.findByText("2.0 KB");
    await userEvent.click(screen.getByRole("button", { name: "Delete old.csv" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await screen.findByText(/Run the pipeline to rebuild/);
    expect(await screen.findByText("No files yet.")).toBeInTheDocument();
  });

  it("only offers the Plaid refresh when the server has the keys, and shows per-account results", async () => {
    mockApi({
      "GET /api/files": [],
      "GET /api/accounts": [{ alias: "card", institution: "Bank", start_date: "2024-05-02" }],
      "POST /api/accounts/pull": {
        accounts: [{ alias: "card", pulled: 12 }, { alias: "broken", error: "ITEM_LOGIN_REQUIRED: log in again" }],
        pipeline: { ran: true, seconds: 1, count: 20 },
      },
    });
    const { unmount } = renderWithClient(<DataView meta={{ ...meta, plaid_configured: false }} />);
    await screen.findByText("card");
    expect(screen.queryByRole("button", { name: /Refresh from Plaid/ })).not.toBeInTheDocument();
    unmount();

    renderWithClient(<DataView meta={meta} />);
    await userEvent.click(await screen.findByRole("button", { name: "Refresh from Plaid" }));
    await screen.findByText("card: 12 transactions pulled");
    expect(screen.getByText("broken: ITEM_LOGIN_REQUIRED: log in again")).toHaveClass("error");
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh from Plaid" })).toBeEnabled());
  });
});
