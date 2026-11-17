// @vitest-environment jsdom
// W14: autosave in the real editor with a stand-in Fabric host (W13 found decisions lost when the item was closed
// before Save). A decision is saved without Save; a decision made just before the item is closed comes back on the next
// opening and is saved; another session's save in the meantime is merged and said in words.
import React from "react";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { MemoryRouter, Route } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./engineClient", async (orig) => {
  const real = await orig<typeof import("./engineClient")>();
  return {
    ...real,
    access: vi.fn(async () => null),
    schemas: vi.fn(async () => ({ schemas: [{ schema: "dbo", tables: 3 }], preselect: "dbo", note: "" })),
    // the engine re-plans with the saved review as `previous`, so decisions carry over: answer it as it is
    review: vi.fn(async (_c: unknown, _s: unknown, previous: unknown) => ({
      review: previous, summary: "", attention: [], note: "",
      counts: { keys: 2, relationships: 0, review: {}, open_questions: 0 },
    })),
  };
});

import { ModelItemEditor } from "./ModelItemEditor";
import { EditorErrorBoundary } from "./EditorErrorBoundary";
import { AUTOSAVE_DELAY_MS, DRAFT_PREFIX } from "./autosave";
import { DefinitionPart, ModelDefinition, ReviewFile, emptyDefinition, fromParts, toParts } from "./ModelItemDefinition";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const WS = "11111111-1111-1111-1111-111111111111";
const LH = "22222222-2222-2222-2222-222222222222";
const ITEM = "33333333-3333-3333-3333-333333333333";

const REVIEW: ReviewFile = {
  format: "krusgraph-review", version: 3, plan_id: "p1", source: { platform: "fabric", schema: "dbo" },
  items: [
    { id: "k1", type: "key", rule: "K1", columns: ["order_id"], table: "orders", review: "proposed" },
    { id: "k2", type: "key", rule: "K1", columns: ["customer_id"], table: "customers", review: "proposed" },
  ],
};

function stored(review: ReviewFile = REVIEW, rev?: number): ModelDefinition {
  const d = emptyDefinition();
  return {
    ...d,
    item: { ...d.item, view: "review", ...(rev ? { saved: { rev, at: "2026-11-17T10:00:00.000Z", session: "other" } } : {}) },
    source: { version: 1, platform: "fabric", workspaceId: WS, itemId: LH, itemType: "Lakehouse", displayName: "demo_lh", schema: "dbo" },
    review,
  };
}
const decided = (r: ReviewFile, id: string, s: "accepted" | "rejected"): ReviewFile =>
  ({ ...r, items: r.items.map((x) => (x.id === id ? { ...x, review: s, reason: "" } : x)) });

/** The stand-in host: one item whose parts live in `fabric.parts`; every read answers what is there now. */
function host(initial: ModelDefinition) {
  const fabric = { parts: toParts(initial) as DefinitionPart[] };
  const wc = {
    itemCrud: {
      getItem: vi.fn(async () => ({ item: { id: ITEM, workspaceId: WS, displayName: "Model 1", type: "Org.Krusgraph.Model" } })),
      getItemDefinition: vi.fn(async () => ({ definition: { parts: fabric.parts } })),
      updateItemDefinition: vi.fn(async (p: { payload?: { definition?: { parts?: DefinitionPart[] } } }) => {
        fabric.parts = p?.payload?.definition?.parts ?? [];
        return {};
      }),
    },
    datahub: { openDialog: vi.fn(async () => ({})) },
    notification: { open: vi.fn(async () => ({})) },
    navigation: { navigate: vi.fn() },
  };
  return { wc, fabric, saved: () => fromParts(fabric.parts) };
}

let el: HTMLDivElement;
let root: Root;
beforeEach(() => {
  localStorage.clear();
  el = document.createElement("div");
  document.body.appendChild(el);
  root = createRoot(el);
});
afterEach(() => {
  act(() => root.unmount());
  el.remove();
});

async function flush(ms = 0) {
  for (let i = 0; i < 5; i++) await act(async () => { await new Promise((r) => setTimeout(r, i === 0 ? ms : 0)); });
}
async function open(wc: unknown) {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[`/ModelItem-editor/${ITEM}`]}>
        <Route path="/ModelItem-editor/:itemObjectId">
          <EditorErrorBoundary><ModelItemEditor workloadClient={wc as never} /></EditorErrorBoundary>
        </Route>
      </MemoryRouter>
    );
  });
  for (let i = 0; i < 40 && !/Accept all/.test(el.textContent ?? ""); i++) await flush(25);   // lazy parts
  await flush();
}
function accept(n: number) {
  // the review opens on the map; the list has an Accept per key and link
  const list = Array.from(el.querySelectorAll("button, [role=tab]")).find((x) => /^(List)+$/.test(x.textContent ?? "")) as HTMLElement | undefined;
  if (list && !Array.from(el.querySelectorAll("button")).some((x) => x.textContent === "Accept")) act(() => { list.click(); });
  const b = Array.from(el.querySelectorAll("button")).filter((x) => x.textContent === "Accept")[n];
  if (!b) throw new Error(`no Accept button ${n} in: ${el.textContent}`);
  act(() => { (b as HTMLButtonElement).click(); });
}
const line = () => el.querySelector(".kg-autosave-line");
const status = (d: ModelDefinition, id: string) => d.review?.items.find((x) => x.id === id)?.review;

