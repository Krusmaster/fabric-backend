// @vitest-environment jsdom
// W3 (Gustav's run of 23 November 2026 in a real tenant): the catalog step's layout and its finish.
// - Before: "Prepare again" at the top, and "I checked the changes above" with "Write N changes as me" far below the
//   handover files, the button grey until the box was ticked. Now the box and Write sit right under Prepare again, after a
//   short summary and a link "See the N changes" to the list (which stays where it was); while Write cannot be used the
//   words beside it say exactly what is missing.
// - After a write: Onto's cheer once (or the same words plain with the mascots off), the receipt compactly, and a button to
//   the workspace with "find it in OneLake catalog" (no documented address opens the catalog at an item).
// - The Krusgraph Model item's own description is one of the changes, named as this item.
import React from "react";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CatalogContext, CatalogPanel, CatalogView } from "./CatalogPanel";
import {
  CatalogAnswer, DIFF_ID, WRITING_OFF, canWrite, catalogPlace, gateSummary, partialLine, receiptLines, seeChangesLabel,
} from "./catalogWords";
import { CheerBook, catalogCheer } from "./cheer";
import { CheerContext, CheerSource } from "./cheerView";
import { FABRIC_PORTAL } from "./openInFabric";

const WS = "11111111-2222-4333-8444-555555555555";
const MODEL_TEXT = "Krusgraph data product customers over demo_lh: 4 of 4 keys unique, 3 of 3 links holding, checked 23 Nov 2026. Built: silver_shop.";
const ANSWER: CatalogAnswer = {
  summary: "1 data product card(s); as you: 3 description(s) and tags on 1 item(s) to write",
  products: [],
  diff: [
    { item: "shop_product", type: "Org.Krusgraph.Model", field: "description", before: "", after: MODEL_TEXT, action: "write", model_item: true },
    { item: "shop_model", type: "SemanticModel", field: "description", before: "old", after: "Krusgraph semantic model shop_model.", action: "write" },
    { item: "silver_shop", type: "Notebook", field: "description", before: "", after: "Krusgraph notebook silver_shop.", action: "write" },
    { item: "shop_model", type: "SemanticModel", field: "tags", before: [], after: ["Krusgraph"], action: "write" },
  ],
  confirm: "catalog-abc",
  writable: true,
  workspace: WS,
  handover: { requests: [], approvals: [], files: { "handover/endorsement.md": "# Endorsement" } },
  note: "Nothing was created or changed in Fabric.",
};
const OK = [
  { item: "shop_product", field: "description", ok: true, status: 200 },
  { item: "shop_model", field: "description", ok: true, status: 200 },
  { item: "silver_shop", field: "description", ok: true, status: 200 },
  { item: "shop_model", field: "tags", ok: true, status: 200 },
];

