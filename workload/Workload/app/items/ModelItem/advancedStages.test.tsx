// @vitest-environment jsdom
// AA1: Advanced analytics in three stages under the Data Science card. The notebooks are advanced_stages.py's templates
// filled here; advancedStages.fixture.json is the Python's answer on the shop sample and the SAP full demo, so this file
// and the Python give the same cells. The shop sample (60 orders) says once that it has too few rows for a model.
import React from "react";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CASES from "./advancedStages.fixture.json";
import REVIEW_FIXTURE from "./w13Review.fixture.json";
import { ReviewFile } from "./ModelItemDefinition";
import { advancedStages, customerLink, fill, literal } from "./advancedStages";
import { nextSteps } from "./nextSteps";
import { AdvancedAnalytics, StarterContext } from "./NextStepsView";
import { RunContext } from "./RunNowView";

type Case = { grain: never; source: { name: string; schema: string }; links: never[]; expected: { analyses: unknown[]; values: unknown; experiment: string } };

describe("the same notebooks as the Python", () => {
  for (const c of CASES as unknown as Case[]) {
    it(`${c.source.name}: every analysis, stage and cell equals advanced_stages.stages()`, () => {
      const got = advancedStages(c.grain, c.source, c.links);
      expect(got.values).toEqual(c.expected.values);
      expect(got.experiment).toBe(c.expected.experiment);
      expect(JSON.parse(JSON.stringify(got.analyses))).toEqual(c.expected.analyses);
    });
  }
  it("fills a literal the way Python writes it", () => {
    expect(literal(null)).toBe("None");
    expect(literal(true)).toBe("True");
    expect(literal(["a", "b"])).toBe('["a", "b"]');
    expect(fill("x = {{v}}  # [[v]]", { v: "orders" })).toBe('x = "orders"  # orders');
  });
  it("picks the proven link to a customer table, without the client column", () => {
    expect(customerLink({ parent: "VBRK" }, [{ source: "VBRK", columns: ["MANDT", "KUNAG"], target: "KNA1", target_columns: ["MANDT", "KUNNR"] }]))
      .toEqual({ table: "KNA1", column: "KUNAG", key: "MANDT_KUNNR_key", parts: ["MANDT", "KUNAG"] });
    expect(customerLink({ parent: "orders" }, [{ source: "orders", columns: ["ship_to_id"], target: "addresses" }])).toBeNull();
  });
});

