// @vitest-environment jsdom
// n223: the map, the data flow and the Data product page load when first shown (lazyParts.tsx): skeleton rows first,
// then the part itself; and the item keeps the last map and the schema list (item.json cache) for an instant first paint.
import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DataProductPage, FlowView, PlanMap, loadDataProduct, loadFlowView, loadPlanMap } from "./lazyParts";
import { emptyDefinition, fromParts, toParts } from "./ModelItemDefinition";
import { cachedSchemas } from "./ModelItemEditor";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const FLOW = JSON.parse(readFileSync(join(__dirname, "flow.fixture.json"), "utf-8"));
const MAP = { tables: [{ name: "orders", columns: 3 }, { name: "customers", columns: 2 }], relationships: [] } as never;

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

async function settle() {
  for (let i = 0; i < 10; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}

describe("the lazy parts of the editor", () => {
  it("are separate modules the editor imports only when shown", async () => {
    const src = readFileSync(join(__dirname, "ModelItemEditor.tsx"), "utf-8") + readFileSync(join(__dirname, "ModelItemViews.tsx"), "utf-8");
    expect(src).not.toMatch(/from "\.\/DataProductView"/);
    expect(src).not.toMatch(/from "\.\/FlowView"/);
    expect(src).not.toMatch(/from "\.\/planMapView"/);
    expect((await loadPlanMap()).PlanMap).toBeTypeOf("function");
    expect((await loadFlowView()).FlowView).toBeTypeOf("function");
    expect((await loadDataProduct()).DataProductView).toBeTypeOf("function");
  });

  it("show skeleton rows with a label first, then the data flow", async () => {
    act(() => root.render(<FlowView flow={FLOW} mascotsOn={false} idPrefix="t" />));
    await settle();
    expect(host.querySelector(".kg-skel")).toBeNull();
    expect(host.innerHTML).toContain("<svg");
  });

  it("show the map once its chunk is there", async () => {
    act(() => root.render(<PlanMap map={MAP} />));
    await settle();
    expect(host.querySelector(".krusgraph-map")).not.toBeNull();
  });

  it("show the Data product page with the editor's wait above it, the page itself staying", async () => {
    const outputs = { version: 1, outputs: [], created: [{ type: "Notebook", id: "n1", name: "demo_silver", workspace: "w" }] } as never;
    act(() => root.render(<DataProductPage productName="demo" outputs={outputs} busy="Reading the items in Fabric…"
      waiting={<div data-testid="kg-wait">Onto: Reading the items in Fabric…</div>} />));
    await settle();
    expect(host.textContent).toContain("Data product: demo");
    expect(host.querySelector('[data-testid="kg-wait"]')).not.toBeNull();
    expect(host.textContent).toContain("demo_silver");
  });

  it("stand in with labelled skeleton rows while a chunk loads", async () => {
    const { renderToStaticMarkup } = await import("react-dom/server");
    const { Skeleton } = await import("./OntoWait");
    const html = renderToStaticMarkup(<Skeleton rows={5} label="Opening the Data product page…" />);
    expect(html).toBe('<div class="kg-skel" role="status" aria-label="Opening the Data product page…"><span></span><span></span><span></span><span></span><span></span></div>');
    expect(readFileSync(join(__dirname, "lazyParts.tsx"), "utf-8").match(/<Suspense fallback=\{<Skeleton rows=\{\d\} label="[^"]+" \/>\}>/g)).toHaveLength(3);
  });
});

describe("the item's cache for a first paint", () => {
  it("keeps the last map and the schema list in item.json, and drops what is not its shape", () => {
    const def = emptyDefinition();
    const list = { schemas: [{ schema: "shop", tables: 7 }], preselect: "shop", note: "" };
    const withCache = { ...def, source: { version: 1, platform: "fabric" as const, workspaceId: "w", itemId: "lh", itemType: "Lakehouse", displayName: "demo_lh", schema: "shop" },
      item: { ...def.item, cache: { map: MAP, schemas: { source: "lh", list } } } };
    const back = fromParts(toParts(withCache) as never);
    expect(back.item.cache?.map).toEqual(MAP);
    expect(cachedSchemas(back)).toEqual(list);
    expect(cachedSchemas(back, "another")).toBeUndefined();     // another source: no list shown from the cache
    const bad = fromParts(toParts({ ...def, item: { ...def.item, cache: { map: { nope: 1 }, schemas: { source: 3 } } as never } }) as never);
    expect(bad.item.cache).toBeUndefined();
    expect(fromParts(toParts(def) as never).item.cache).toBeUndefined();   // an older item reads as before
  });
});
