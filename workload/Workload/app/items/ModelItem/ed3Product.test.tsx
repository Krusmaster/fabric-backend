// @vitest-environment jsdom
// ED3 (Gustav's editor test of 21 November 2026, part 3): the Data product step and Publish to OneLake catalog. One
// owner, filled, set in one place; what the latest Create built is found by its plan marker and added once; a failed
// row points to Fix and finish with Fabric's message under Details; Check health now; writing off said beside the
// button with no checkbox; each handover file downloads and copies as exactly that file. Synthetic shop data only.
import React from "react";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CatalogContext, CatalogView } from "./CatalogPanel";
import { CatalogAnswer, WRITING_OFF } from "./catalogWords";
import { DataProductView } from "./DataProductView";
import { FAILED_LINE, adoptedLine, autoAdopt, ownerLine, ownerShown } from "./ed3Product";
import { LEFTOVERS, OUTPUTS, STATUS, WS } from "./productPage.fixture";
import type { ProductRow } from "./productWords";

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

const row = (over: Partial<ProductRow>): ProductRow => ({ key: "k", type: "", typeLabel: "Gold views", name: "demo_lh_gold", state: "built", ...over } as ProductRow);

describe("the owner, once", () => {
  it("is the saved one, else the signed-in person by default", () => {
    expect(ownerShown("Data team", "Anna Berg")).toEqual({ owner: "Data team", byDefault: false });
    expect(ownerShown(undefined, "Anna Berg")).toEqual({ owner: "Anna Berg", byDefault: true });
    expect(ownerLine(undefined, "Anna Berg")).toBe("Owner: Anna Berg (you, by default). Change it below.");
    expect(ownerLine("Data team", "Anna Berg")).toBeUndefined();
  });
  it("the page shows it filled, never 'Nobody is the owner yet' when someone is signed in", () => {
    const outputs = { ...OUTPUTS, product: undefined } as never;
    act(() => root.render(<DataProductView productName="shop" outputs={outputs} status={STATUS} />));
    expect(host.textContent).not.toContain("Nobody is the owner yet");
    expect((host.querySelector("#kg-dp-owner-input") as HTMLInputElement).value).toBe(STATUS.you);
  });
});

describe("found and added by the plan marker", () => {
  const unsaved = row({ key: "unsaved:semantic_model", name: "demo_lh_model4", why: "x" });
  it("adopts only a same-plan leftover named as the output the latest Create built without an id", () => {
    expect(autoAdopt([unsaved], LEFTOVERS)).toEqual([{ id: LEFTOVERS.leftovers[0].id, name: "demo_lh_model4" }]);
    expect(autoAdopt([row({ key: "unsaved:report", name: "old_report" })], LEFTOVERS)).toEqual([]);   // another plan
    expect(autoAdopt([row({ key: "x", id: "1", name: "demo_lh_model4" })], LEFTOVERS)).toEqual([]);   // nothing lost
  });
  it("says it once", () => {
    act(() => root.render(<DataProductView productName="shop" outputs={OUTPUTS} status={STATUS} adopted={["demo_lh_gold"]} />));
    expect(host.textContent!.split("Found and added").length - 1).toBe(1);
    expect(adoptedLine(["demo_lh_gold"])).toContain("plan marker matched");
  });
});

describe("a failed row", () => {
  it("says one line, points to Fix and finish once, and keeps Fabric's message under Details", () => {
    const outputs = { ...OUTPUTS, last_create: { at: "2026-11-21T13:30:00Z", outputs: [
      { output: "rayfin_app", label: "App", name: "demo_lh_app", state: "failed", reason: "HTTP 409: ItemDisplayNameAlreadyInUse, Requested 'demo_lh_silver' is already in use (a long Fabric message)" },
      { output: "drift_monitor", label: "Drift monitor", name: "demo_lh_drift", state: "failed", reason: "HTTP 404: EntityNotFound (a long Fabric message)" },
    ] } } as never;
    const fix = vi.fn();
    act(() => root.render(<DataProductView productName="shop" outputs={outputs} status={STATUS} onFixAndFinish={fix} plan={undefined} />));
    const failed = Array.from(host.querySelectorAll("[data-state=failed]"));
    expect(failed.length).toBeGreaterThan(0);
    for (const li of failed) {
      expect(li.textContent).toContain(FAILED_LINE);
      expect(li.querySelector("details summary")!.textContent).toBe("Details");
    }
    const buttons = Array.from(host.querySelectorAll("button")).filter((b) => b.textContent?.startsWith("Fix and finish"));
    expect(buttons.length).toBe(1);
    act(() => buttons[0].click());
    expect(fix).toHaveBeenCalled();
  });
});

