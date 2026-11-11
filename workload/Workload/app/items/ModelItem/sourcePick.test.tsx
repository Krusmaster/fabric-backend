// @vitest-environment jsdom
// n215: the editor went blank (white) right after a lakehouse was picked in the OneLake catalog. The Fabric host answers
// datahub.openDialog with selectedDatahubItem[0].datahubItemUI, whose itemType the workload client types as `any`
// (Fabric's own item type enum, a number), with the REST name in fabricItemType. n201 stored that number as the
// source's itemType; isReadOnly(number) was true, so the empty view drew the target line, and
// sourceLabel(number).toLowerCase() threw during render: React unmounted the whole editor.
// This test renders the real editor, with the real DataHubController, and feeds it the host's shapes.
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
  };
});

import { ModelItemEditor } from "./ModelItemEditor";
import { EditorErrorBoundary } from "./EditorErrorBoundary";
import * as engine from "./engineClient";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const WS = "11111111-1111-1111-1111-111111111111";
const LH = "22222222-2222-2222-2222-222222222222";
const ITEM = "33333333-3333-3333-3333-333333333333";

/** selectedDatahubItem[0] as the host returns it for a picked lakehouse (BaseDatahubItemUI in the workload client). */
function picked(ui: Record<string, unknown> | undefined) {
  return {
    selectedDatahubItem: [{
      workspaceObjectId: WS,
      itemObjectId: LH,
      datahubItemUI: ui && { itemObjectId: LH, displayName: "demo_lh", workspaceName: "demo", workspaceObjectId: WS, ...ui },
    }],
  };
}

function client(answer: unknown) {
  return {
    itemCrud: {
      getItem: vi.fn(async () => ({ item: { id: ITEM, workspaceId: WS, displayName: "Model 1", type: "Org.Krusgraph.Model" } })),
      getItemDefinition: vi.fn(async () => ({ definition: { parts: [] } })),
      updateItemDefinition: vi.fn(async () => ({})),
    },
    datahub: { openDialog: vi.fn(async () => answer) },
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
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

async function flush() {
  for (let i = 0; i < 5; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}

function button(text: RegExp): HTMLButtonElement {
  const b = Array.from(host.querySelectorAll("button")).find((x) => text.test(x.textContent ?? ""));
  if (!b) throw new Error(`no button ${text} in: ${host.textContent}`);
  return b as HTMLButtonElement;
}

async function pickWith(answer: unknown) {
  const wc = client(answer);
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
  await act(async () => { button(/Choose a source/).click(); });
  await flush();
  return wc;
}

describe("n215: picking a lakehouse in the OneLake catalog", () => {
  const shapes: [string, Record<string, unknown> | undefined][] = [
    ["itemType as Fabric's numeric enum, fabricItemType 'Lakehouse'", { itemType: 13, fabricItemType: "Lakehouse" }],
    ["itemType as a number only", { itemType: 13 }],
    ["itemType 'lakehouse' in lower case", { itemType: "lakehouse" }],
    ["itemType 'Lakehouse'", { itemType: "Lakehouse" }],
    ["itemType as an object", { itemType: { name: "Lakehouse" } }],
    ["no datahubItemUI", undefined],
  ];
  it.each(shapes)("%s: the editor shows the next step, not a white page", async (_, ui) => {
    await pickWith(picked(ui));
    const text = host.textContent ?? "";
    expect(text).not.toMatch(/Something went wrong in the editor/);
    expect(text).toMatch(ui ? /Lakehouse: demo_lh/ : /Lakehouse:/);
    expect(text).toMatch(/Find keys and relationships/);
    // a lakehouse is not read-only: no Target lakehouse step
    expect(text).not.toMatch(/Target lakehouse/);
    expect(button(/Find keys and relationships/).disabled).toBe(false);
    expect(engine.schemas).toHaveBeenLastCalledWith(expect.anything(), { workspace: WS, source: LH, source_name: ui ? "demo_lh" : "" });
  });

  it("a warehouse named by fabricItemType is read-only and offers the target", async () => {
    await pickWith(picked({ itemType: 7, fabricItemType: "Warehouse", displayName: "demo_wh" }));
    expect(host.textContent).toMatch(/Warehouse: demo_wh/);
    expect(host.textContent).toMatch(/Target lakehouse/);
  });

  it("a render error shows its text and Reload, not a white page", async () => {
    const Boom = () => { throw new Error("kaboom"); };
    const quiet = vi.spyOn(console, "error").mockImplementation(() => undefined);
    await act(async () => { root.render(<EditorErrorBoundary><Boom /></EditorErrorBoundary>); });
    quiet.mockRestore();
    expect(host.textContent).toMatch(/Something went wrong in the editor/);
    expect(host.textContent).toMatch(/kaboom/);
    expect(button(/Reload/)).toBeTruthy();
  });
});