describe("the words", () => {
  it("say exactly what is missing while Write cannot be used", () => {
    expect(canWrite(ANSWER, false).why).toBe("Tick that you checked the changes.");
    expect(canWrite({ ...ANSWER, writable: false }, true).why).toBe(WRITING_OFF);
    expect(WRITING_OFF).toBe("Writing is off in this workspace while Krusgraph is in test; use the handover files.");
    expect(canWrite(ANSWER, true)).toEqual({ ok: true, why: "" });
  });

  it("summarise the writes in one short line and link to the list", () => {
    expect(seeChangesLabel(ANSWER)).toBe("See the 4 changes");
    expect(gateSummary(ANSWER)).toBe("As you: 3 descriptions and tags on 1 item, this Krusgraph Model item's own description included, "
      + "each shown below with what is there now and what would be there.");
    expect(gateSummary({ ...ANSWER, diff: [] })).toBe("");                   // the words beside Write say it, once
  });

  it("cheer only when every change went through, with the number of descriptions", () => {
    expect(catalogCheer(OK)).toBe("Done! 3 descriptions are in the OneLake catalog. People can now find this data product, "
      + "with the row-check evidence next to it.");
    expect(catalogCheer([{ ...OK[0], ok: false }, ...OK.slice(1)])).toBeUndefined();
    expect(catalogCheer([])).toBeUndefined();
    expect(receiptLines(OK)).toEqual(["Written: shop_product (description), shop_model (description), silver_shop (description), shop_model (tags)."]);
    expect(receiptLines([{ item: "x", field: "tags", ok: false, hint: "Fabric refused" }])).toEqual(["Not written: x (tags: Fabric refused)."]);
    expect(partialLine([{ item: "x", field: "tags", ok: false }, OK[0]])).toMatch(/^1 of 2 changes written\./);
  });

  it("open the workspace's list, the documented address, and say to find it in OneLake catalog", () => {
    const place = catalogPlace(WS, FABRIC_PORTAL)!;
    expect(place.url).toBe(`https://app.fabric.microsoft.com/groups/${WS}/list`);
    expect(place.line).toMatch(/^Find it in OneLake catalog/);
    expect(catalogPlace(undefined, FABRIC_PORTAL)).toBeUndefined();
    expect(catalogPlace("not a workspace", FABRIC_PORTAL)).toBeUndefined();
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

const buttons = () => Array.from(host.querySelectorAll("button"));
const view = (a: CatalogAnswer, extra: Partial<React.ComponentProps<typeof CatalogView>> = {}) => (
  <CatalogView answer={a} busy={false} owner="" checked={false} onOwner={() => {}} onPrepare={() => {}} onChecked={() => {}}
    onWrite={() => {}} {...extra} />);

describe("the layout", () => {
  it("puts the summary, the link, the box and Write right under Prepare again, before the cards, the list and the files", () => {
    act(() => root.render(view(ANSWER)));
    const order = (el: Element | null | undefined) => Array.from(host.querySelectorAll("*")).indexOf(el as Element);
    const prepare = buttons().find((b) => b.textContent === "Prepare again")!;
    const gate = host.querySelector("[data-w3=write-gate]")!;
    const write = buttons().find((b) => b.textContent === "Write 4 changes as me")!;
    expect(write.className).toContain("fui-Button");
    expect(gate.contains(write) && gate.contains(host.querySelector("input[type=checkbox]"))).toBe(true);
    const link = gate.querySelector("a.kg-catalog-see") as HTMLAnchorElement;
    expect(link.textContent).toBe("See the 4 changes");
    expect(link.getAttribute("href")).toBe(`#${DIFF_ID}`);
    const summary = gate.querySelector("p")!;
    const box = gate.querySelector("input[type=checkbox]")!;
    expect(order(prepare) < order(summary) && order(summary) < order(link) && order(link) < order(box) && order(box) < order(write)).toBe(true);
    const list = host.querySelector(`#${DIFF_ID}`)!;
    expect(list.textContent).toBe("What would be written as you (4)");
    expect(order(write) < order(list) && order(list) < order(host.querySelector(".kg-catalog-files"))).toBe(true);
    expect(write.hasAttribute("disabled")).toBe(true);
    expect(host.querySelector("#kg-catalog-why")!.textContent).toBe("Tick that you checked the changes.");
    expect(host.textContent).toContain("This Krusgraph Model item");       // the Model item's own row says what it is
    expect(host.textContent).toContain(MODEL_TEXT);
  });

  it("scrolls to the list when the link is chosen", () => {
    const scroll = vi.fn();
    act(() => root.render(view(ANSWER)));
    (document.getElementById(DIFF_ID) as HTMLElement).scrollIntoView = scroll;
    act(() => (host.querySelector("a.kg-catalog-see") as HTMLAnchorElement).click());
    expect(scroll).toHaveBeenCalledTimes(1);
  });

  it("with the box ticked Write is on; with writing off there is no box and the reason is beside the button", () => {
    act(() => root.render(view(ANSWER, { checked: true })));
    expect(buttons().find((b) => b.textContent?.startsWith("Write"))!.hasAttribute("disabled")).toBe(false);
    expect(host.querySelector("#kg-catalog-why")).toBeNull();
    act(() => root.render(view({ ...ANSWER, writable: false }, { checked: true })));
    expect(host.querySelector("[data-w3=write-gate] input[type=checkbox]")).toBeNull();
    expect(host.querySelector("#kg-catalog-why")!.textContent).toBe(WRITING_OFF);
  });
});

describe("after the write", () => {
  const source = (on: boolean, book = new CheerBook(), record?: (m: string) => void): CheerSource => ({ on, create: "c1", book, record });

  it("Onto cheers in place of the bare list, the receipt under it, and the button to the workspace", () => {
    const record = vi.fn();
    act(() => root.render(
      <CheerContext.Provider value={source(true, new CheerBook(), record)}>{view({ ...ANSWER, results: OK }, { written: true })}</CheerContext.Provider>));
    const done = host.querySelector("[data-w3=written]")!;
    expect(done.querySelector("[data-w3-cheer=catalog_written] [data-pose=celebrate]")).not.toBeNull();
    expect(done.textContent).toContain("Done! 3 descriptions are in the OneLake catalog.");
    expect(done.textContent).toContain("Written: shop_product (description)");
    expect(done.textContent).not.toContain("description: written");
    const open = done.querySelector("a[data-w3=open-catalog]") as HTMLAnchorElement;
    expect(open.getAttribute("href")).toBe(`https://app.fabric.microsoft.com/groups/${WS}/list`);
    expect(open.textContent).toContain("Open the workspace");
    expect(done.textContent).toContain("Find it in OneLake catalog");
    expect(buttons().some((b) => b.textContent?.startsWith("Write"))).toBe(false);
    expect(record).toHaveBeenCalledWith("catalog_written");
  });

  it("with the mascots off, or cheered already in this Create, the same words plain and no figure", () => {
    act(() => root.render(
      <CheerContext.Provider value={source(false)}>{view({ ...ANSWER, results: OK }, { written: true })}</CheerContext.Provider>));
    expect(host.querySelector("[data-w3-cheer]")).toBeNull();
    expect(host.querySelector(".krusgraph-fig")).toBeNull();
    expect(host.textContent).toContain("Done! 3 descriptions are in the OneLake catalog.");
    act(() => root.render(
      <CheerContext.Provider value={{ ...source(true), before: { create: "c1", said: ["catalog_written"] } }}>
        {view({ ...ANSWER, results: OK }, { written: true })}</CheerContext.Provider>));
    expect(host.querySelector("[data-w3-cheer]")).toBeNull();
    expect(host.textContent).toContain("Done! 3 descriptions are in the OneLake catalog.");
  });

  it("a write where something failed says how many went through, without a cheer or the button", () => {
    act(() => root.render(view({ ...ANSWER, results: [{ ...OK[0], ok: false, hint: "Fabric refused" }, ...OK.slice(1)] }, { written: true })));
    expect(host.querySelector("[data-w3-cheer]")).toBeNull();
    expect(host.textContent).toContain("3 of 4 changes written.");
    expect(host.textContent).toContain("Not written: shop_product (description: Fabric refused).");
    expect(host.querySelector("a[data-w3=open-catalog]")).toBeNull();
  });

  it("the panel sends the dry run's confirm, then shows the cheer", async () => {
    const run = vi.fn(async ({ dryRun }: { dryRun: boolean }) => (dryRun ? ANSWER : { ...ANSWER, results: OK }));
    act(() => root.render(<CatalogContext.Provider value={{ run }}><CatalogPanel /></CatalogContext.Provider>));
    await act(async () => buttons().find((b) => b.textContent?.startsWith("Prepare"))!.click());
    await act(async () => (host.querySelector("input[type=checkbox]") as HTMLInputElement).click());
    await act(async () => buttons().find((b) => b.textContent?.startsWith("Write"))!.click());
    expect(run).toHaveBeenLastCalledWith({ dryRun: false, confirm: "catalog-abc", owner: null, include: [] });
    expect(host.textContent).toContain("Done! 3 descriptions are in the OneLake catalog.");
  });
});