describe("the rules", () => {
  const sap = (CASES as unknown as Case[])[1];
  const plan = advancedStages(sap.grain, sap.source, sap.links);
  it("on the SAP full demo: forecast, segments and drivers, the first two with three stages and drivers with two", () => {
    expect(plan.analyses.map((a) => [a.analysis, a.stages.map((s) => s.stage)])).toEqual([
      ["forecast", ["features", "model", "predictions"]],
      ["segments", ["features", "model", "predictions"]],
      ["drivers", ["features", "model"]],
    ]);
    expect(plan.analyses.every((a) => !a.too_few)).toBe(true);
    expect(plan.analyses.find((a) => a.analysis === "segments")!.gold_table).toBe("gold.customer_segment");
    expect(plan.analyses.find((a) => a.analysis === "forecast")!.gold_table).toBe("gold.vbrk_forecast");
  });
  it("trains through MLflow and scores through PREDICT, with the version and run id written", () => {
    const seg = plan.analyses.find((a) => a.analysis === "segments")!;
    const model = seg.stages[1].cells!.join("\n");
    const pred = seg.stages[2].cells!.join("\n");
    expect(model).toContain("mlflow.autolog(exclusive=False)");
    expect(model).toContain("registered_model_name=P[\"model_name\"]");
    expect(pred).toContain("from synapse.ml.predict import MLFlowTransformer");
    expect(pred).toContain("model_version=MODEL_VERSION, run_id=RUN_ID");
    expect(pred).toContain("check_grain(pdf, P[\"order_key\"])");
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

describe("in the editor: ED3's Advanced analytics section on the Data product step", () => {
  const REVIEW = REVIEW_FIXTURE.review as unknown as ReviewFile;
  const SOURCE = { displayName: "shop_lh", schema: "shop", itemType: "Lakehouse" };

  it("the shop sample: each analysis shows Feature table, Model, Predictions in gold, and too few rows is said once", () => {
    const step = nextSteps({ review: REVIEW, created: [], source: SOURCE }).steps.find((s) => s.id === "ds-features")!;
    expect(step.advanced!.analyses.map((a) => a.analysis)).toEqual(["forecast", "segments", "drivers"]);
    act(() => root.render(<AdvancedAnalytics review={REVIEW} source={SOURCE} created={[]} />));
    const section = host.querySelector("#kg-advanced-analytics .kg-adv")!;
    expect(section).not.toBeNull();
    const forecast = section.querySelector('[data-stages="forecast"]')!;
    expect(Array.from(forecast.querySelectorAll(".kg-adv-stage strong")).map((e) => e.textContent)).toEqual(
      ["1. Feature table", "2. Model", "3. Predictions in gold"]);
    expect((section.textContent ?? "").split("Too few rows for a model").length - 1).toBe(1);
    expect(section.textContent).toContain("The feature table is still useful");
    expect(forecast.querySelectorAll('[data-stage="model"] button, [data-stage="predictions"] button').length).toBe(0);   // waits
    expect(forecast.textContent).toContain("Waits for more rows.");
    expect(section.querySelectorAll('[data-stages="drivers"] [data-stage="model"] button').length).toBeGreaterThan(0);  // no model needed
    expect(section.textContent).toContain("About ML experiments");
  });

  it("with enough rows: Dry run then Create a model notebook as ds_model; once created, Open in Fabric and Run now", async () => {
    const big = JSON.parse(JSON.stringify(REVIEW)) as ReviewFile;
    for (const it of big.items) {
      if (it.type === "key" && it.check?.result) it.check.result = { ...it.check.result, rows: Number(it.check.result.rows) * 10, distinct: Number(it.check.result.distinct ?? it.check.result.rows) * 10 };
    }
    const created = { type: "Notebook", id: "nb-7", name: "shop_lh_orders_forecast_model", workspace: "ws-1", output: "ds_model", attached: "lh-1" };
    const run = vi.fn(async (o: { name: string; dryRun: boolean; output?: string }) => (o.dryRun
      ? { would: "create" as const, name: o.name, confirm: "starter-2", words: `Would create the notebook ${o.name}.` }
      : { would: "created" as const, name: o.name, confirm: "starter-2", words: `Created the notebook ${o.name}.`, created }));
    act(() => root.render(
      <StarterContext.Provider value={{ run }}>
        <AdvancedAnalytics review={big} source={SOURCE} created={[]} />
      </StarterContext.Provider>));
    const stage = () => host.querySelector('[data-stages="forecast"] [data-stage="model"]')!;
    expect(host.querySelector(".kg-adv")!.textContent).not.toContain("Too few rows");
    const dry = Array.from(stage().querySelectorAll("button")).find((b) => b.textContent === "Dry run")!;
    await act(async () => dry.click());
    expect(run).toHaveBeenCalledWith(expect.objectContaining({ name: "shop_lh_orders_forecast_model", dryRun: true, output: "ds_model" }));
    const create = Array.from(stage().querySelectorAll("button")).find((b) => b.textContent === "Create shop_lh_orders_forecast_model")!;
    await act(async () => create.click());
    expect(run).toHaveBeenLastCalledWith(expect.objectContaining({ dryRun: false, confirm: "starter-2", output: "ds_model" }));
    const runNow = vi.fn();
    act(() => root.render(
      <RunContext.Provider value={{ run: runNow } as never}>
        <AdvancedAnalytics review={big} source={SOURCE} created={[created]} />
      </RunContext.Provider>));
    expect(stage().querySelector("[data-open-in-fabric]")?.getAttribute("href")).toContain("/groups/ws-1/");
    expect(Array.from(stage().querySelectorAll("button")).some((b) => /Run now/.test(b.textContent ?? ""))).toBe(true);
    expect(host.querySelector(".kg-adv")!.textContent).toContain("Open the experiment (in the workspace)");
  });
});
