// @vitest-environment jsdom
// n223: reopening an item with a review shows the saved review and the map kept with it at once, and reads the review
// again behind it with Onto's line above (it used to be a page that only spun until the engine answered). The item and
// its definition are read at the same time, and the schemas are not listed where they are not shown.
import React from "react";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { MemoryRouter, Route } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let answerReview: (a: unknown) => void = () => undefined;
vi.mock("./engineClient", async (orig) => {
  const real = await orig<typeof import("./engineClient")>();
  return {
    ...real,
    access: vi.fn(async () => null),
    schemas: vi.fn(async () => ({ schemas: [{ schema: "shop", tables: 7 }], preselect: "shop", note: "" })),
    review: vi.fn(() => new Promise((r) => { answerReview = r; })),
  };
});

import { ModelItemEditor } from "./ModelItemEditor";
import { emptyDefinition, toParts } from "./ModelItemDefinition";
import * as engine from "./engineClient";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const WS = "11111111-1111-1111-1111-111111111111";
const LH = "22222222-2222-2222-2222-222222222222";
const ITEM = "33333333-3333-3333-3333-333333333333";

const REVIEW = {
  format: "krusgraph-review", version: 1, plan_id: "p1", source: { platform: "fabric", source: "demo_lh", schema: "shop" },
  items: [{ id: "key:orders", type: "key", rule: "R1", columns: ["order_id"], table: "orders", review: "proposed" }],
};
const MAP = { tables: [{ name: "orders", columns: 3 }], relationships: [] as unknown[] };

function saved() {
  const d = emptyDefinition();
  return toParts({
    ...d,
    item: { ...d.item, view: "review", cache: { map: MAP as never, schemas: { source: LH, list: { schemas: [{ schema: "shop", tables: 7 }], preselect: "shop", note: "" } } } },
    source: { version: 1, platform: "fabric", workspaceId: WS, itemId: LH, itemType: "Lakehouse", displayName: "demo_lh", schema: "shop" },
    review: REVIEW as never,
  });
}

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

async function flush() {
  for (let i = 0; i < 8; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}

describe("n223: reopening an item with a review", () => {
  it("reads the item and its definition at the same time, then shows the saved review while it is read again", async () => {
    const order: string[] = [];
    let giveItem: (x: unknown) => void = () => undefined;
    const wc = {
      itemCrud: {
        getItem: vi.fn(() => { order.push("item"); return new Promise((r) => { giveItem = r; }); }),
        getItemDefinition: vi.fn(async () => { order.push("definition"); return { definition: { parts: saved() } }; }),
        updateItemDefinition: vi.fn(async () => ({})),
      },
      notification: { open: vi.fn(async () => ({})) },
      navigation: { navigate: vi.fn() },
    };
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={[`/ModelItem-editor/${ITEM}`]}>
          <Route path="/ModelItem-editor/:itemObjectId"><ModelItemEditor workloadClient={wc as never} /></Route>
        </MemoryRouter>
      );
    });
    await flush();
    expect(order).toEqual(["item", "definition"]);                       // both asked before either answered
    expect(host.querySelector('[data-testid="kg-wait"]')).not.toBeNull();   // Onto while Fabric hands over the item
    expect(host.textContent).toContain("Opening the model…");

    await act(async () => { giveItem({ item: { id: ITEM, workspaceId: WS, displayName: "Model 1", type: "Org.Krusgraph.Model" } }); });
    await flush();
    const text = host.textContent ?? "";
    expect(text).toContain("1 key and 0 links");                          // the saved review, at once
    expect(text).toContain("Check against the rows");
    expect(text).toContain("Reading the tables in shop and finding keys and links again; the saved review is shown meanwhile…");
    expect(host.querySelector(".kg-skel")).toBeNull();                    // a line above the review, not a page of grey rows
    expect(engine.review).toHaveBeenCalledTimes(1);
    expect(engine.schemas).not.toHaveBeenCalled();                        // not listed where it is not shown

    await act(async () => { answerReview({ review: REVIEW, map: MAP }); });
    await flush();
    expect(host.textContent).not.toContain("the saved review is shown meanwhile");
  });
});
