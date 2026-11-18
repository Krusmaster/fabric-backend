// @vitest-environment jsdom
// CA1: "Publish to OneLake catalog" on the Data product page. Prepare is a dry run that shows every change as its own
// block (item, field, now, after); the write is offered only after a dry run with something to write, in a workspace the
// engine says is writable, once the person ticked that they checked; the others' steps are grouped by who must act, and
// endorsement is said to stay a person's decision.
import React from "react";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CatalogContext, CatalogPanel, CatalogView } from "./CatalogPanel";
import { CatalogAnswer, ENDORSE_LINE, approvals, canWrite, diffLine, fileHref, shown, writeCount } from "./catalogWords";

const ANSWER: CatalogAnswer = {
  summary: "2 data product card(s); as you: 1 description(s) and tags on 1 item(s) to write",
  products: [{
    name: "customers", slug: "customers", tables: ["customers", "orders"],
    description: "Data product customers (shop): Customers, Orders. Checked by Krusgraph: 2 of 2 keys unique, 0 orphan rows over 1 link, checked 17 Nov 2026.",
    owner: "not chosen yet", domain: { proposed: "customers", why: "x", note: "a proposal" }, tags: ["Krusgraph", "customers"],
    contract: { format: "ODCS v3.2.0", status: "draft", file: "contracts/customers.odcs.yaml" },
    glossary: [{ term: "Orders", definition: "One row of shop.orders; identified by order_id (rule K2)." }],
    evidence: { counted: true, line: "2 of 2 keys unique, 0 orphan rows over 1 link, checked 17 Nov 2026" },
    quality_rules: [{ id: "orders_key_unique", kind: "unique_key", says: "orders.order_id has no duplicates", status: "proven", sql: "SELECT 0" }],
  }],
  diff: [
    { item: "shop_model", field: "description", before: "old", after: "Data product customers", action: "write" },
    { item: "demo_lh", field: "tags", before: [], after: ["Krusgraph"], action: "write" },
    { item: "demo_lh", field: "description", before: null, after: "Data product customers", action: "kept", why: "the item has its own description" },
  ],
  confirm: "catalog-abc",
  writable: true,
  handover: {
    requests: [
      { step: "Endorse customers", by: "reviewer", method: null, url: null },
      { step: "Create the tags", by: "fabric_admin", method: "POST", url: "https://api.fabric.microsoft.com/v1/admin/tags/bulkCreateTags" },
      { step: "Assign the workspace to the domain", by: "workspace_admin", method: "POST", url: "x" },
    ],
    approvals: [],
    files: { "handover/fabric-admin.md": "# For the admin", "handover/purview.json": "{}" },
  },
  note: "Nothing was created or changed in Fabric.",
};

describe("catalogWords", () => {
  it("counts the writes and says each change in one line", () => {
    expect(writeCount(ANSWER)).toBe(2);
    expect(diffLine(ANSWER.diff[0])).toBe("shop_model: description will change from old to Data product customers");
    expect(diffLine(ANSWER.diff[2])).toContain("kept as it is");
    expect(shown([])).toBe("(no tags)");
    expect(shown(null)).toBe("—");
  });

  it("offers the write only after a dry run, with something to write, where writing is on, once checked", () => {
    expect(canWrite(undefined, true).ok).toBe(false);
    expect(canWrite({ ...ANSWER, writable: false }, true).why).toContain("operator lists");
    expect(canWrite({ ...ANSWER, confirm: null }, true).ok).toBe(false);
    expect(canWrite(ANSWER, false).why).toContain("Tick");
    expect(canWrite(ANSWER, true).ok).toBe(true);
  });

  it("groups the others' steps by who must act, endorsement last", () => {
    expect(approvals(ANSWER).map((g) => g.who)).toEqual(["Fabric administrator", "Workspace admin", "A reviewer (a person)"]);
  });

  it("downloads files as data links", () => {
    expect(fileHref("{}", "handover/purview.json")).toMatch(/^data:application\/json/);
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

describe("CatalogView", () => {
  it("shows each change as now and after, the files, and that endorsement is a person's", () => {
    act(() => root.render(<CatalogView answer={ANSWER} busy={false} owner="" checked={false} onOwner={() => {}}
      onPrepare={() => {}} onChecked={() => {}} onWrite={() => {}} />));
    const changes = host.querySelectorAll(".kg-catalog-change");
    expect(changes.length).toBe(3);
    expect(changes[0].getAttribute("aria-label")).toContain("will change from old");
    expect(host.querySelectorAll(".kg-catalog-before-after").length).toBe(2);
    expect(host.textContent).toContain(ENDORSE_LINE);
    expect(host.querySelectorAll("button[aria-label^='Download handover/']").length).toBe(2);   // WB10: fileOffer.tsx
    expect(host.querySelector("table")).toBeNull();                       // nothing to scroll sideways on a phone
    const write = Array.from(host.querySelectorAll("button")).find((b) => b.textContent?.startsWith("Write"));
    expect(write?.hasAttribute("disabled")).toBe(true);                   // not ticked yet
  });

  it("is not shown where nothing provides the call", () => {
    act(() => root.render(<CatalogPanel />));
    expect(host.textContent).toBe("");
  });

  it("prepares as a dry run first, then writes with the dry run's confirm", async () => {
    const run = vi.fn(async ({ dryRun }: { dryRun: boolean }) =>
      dryRun ? ANSWER : { ...ANSWER, results: [{ item: "shop_model", field: "description", ok: true, status: 200 }] });
    act(() => root.render(<CatalogContext.Provider value={{ run }}><CatalogPanel /></CatalogContext.Provider>));
    const prepare = Array.from(host.querySelectorAll("button")).find((b) => b.textContent?.startsWith("Prepare"))!;
    await act(async () => { prepare.click(); });
    expect(run).toHaveBeenCalledWith({ dryRun: true, confirm: null, owner: null });
    const box = host.querySelector("input[type=checkbox]") as HTMLInputElement;
    await act(async () => { box.click(); });
    const write = Array.from(host.querySelectorAll("button")).find((b) => b.textContent?.startsWith("Write"))!;
    expect(write.hasAttribute("disabled")).toBe(false);
    await act(async () => { write.click(); });
    expect(run).toHaveBeenLastCalledWith({ dryRun: false, confirm: "catalog-abc", owner: null });
    expect(host.textContent).toContain("shop_model, description: written");
  });
});
