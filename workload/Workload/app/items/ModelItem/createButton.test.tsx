// @vitest-environment jsdom
// n222, from the founder's live test of 11 November 2026, with the real editor rendered:
// - the dry run page's own Create button "did nothing" (only the toolbar's Create started Create). Create waited for the
//   item's save before it showed anything, so with Fabric slow to save a click looked lost and a second click could start a
//   second Create. Now the click shows the cards at once and locks both buttons; one Create at a time.
// - "Suggested data products" after the review: tick one, and the dry run sends it and shows it as a data product.
// - the dry run's busy line shows the engine's progress words as they come.
import React from "react";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { MemoryRouter, Route } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BuildCard, ManyAnswer, SuggestedProducts } from "./engineClient";

const CARD = (output: string, name: string): BuildCard => ({
  output, label: output, type: "GraphQLApi", name, dry_run: true, would: "create", updates_in_place: true,
  permissions: { needs: [], missing: null, execute: "" }, answer: { dry_run: true },
} as unknown as BuildCard);

const SUGGESTED: SuggestedProducts = {
  products: [
    { id: "customers", name: "customers", tables: ["addresses", "customers", "order_items", "orders"], rule: "Tables joined by their keys.",
      name_reason: "the tables share the name prefix", why: {}, interface: { provides: [], consumes: [{ product: "products", id: "products", link: "order_items.product_id → products", rule: "R1" }] },
      evidence: ["link orders.customer_id → customers (R1; not checked against the rows)"] },
    { id: "products", name: "products", tables: ["categories", "products"], rule: "Tables joined by their keys.",
      name_reason: "products is the table the others point at most", why: {}, interface: { provides: [{ product: "customers", id: "customers", link: "order_items.product_id → products", rule: "R1" }], consumes: [] },
      evidence: ["key products.product_id (K2; not checked against the rows)"] },
  ],
  unassigned: [{ table: "audit_log", reason: "no key" }], checked: false, from: "domain_draft's proposal", note: "Suggestions, not decisions.",
};

const hold: { release?: () => void; progress?: (s: unknown) => void } = {};

vi.mock("./engineClient", async (orig) => {
  const real = await orig<typeof import("./engineClient")>();
  const review = { format: "krusgraph-review", version: 1, plan_id: "p1", source: { schema: "dbo" }, items: [] as unknown[] };
  const dry = (products?: { id: string; name: string }[]): ManyAnswer => ({
    dry_run: true, outputs: [CARD("graphql", "demo_lh_api")], order: ["graphql"], refused: 0, to_decide: 0, left_out_by_review: [],
    note: "Nothing was created or changed in Fabric.", row_check: { checked: 0 },
    ...(products?.length ? { products: [{ id: "products", name: "products", tables: ["categories", "products"], words: "2 table(s); the outputs of this build cover them.",
      interface: { provides: [{ product: "customers", id: "customers", link: "order_items.product_id → products", rule: "R1" }], consumes: [] }, items: [{ type: "GraphQLApi", name: "demo_lh_api" }] }] } : {}),
  } as unknown as ManyAnswer);
  return {
    ...real,
    access: vi.fn(async () => null),
    schemas: vi.fn(async () => ({ schemas: [{ schema: "dbo", tables: 3 }], preselect: "dbo", note: "" })),
    review: vi.fn(async () => ({ review, summary: "", attention: [] as string[], note: "", suggested_products: SUGGESTED,
      counts: { keys: 0, relationships: 0, review: {}, open_questions: 0 } })),
    buildMany: vi.fn(async (_wc: unknown, _s: unknown, _o: unknown, _r: unknown, _d: boolean, _p: unknown, _c: unknown, _pe: unknown,
      opts?: { onProgress?: (s: unknown) => void; products?: { id: string; name: string }[] }) => {
      if (hold.progress === undefined && opts?.onProgress) {
        hold.progress = opts.onProgress;
      }
      return dry(opts?.products);
    }),
    buildOne: vi.fn(async () => ({ dry_run: false, outputs: [{ ...CARD("graphql", "demo_lh_api"), dry_run: false,
      created: [{ id: "x1", type: "GraphQLApi", name: "demo_lh_api" }] }], order: ["graphql"], refused: 0, left_out_by_review: [] as unknown[],
      note: "1 of 1 output(s) built.", created: [{ id: "x1", type: "GraphQLApi", name: "demo_lh_api" }] })),
    finish: vi.fn(async () => ({ outputs: [] as unknown[], flow: null as unknown })),
    itemOperations: vi.fn(async () => ({ operations: [] as unknown[] })),
  };
});

