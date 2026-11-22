// @vitest-environment jsdom
// WB10 (Gustav's live test in Fabric, 18 Nov 2026): the Data product page's pipeline line when no pipeline was built
// (#62), the Data Factory card when the silver notebook is built (#63), and the Data Science starter's Dry run then
// Create (#64). The review is the engine's own answer on the synthetic shop schema (w13Review.fixture.json).
import React from "react";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FIXTURE from "./w13Review.fixture.json";
import { ReviewFile } from "./ModelItemDefinition";
import { builtKinds, factoryTitle, nextSteps } from "./nextSteps";
import { NextStepsPanel, StarterContext } from "./NextStepsView";
import { NO_PIPELINE, lastRunWords } from "./productWords";

const REVIEW = FIXTURE.review as unknown as ReviewFile;
const SOURCE = { displayName: "shop_lh", schema: "shop", itemType: "Lakehouse" };
const silver = { type: "Notebook", id: "nb-1", name: "shop_lh_silver", workspace: "ws", output: "silver_notebook" };

describe("#62: the last pipeline run", () => {
  it("says no pipeline was built, and points to the Data Factory step", () => {
    expect(lastRunWords({ created: [silver], choices: [] } as never)).toBe(NO_PIPELINE);
    expect(NO_PIPELINE).toContain("Data Factory");
  });
  it("keeps 'none recorded' for a pipeline that has not run", () => {
    const pl = { type: "DataPipeline", id: "pl-1", name: "shop_lh_pipeline", workspace: "ws", output: "pipeline" };
    expect(lastRunWords({ created: [pl], choices: [] } as never)).toContain("Last pipeline run: none recorded");
  });
});

describe("#63: the Data Factory card says what is left", () => {
  it("with the silver notebook built: gold views and a pipeline, and only those are ticked", () => {
    const n = nextSteps({ review: REVIEW, created: [silver], source: SOURCE });
    const f = n.steps.find((s) => s.id === "factory")!;
    expect(f.title).toBe("Gold views and a pipeline; the silver notebook is built");
    expect(f.how).toMatchObject({ kind: "build", outputs: ["gold_views", "pipeline"] });
  });
  it("tells a silver notebook recorded without its output by its name", () => {
    expect(builtKinds([{ type: "Notebook", name: "shop_lh_silver" }]).has("silver_notebook")).toBe(true);
    expect(builtKinds([{ type: "Notebook", name: "shop_lh_gold" }]).has("gold_views")).toBe(true);
  });
  it("is gone when all three are built, and whole when none is", () => {
    const all = ["silver_notebook", "gold_views", "pipeline"].map((o) => ({ type: "x", name: o, output: o }));
    expect(nextSteps({ review: REVIEW, created: all, source: SOURCE }).steps.some((s) => s.id === "factory")).toBe(false);
    expect(factoryTitle(["silver_notebook", "gold_views", "pipeline"], [])).toBe("Silver notebook, gold views and a pipeline");
    expect(factoryTitle(["pipeline"], ["silver_notebook", "gold_views"])).toBe("A pipeline; the silver notebook and gold views are built");
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

describe("#64: the Data Science starter, created in the workspace", () => {
  it("offers Dry run next to Download and Copy, then Create with the dry run's confirm; Krusgraph trains no model", async () => {
    const created = { type: "Notebook", id: "nb-9", name: "shop_lh_orders_features", workspace: "ws", output: "ds_features" };
    const run = vi.fn(async ({ dryRun }: { dryRun: boolean; name: string; cells: string[]; confirm?: string | null }) => dryRun
      ? { would: "create" as const, name: "shop_lh_orders_features", confirm: "starter-1", words: "Would create the notebook shop_lh_orders_features … Krusgraph does not run it and trains no model." }
      : { would: "created" as const, name: "shop_lh_orders_features", confirm: "starter-1", words: "Created the notebook shop_lh_orders_features.", created });
    const onCreated = vi.fn();
    act(() => root.render(
      <StarterContext.Provider value={{ run, onCreated }}>
        <NextStepsPanel review={REVIEW} created={[]} source={SOURCE} onBuild={() => {}} />
      </StarterContext.Provider>));
    const card = host.querySelector("[data-step=ds-features]")!;
    expect(card.textContent).toContain("trains no model");
    const labels = Array.from(card.querySelectorAll("button, a")).map((b) => b.textContent);
    expect(labels).toEqual(expect.arrayContaining(["Dry run", "Copy the code"]));
    const dry = Array.from(card.querySelectorAll("button")).find((b) => b.textContent === "Dry run")!;
    await act(async () => { dry.click(); });
    expect(run).toHaveBeenCalledWith(expect.objectContaining({ name: "shop_lh_orders_features", dryRun: true, confirm: null }));
    expect(run.mock.calls[0][0].cells.length).toBe(4);
    expect(card.textContent).toContain("trains no model");
    const create = Array.from(card.querySelectorAll("button")).find((b) => b.textContent === "Create shop_lh_orders_features")!;
    await act(async () => { create.click(); });
    expect(run).toHaveBeenLastCalledWith(expect.objectContaining({ dryRun: false, confirm: "starter-1" }));
    expect(onCreated).toHaveBeenCalledWith(created);
  });

  it("says the notebook is in the workspace once it was created", () => {
    const n = nextSteps({ review: REVIEW, created: [{ type: "Notebook", name: "x", output: "ds_features" }], source: SOURCE });
    expect(n.steps.find((s) => s.id === "ds-features")!.note).toContain("The notebook is in this item's workspace");
  });
});
