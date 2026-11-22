import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { MultiSelect } from "./components/MultiSelect";

function Harness({ initial = [] as string[] }) {
  const [value, setValue] = useState(initial);
  return <MultiSelect label="Categories in" options={["Bills", "Dining", "Rent"]} value={value} onChange={setValue} />;
}

describe("MultiSelect", () => {
  it("says 'Choose options' when empty", () => {
    render(<Harness />);
    expect(within(screen.getByRole("combobox", { name: "Categories in" })).getByText("Choose options")).toBeInTheDocument();
  });

  it("opens a list of the options not yet chosen, and picks one into a tag", async () => {
    render(<Harness initial={["Bills"]} />);
    await userEvent.click(screen.getByRole("combobox", { name: "Categories in" }));
    const list = screen.getByRole("listbox", { name: "Categories in" });
    expect(within(list).queryByRole("option", { name: "Bills" })).toBeNull();
    await userEvent.click(within(list).getByRole("option", { name: "Rent" }));
    const box = screen.getByRole("combobox", { name: "Categories in" });
    expect(within(box).getByText("Bills")).toBeInTheDocument();
    expect(within(box).getByText("Rent")).toBeInTheDocument();
  });

  it("filters the list as you type", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("combobox", { name: "Categories in" }));
    await userEvent.type(screen.getByLabelText("Filter Categories in"), "di");
    const options = screen.getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Dining"]);
    await userEvent.clear(screen.getByLabelText("Filter Categories in"));
    await userEvent.type(screen.getByLabelText("Filter Categories in"), "zzz");
    expect(screen.getByText("No results")).toBeInTheDocument();
  });

  it("removes a tag with its ×, and clears everything with ⊗", async () => {
    render(<Harness initial={["Bills", "Rent"]} />);
    await userEvent.click(screen.getByRole("button", { name: "Remove Bills" }));
    const box = screen.getByRole("combobox", { name: "Categories in" });
    expect(within(box).queryByText("Bills")).toBeNull();
    expect(within(box).getByText("Rent")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear Categories in" }));
    expect(within(box).getByText("Choose options")).toBeInTheDocument();
  });

  it("closes on Escape and on a click outside", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("combobox", { name: "Categories in" }));
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).toBeNull();
    await userEvent.click(screen.getByRole("combobox", { name: "Categories in" }));
    await userEvent.click(document.body);
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("opens from the keyboard", async () => {
    render(<Harness />);
    screen.getByRole("combobox", { name: "Categories in" }).focus();
    await userEvent.keyboard("{Enter}");
    expect(screen.getByRole("listbox")).toBeInTheDocument();
  });
});