import { ModelItemEditor } from "./ModelItemEditor";
import { EditorErrorBoundary } from "./EditorErrorBoundary";
import { encodeJson } from "./ModelItemDefinition";
import * as engine from "./engineClient";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const WS = "11111111-1111-1111-1111-111111111111";
const LH = "22222222-2222-2222-2222-222222222222";
const ITEM = "33333333-3333-3333-3333-333333333333";
const part = (path: string, v: unknown) => ({ path, payload: encodeJson(v), payloadType: "InlineBase64" });

function client(slowSave: boolean) {
  return {
    itemCrud: {
      getItem: vi.fn(async () => ({ item: { id: ITEM, workspaceId: WS, displayName: "Model 1", type: "Org.Krusgraph.Model" } })),
      getItemDefinition: vi.fn(async () => ({ definition: { parts: [
        part("item.json", { version: 1, format: "krusgraph-model", view: "review" }),
        part("source.json", { version: 1, platform: "fabric", workspaceId: WS, itemId: LH, itemType: "Lakehouse", displayName: "demo_lh", schema: "dbo" }),
        part("outputs.json", { version: 1, outputs: [], created: [] }),
        part("review.json", { format: "krusgraph-review", version: 1, plan_id: "p1", source: {}, items: [] }),
      ] } })),
      // Fabric slow to save: every save waits until the test releases it
      updateItemDefinition: vi.fn(() => (slowSave ? new Promise((r) => { const prev = hold.release; hold.release = () => { prev?.(); r({}); }; }) : Promise.resolve({}))),
    },
    datahub: { openDialog: vi.fn() },
    notification: { open: vi.fn(async () => ({})) },
    navigation: { navigate: vi.fn() },
  };
}

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  vi.clearAllMocks();
  hold.release = undefined;
  hold.progress = undefined;
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

async function flush() {
  for (let i = 0; i < 8; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}
function buttons(text: RegExp): HTMLButtonElement[] {
  return Array.from(host.querySelectorAll("button")).filter((x) =>
    text.test((x.textContent ?? "").trim()) || text.test(x.getAttribute("aria-label") ?? "")) as HTMLButtonElement[];
}
function button(text: RegExp): HTMLButtonElement {
  const b = buttons(text)[0];
  if (!b) throw new Error(`no button ${text} in: ${host.textContent}`);
  return b;
}
const pageCreate = () => Array.from(host.querySelectorAll(".krusgraph-view button")).filter((b) => /^Creat/.test((b.textContent ?? "").trim())) as HTMLButtonElement[];

async function open(slowSave = false) {
  const wc = client(slowSave);
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[`/ModelItem-editor/${ITEM}`]}>
        <Route path="/ModelItem-editor/:itemObjectId">
          <EditorErrorBoundary><ModelItemEditor workloadClient={wc as never} /></EditorErrorBoundary>
        </Route>
      </MemoryRouter>
    );
  });
  await flush();
  await act(async () => { button(/^Next$/).click(); });
  await flush();
  return wc;
}

async function toDryRun(slowSave = false) {
  const wc = await open(slowSave);
  await act(async () => { button(/^Preview$/).click(); });
  await flush();
  expect(host.textContent).toMatch(/Dry run/);
  return wc;
}

