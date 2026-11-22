import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderWithClient } from "../test-utils";
import type { Meta, Rules } from "../types";
import { RulesView } from "./RulesView";

const meta: Meta = {
  min_date: null,
  max_date: null,
  count: 9,
  categories: ["Dining", "Shopping"],
  sources: [],
  colors: {},
  plaid_configured: false,
};
const empty: Rules = { description: {}, category: {}, new_categories: {} };
afterEach(() => vi.unstubAllGlobals());

describe("RulesView", () => {
  it("saves the edited rules, then applies them, in that order", async () => {
    const calls = mockApi({
      "GET /api/rules": empty,
      "PUT /api/rules": ({ body }: { body: unknown }) => new Response(JSON.stringify(body), { status: 200 }),
      "POST /api/pipeline/run": { ran: true, seconds: 0.3, count: 9 },
      "GET /api/meta": meta,
      "GET /api/files": [],
      "GET /api/accounts": [],
    });
    renderWithClient(<RulesView meta={meta} />);

    const form = await screen.findByRole("form", { name: "Add description rule" });
    await userEvent.type(form.querySelector("input")!, "rei");
    await userEvent.selectOptions(form.querySelector("select")!, "Shopping");
    await userEvent.click(screen.getByRole("button", { name: "Add description rule" }));
    expect(screen.getByText("“rei”")).toBeInTheDocument();
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();

    const category = screen.getByRole("form", { name: "Add category" });
    await userEvent.type(category.querySelector("input")!, "side hustle");
    await userEvent.click(screen.getByRole("button", { name: "Add category" }));
    expect(screen.getByRole("button", { name: "Delete category Side Hustle" })).toBeInTheDocument();
    expect(screen.getAllByRole("option", { name: "Side Hustle" }).length).toBeGreaterThan(0); // usable as a rule target at once

    await userEvent.click(screen.getByRole("button", { name: "Save and apply" }));
    await screen.findByText(/Saved and applied: 9 transactions in 0.3s/);

    const writes = calls.filter((c) => c.method !== "GET");
    expect(writes.map((c) => `${c.method} ${c.url}`)).toEqual(["PUT /api/rules", "POST /api/pipeline/run"]);
    expect(writes[0].body).toEqual({ description: { rei: "Shopping" }, category: {}, new_categories: { "Side Hustle": "#4e79a7" } });
    expect(writes[1].body).toEqual({ rules_only: true });
  });

  it("Save alone does not run the pipeline, and a rule can be deleted", async () => {
    const calls = mockApi({
      "GET /api/rules": { ...empty, category: { food: "Dining" } },
      "PUT /api/rules": ({ body }: { body: unknown }) => new Response(JSON.stringify(body), { status: 200 }),
      "GET /api/meta": meta,
      "GET /api/files": [],
      "GET /api/accounts": [],
    });
    renderWithClient(<RulesView meta={meta} />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete category rule food" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(calls.find((c) => c.method === "PUT")!.body).toEqual(empty);
    expect(calls.some((c) => c.url === "/api/pipeline/run")).toBe(false);
    await screen.findByText(/Saved\. Use/);
  });
});