describe("refresh and health", () => {
  it("the manual refresh is small, and health has one button", () => {
    const check = vi.fn();
    act(() => root.render(<DataProductView productName="shop" outputs={OUTPUTS} status={STATUS} onCheckHealth={check} />));
    const refresh = host.querySelector("button[aria-label='Read Fabric again']")!;
    expect(refresh.className).toContain("kg-dp-small");
    const health = Array.from(host.querySelectorAll("button")).find((b) => b.textContent === "Check health now")!;
    act(() => health.click());
    expect(check).toHaveBeenCalled();
  });
});

const FILES: Record<string, string> = {
  "handover/fabric-admin.md": "# OneLake catalog for shop_lh: for the Fabric administrator\n",
  "handover/endorsement.md": "# OneLake catalog for shop_lh: endorsement\n",
  "handover/purview.json": JSON.stringify({ retiring: "x", products: [{ name: "customers" }] }, null, 2) + "\n",
  "contracts/customers.odcs.yaml": "apiVersion: v3.0.2\nkind: DataContract\ndataProduct: customers\ndescription:\n  purpose: Proposed data product\n  usage: Draft\n",
  "contracts/orders.odcs.yaml": "apiVersion: v3.0.2\nkind: DataContract\ndataProduct: orders\n",
};
const ANSWER = {
  summary: "2 data product card(s)", products: [], diff: [{ item: "demo_lh_gold", field: "description", before: "", after: "Krusgraph notebook x.", action: "write" }],
  confirm: "catalog-abc", writable: false,
  handover: { requests: [], approvals: [], files: FILES }, note: "",
} as unknown as CatalogAnswer;

describe("Publish to OneLake catalog", () => {
  const view = (a: CatalogAnswer) => (
    <CatalogView answer={a} busy={false} owner="Anna Berg" checked={false} onOwner={() => {}} onPrepare={() => {}} onChecked={() => {}} onWrite={() => {}} />);
  it("with writing off: no checkbox, the reason beside the disabled button", () => {
    act(() => root.render(view(ANSWER)));
    expect(host.querySelector(".kg-catalog-write input[type=checkbox]")).toBeNull();
    const btn = Array.from(host.querySelectorAll("button")).find((b) => b.textContent?.startsWith("Write "))!;
    expect(btn.hasAttribute("disabled")).toBe(true);
    expect(host.querySelector("#kg-catalog-why")!.textContent).toBe(WRITING_OFF);
  });
  it("asks for no owner of its own", () => {
    act(() => root.render(view(ANSWER)));
    expect(host.querySelector("input[name=kg-catalog-owner]")).toBeNull();
    expect(host.textContent).toContain("Owner: Anna Berg, the data product's owner");
  });
  it("each Copy and each Download gives exactly that one file", async () => {
    const copied: string[] = [];
    Object.assign(navigator, { clipboard: { writeText: async (t: string) => { copied.push(t); } } });
    const offered: { filename: string; text?: string }[] = [];
    await act(async () => root.render(
      <CatalogContext.Provider value={undefined}>{view(ANSWER)}</CatalogContext.Provider>));
    for (const [path, text] of Object.entries(FILES)) {
      const copy = Array.from(host.querySelectorAll("button")).find((b) => b.textContent === `Copy ${path}`)!;
      await act(async () => copy.click());
      expect(copied[copied.length - 1]).toBe(text);
      for (const [other, body] of Object.entries(FILES)) if (other !== path) expect(copied[copied.length - 1].includes(body.trim())).toBe(false);
    }
    expect(copied.length).toBe(Object.keys(FILES).length);
    void offered;
    // the download link of each file holds that file alone
    for (const path of Object.keys(FILES)) {
      const dl = host.querySelector(`button[aria-label='Download ${path}']`) as HTMLButtonElement;
      await act(async () => dl.click());
    }
    const links = Array.from(host.querySelectorAll(".kg-file a")) as HTMLAnchorElement[];
    for (const a of links) {
      const body = decodeURIComponent(a.href.split(",").slice(1).join(","));
      expect(Object.values(FILES)).toContain(body);
    }
    void WS;
  });
});