describe("n222: Create on the dry run page", () => {
  it("the page's own Create button starts Create", async () => {
    await toDryRun();
    expect(pageCreate().length).toBe(1);
    await act(async () => { pageCreate()[0].click(); });
    await flush();
    expect(engine.buildOne).toHaveBeenCalledTimes(1);
  });

  it("with Fabric slow to save, the click shows the Create's cards at once and a second click starts nothing", async () => {
    await toDryRun(true);
    hold.release?.();                                            // the dry run's own save
    hold.release = undefined;
    await flush();
    await act(async () => { pageCreate()[0].click(); });
    await flush();
    expect(host.textContent).not.toMatch(/This is the dry run/);   // the result view, not the dry run
    expect(host.textContent).toMatch(/demo_lh_api/);
    expect(engine.buildOne).not.toHaveBeenCalled();               // the save is still on its way
    for (const b of buttons(/^Create$/)) await act(async () => { b.click(); });   // the toolbar's Create, if it is still shown
    await flush();
    hold.release?.();
    await flush();
    hold.release?.();
    await flush();
    expect(engine.buildOne).toHaveBeenCalledTimes(1);            // one Create
  });
});

describe("n222: suggested data products", () => {
  it("are shown after the review with tables, rule, interface and evidence; a ticked one is in the dry run", async () => {
    await open();
    const panel = host.querySelector('[aria-label="Suggested data products"]');
    expect(panel?.textContent).toMatch(/2 suggested data products/);
    expect(panel?.textContent).toMatch(/Tables: categories, products/);
    expect(panel?.textContent).toMatch(/Grouped by: Tables joined by their keys/);
    expect(panel?.textContent).toMatch(/Provides to customers: order_items.product_id → products \(R1\)/);
    expect(panel?.textContent).toMatch(/Evidence \(1\)/);
    expect(panel?.textContent).toMatch(/audit_log \(no key\)/);
    const box = host.querySelector('[data-product="products"] input[type="checkbox"]') as HTMLInputElement;
    await act(async () => { box.click(); });
    await flush();
    await act(async () => { button(/^Preview$/).click(); });
    await flush();
    const opts = (engine.buildMany as unknown as { mock: { calls: unknown[][] } }).mock.calls[0][8] as { products?: unknown[] };
    expect(opts.products).toEqual([{ id: "products", name: "products" }]);
    const shown = host.querySelector('[aria-label="Data products (dry run)"]');
    expect(shown?.textContent).toMatch(/products: categories, products/);
  });
});

describe("n222: the dry run's progress line", () => {
  it("shows the engine's words while the outputs are prepared", async () => {
    let finish: (a: unknown) => void = () => undefined;
    (engine.buildMany as unknown as { mockImplementationOnce: (f: unknown) => void }).mockImplementationOnce(
      (_a: unknown, _b: unknown, _c: unknown, _d: unknown, _e: unknown, _f: unknown, _g: unknown, _h: unknown, opts: { onWait: (s: unknown) => void }) =>
        new Promise((r) => { hold.progress = opts.onWait; finish = r; }));
    await open();
    await act(async () => { button(/^Preview$/).click(); });
    await flush();
    expect(host.textContent).toMatch(/Preparing the dry run of each output/);
    await act(async () => { hold.progress?.({ kind: "engine", words: "Dry run: 3 of 6 outputs prepared (Silver notebook, Gold views, API for GraphQL)." }); });
    expect(host.textContent).toMatch(/Dry run: 3 of 6 outputs prepared/);
    await act(async () => { finish({ dry_run: true, outputs: [CARD("graphql", "x")], order: ["graphql"], refused: 0, left_out_by_review: [], note: "", row_check: { checked: 0 } }); });
    await flush();
    expect(host.textContent).toMatch(/Dry run/);
  });
});
