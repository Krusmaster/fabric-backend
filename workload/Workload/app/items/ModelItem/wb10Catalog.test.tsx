// @vitest-environment jsdom
// WB10 (Gustav's live test in Fabric, 18 Nov 2026): the catalog step's owner is a person or group (#58), never an
// item's name and never filled by the browser; an item Krusgraph did not build is offered unticked and written only when
// ticked (#61); and the Thinker line states the check's time as the catalog cards do (#60).
import React from "react";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CatalogContext, CatalogPanel } from "./CatalogPanel";
import { CatalogAnswer, diffLine, optionalRows, ownerProblem } from "./catalogWords";
import { proofLine, proofOf } from "./nextSteps";

const PEOPLE = [
  { name: "Eva Berg", type: "User" as const, role: "Admin", upn: "eva@contoso.example" },
  { name: "Data team", type: "Group" as const, role: "Member" },
];
const ITEMS = ["demo_lh_api9", "shop_lh_silver"];

const ANSWER: CatalogAnswer = {
  summary: "2 data product card(s)",
  products: [],
  diff: [
    { item: "shop_lh_silver", field: "description", before: "Silver tables for shop_lh.shop.", after: "Silver tables for shop_lh.shop. Data products customers and products over shop_lh, checked by Krusgraph: 6 of 6 keys unique.", action: "write" },
    { item: "shop_lh", item_id: "aaaaaaaa-0000-0000-0000-000000000001", field: "description and tags", before: "", after: "Data products customers and products over shop_lh.", action: "optional",
      why: "Krusgraph did not build shop_lh: its description and tags are its owner's, so nothing is written to it unless you tick it" },
  ],
  confirm: "catalog-abc",
  writable: true,
  handover: { requests: [], approvals: [], files: {} },
  note: "Nothing was created or changed in Fabric.",
};

describe("ownerProblem (#58)", () => {
  it("refuses an item's name, even when the workspace's people are unknown", () => {
    expect(ownerProblem("demo_lh_api9", PEOPLE, "Eva Berg", ITEMS)).toContain("is an item in this workspace, not a person or group");
    expect(ownerProblem("demo_lh_api9", null, null, ITEMS)).toContain("is an item");
  });
  it("accepts a person, a group, their e-mail, the picker's value and Me; refuses a stranger where people are known", () => {
    for (const ok of ["Eva Berg", "eva@contoso.example", "Eva Berg (eva@contoso.example)", "data team", "Me Myself", ""]) {
      expect(ownerProblem(ok, PEOPLE, "Me Myself", ITEMS)).toBe("");
    }
    expect(ownerProblem("Somebody", PEOPLE, "Me Myself", ITEMS)).toContain("not a person or group");
    expect(ownerProblem("Somebody", null, null, ITEMS)).toBe("");
  });
});

describe("optional rows (#61)", () => {
  it("say that nothing is written unless ticked", () => {
    expect(optionalRows(ANSWER).map((r) => r.item)).toEqual(["shop_lh"]);
    expect(diffLine(ANSWER.diff[1])).toContain("not written unless you tick it");
  });
});

describe("the Thinker line's time (#60)", () => {
  it("is the latest recorded check, written as the catalog cards write it", () => {
    const at = (t: string) => ({ status: "passed" as const, checked_at: t, result: { rows: 4, nulls: 0, distinct: 4 } });
    const review = { items: [
      { id: "k1", type: "key", table: "a", columns: ["id"], review: "accepted", check: at("2026-11-14T14:54Z") },
      { id: "k2", type: "key", table: "b", columns: ["id"], review: "accepted", check: at("2026-11-18T10:12Z") },
    ] } as never;
    expect(proofLine(proofOf(review))).toContain("(checked 2026-11-18 10:12 UTC)");
  });
});

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

describe("CatalogPanel (#58, #61)", () => {
  it("has autocomplete off, a name of its own, the people picker and Me; an item's name is not prefilled", () => {
    const run = vi.fn(async () => ANSWER);
    act(() => root.render(
      <CatalogContext.Provider value={{ run, owner: "demo_lh_api9", people: PEOPLE, you: "Eva Berg", itemNames: ITEMS }}>
        <CatalogPanel />
      </CatalogContext.Provider>));
    const input = host.querySelector("input[name=kg-catalog-owner]") as HTMLInputElement;
    expect(input.getAttribute("autocomplete")).toBe("off");
    expect(input.value).toBe("");                                      // the saved item name is not offered
    const list = host.querySelector(`datalist#${input.getAttribute("list")}`);
    expect(Array.from(list!.querySelectorAll("option")).map((o) => o.getAttribute("value"))).toEqual(["Eva Berg (eva@contoso.example)", "Data team"]);
    const me = Array.from(host.querySelectorAll("button")).find((b) => b.textContent === "Me (Eva Berg)");
    expect(me).toBeTruthy();
  });

  it("refuses an item's name typed in, and does not prepare with it", async () => {
    const run = vi.fn(async () => ANSWER);
    act(() => root.render(
      <CatalogContext.Provider value={{ run, people: PEOPLE, you: "Eva Berg", itemNames: ITEMS }}><CatalogPanel /></CatalogContext.Provider>));
    const input = host.querySelector("input[name=kg-catalog-owner]") as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    await act(async () => { setter.call(input, "demo_lh_api9"); input.dispatchEvent(new Event("input", { bubbles: true })); });
    expect(host.textContent).toContain("is an item in this workspace, not a person or group");
    const prepare = Array.from(host.querySelectorAll("button")).find((b) => b.textContent?.startsWith("Prepare"))!;
    expect(prepare.hasAttribute("disabled")).toBe(true);
    expect(run).not.toHaveBeenCalled();
  });

  it("offers an item Krusgraph did not build unticked, and prepares again with it when ticked", async () => {
    const run = vi.fn(async () => ANSWER);
    act(() => root.render(<CatalogContext.Provider value={{ run }}><CatalogPanel /></CatalogContext.Provider>));
    const prepare = Array.from(host.querySelectorAll("button")).find((b) => b.textContent?.startsWith("Prepare"))!;
    await act(async () => { prepare.click(); });
    const row = host.querySelector("[data-action=optional]")!;
    expect(row.textContent).toContain("Krusgraph did not build shop_lh");
    const box = row.querySelector("input[type=checkbox]") as HTMLInputElement;
    expect(box.checked).toBe(false);
    await act(async () => { box.click(); });
    expect(run).toHaveBeenLastCalledWith({ dryRun: true, confirm: null, owner: null, include: ["aaaaaaaa-0000-0000-0000-000000000001"] });
  });
});