describe("W14: autosave in the Model editor", () => {
  it("a decision is saved without Save, and the line says so", async () => {
    const h = host(stored());
    await open(h.wc);
    expect(line()?.getAttribute("role")).toBe("status");
    expect(line()?.textContent).toMatch(/Saved/);
    const before = h.wc.itemCrud.updateItemDefinition.mock.calls.length;
    accept(0);
    await flush();
    expect(line()?.textContent).toMatch(/Unsaved changes/);
    expect(localStorage.getItem(DRAFT_PREFIX + ITEM)).toContain("accepted");   // kept in this browser at once
    await flush(AUTOSAVE_DELAY_MS + 200);
    expect(h.wc.itemCrud.updateItemDefinition.mock.calls.length).toBe(before + 1);
    expect(status(h.saved(), "k1")).toBe("accepted");
    expect(h.saved().item.saved?.rev).toBe(1);
    expect(line()?.textContent).toMatch(/✓ Saved \d\d:\d\d UTC/);
    expect(localStorage.getItem(DRAFT_PREFIX + ITEM)).toBeNull();               // in Fabric now: the draft is gone
  });

  it("several quick decisions are one save", async () => {
    const h = host(stored());
    await open(h.wc);
    const before = h.wc.itemCrud.updateItemDefinition.mock.calls.length;
    accept(0);
    await flush(200);
    accept(0);                                                   // the list puts what is still undecided first
    await flush(AUTOSAVE_DELAY_MS + 200);
    expect(h.wc.itemCrud.updateItemDefinition.mock.calls.length).toBe(before + 1);
    expect([status(h.saved(), "k1"), status(h.saved(), "k2")]).toEqual(["accepted", "accepted"]);
  });

  it("closed before the save: the decision comes back on the next opening and is saved", async () => {
    const h = host(stored());
    await open(h.wc);
    accept(0);
    await flush();
    act(() => root.unmount());                                   // closed at once, before the autosave's pause ends
    expect(status(h.saved(), "k1")).toBe("proposed");            // Fabric did not get it
    root = createRoot(el);
    await open(h.wc);
    expect(el.textContent).toMatch(/Recovered changes from \d\d:\d\d UTC that were not saved in Fabric yet/);
    await flush(AUTOSAVE_DELAY_MS + 200);
    expect(status(h.saved(), "k1")).toBe("accepted");
  });

  it("another session saved meanwhile: its decision is kept, this one's too, and a warning says so", async () => {
    const h = host(stored(REVIEW, 1));
    await open(h.wc);
    // the other session rejects k2 and saves revision 2 while this one accepts k1
    h.fabric.parts = toParts(stored(decided(REVIEW, "k2", "rejected"), 2));
    accept(0);
    await flush(AUTOSAVE_DELAY_MS + 200);
    const d = h.saved();
    expect([status(d, "k1"), status(d, "k2")]).toEqual(["accepted", "rejected"]);
    expect(d.item.saved?.rev).toBe(3);
    const note = el.querySelector(".kg-autosave-note");
    expect(note?.getAttribute("role")).toBe("alert");
    expect(note?.textContent).toMatch(/Someone else saved this item at 10:00 UTC\. Their decision on 1 item you had not changed was kept\./);
  });

  it("both changed the same item: this session's decision is saved (last write wins) with a warning", async () => {
    const h = host(stored(REVIEW, 1));
    await open(h.wc);
    h.fabric.parts = toParts(stored(decided(REVIEW, "k1", "rejected"), 2));
    accept(0);
    await flush(AUTOSAVE_DELAY_MS + 200);
    expect(status(h.saved(), "k1")).toBe("accepted");
    expect(el.querySelector(".kg-autosave-note")?.textContent).toMatch(/On 1 item you both changed, your decision was saved over theirs\./);
  });

  it("Fabric refuses the save: Not saved, Save again, and the draft stays", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const h = host(stored());
      h.wc.itemCrud.updateItemDefinition.mockImplementation(async () => undefined as never);
      await open(h.wc);
      accept(0);
      await act(async () => { await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS + 20000); });
      await flush();
      expect(line()?.textContent).toMatch(/✕ Not saved/);
      expect(Array.from(el.querySelectorAll("button")).some((b) => b.textContent === "Save again")).toBe(true);
      expect(localStorage.getItem(DRAFT_PREFIX + ITEM)).toContain("accepted");
    } finally {
      vi.useRealTimers();
    }
  });
});
