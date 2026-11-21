// W13: next steps with other Fabric workloads (nextSteps.ts, NextStepsView.tsx), the step indicator (flowSteps.ts) and
// the proof shown after the check. The review is the engine's own answer on the synthetic shop schema
// (w13Review.fixture.json: /review then /check on tests/golden_support.py's doubles).
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import FIXTURE from "./w13Review.fixture.json";
import { ReviewFile } from "./ModelItemDefinition";
import { KINDS } from "./buildWords";
import { builtKinds, featureCells, grainLine, nextSteps, proofLine, proofOf, toIpynb } from "./nextSteps";
import { NextStepsPanel, ProofStrip } from "./NextStepsView";
import { FIRST_LINE, flowSteps, stepLine } from "./stepWords";
import { FlowSteps } from "./FlowSteps";

const REVIEW = FIXTURE.review as unknown as ReviewFile;
const SOURCE = { displayName: "demo_lh", schema: "shop", itemType: "Lakehouse" };
const unchecked = (): ReviewFile => ({ ...REVIEW, items: REVIEW.items.map((it) => ({ ...it, check: undefined as ReviewFile["items"][number]["check"] })) });

describe("W13: what the check proved", () => {
  it("counts rows, keys, links, orphans and duplicates from the review alone", () => {
    const p = proofOf(REVIEW);
    expect(p).toMatchObject({ keysPassed: 6, keysChecked: 6, linksPassed: 7, linksChecked: 7, rows: 232, tables: 6, orphans: 0, duplicates: 0 });
    expect(proofLine(p)).toBe("Proven on the rows (checked 2026-11-17 00:40 UTC): 6 of 6 keys unique, 7 of 7 links holding, 232 rows counted in 6 tables, 0 orphans, 0 duplicate keys.");
  });

  it("finds the grain a sum would double: order lines over orders first (lines of a header), 134 over 60 is 2.2×", () => {
    const g = proofOf(REVIEW).grains[0];
    expect(g).toMatchObject({ child: "order_items", parent: "orders", childColumns: ["order_id"], childRows: 134, parentRows: 60, ratio: 2.2, lines: true });
    expect(grainLine(g)).toBe("134 order_items rows over 60 orders rows: an amount on orders summed over order_items would count each orders row 2.2× on average. Sum order_items per orders row first.");
  });

  it("leaves out a rejected link and a failed key", () => {
    const r: ReviewFile = { ...REVIEW, items: REVIEW.items.map((it) => it.id === "rel:order_items.order_id>orders" ? { ...it, review: "rejected" } : it) };
    expect(proofOf(r).grains.map((g) => `${g.child}>${g.parent}`)).not.toContain("order_items>orders");
    const f: ReviewFile = { ...REVIEW, items: REVIEW.items.map((it) => it.id === "key:orders" ? { ...it, check: { status: "failed", result: { rows: 60, nulls: 0, distinct: 58 } } } : it) };
    expect(proofOf(f).duplicates).toBe(2);
    expect(proofOf(f).grains.some((g) => g.parent === "orders")).toBe(false);
  });

  it("shows tiles and Onto's sentence, and nothing before a check", () => {
    const html = renderToStaticMarkup(<ProofStrip review={REVIEW} />);
    for (const t of ["232", "rows counted", "6 of 6", "keys unique", "7 of 7", "links holding", "orphans", "duplicate keys", "2.2×"]) expect(html).toContain(t);
    expect(renderToStaticMarkup(<ProofStrip review={unchecked()} />)).toBe("");
  });
});

describe("W13: next steps with other Fabric workloads", () => {
  it("suggests nothing before the check has proven a key", () => {
    const n = nextSteps({ review: unchecked(), created: [], source: SOURCE });
    expect(n.steps).toEqual([]);
    expect(n.waiting).toContain("Check against the rows first");
  });

  it("suggests each workload once, in order, with one line of why, and only what Krusgraph can do or hand over", () => {
    const n = nextSteps({ review: REVIEW, created: [], source: SOURCE });
    expect(n.steps.map((s) => `${s.workload}: ${s.status}`)).toEqual([
      "Data Science: starter", "Power BI: builds", "Data agent: builds", "Data Factory: builds", "Data Engineering: builds",
      "Fabric IQ: builds", "Apps: builds",
    ]);   // SM3: the drift monitor (a typed request for Claude) is hidden until it has a Dry run here
    const kinds = new Set(KINDS.map((k) => k.kind));
    for (const s of n.steps) {
      expect(s.why.length).toBeGreaterThan(20);
      expect(s.why).not.toContain("\n");
      if (s.how.kind === "build") for (const o of s.how.outputs) expect(kinds.has(o)).toBe(true);   // only outputs the editor builds
    }
    expect(n.steps[0].why).toBe("Your order_items → orders link is proven (134 rows, 0 orphans), so this notebook sums order_items per orders row first: one row per orders row, no total counted 2.2×.");
  });

  it("does not suggest again what this item built, and a report alone once the model exists", () => {
    const created = [
      { type: "SemanticModel", output: "semantic_model", name: "demo_lh_model" },
      { type: "DataAgent", output: "data_agent", name: "demo_lh_agent" },
      { type: "GraphQLApi", name: "demo_lh_api" },   // phase 1's API, no output recorded
    ];
    expect([...builtKinds(created)].sort()).toEqual(["data_agent", "graphql", "semantic_model"]);
    const n = nextSteps({ review: REVIEW, created, source: SOURCE });
    const pbi = n.steps.find((s) => s.id === "pbi");
    expect(pbi?.how).toMatchObject({ kind: "build", outputs: ["report"] });
    expect(n.steps.map((s) => s.id)).not.toContain("agent");
    expect(n.steps.map((s) => s.id)).not.toContain("api");
  });

  it("offers no pipeline or drift monitor for a source that is not a lakehouse", () => {
    const n = nextSteps({ review: REVIEW, created: [], source: { ...SOURCE, itemType: "Warehouse" } });
    expect(n.steps.map((s) => s.id)).not.toContain("factory");
    expect(n.steps.map((s) => s.id)).not.toContain("drift");
  });

  it("SM3: hands nothing over as a request to copy for Claude (the drift monitor is hidden until it has a Dry run)", () => {
    const all = [nextSteps({ review: REVIEW, created: [], source: SOURCE }),
      nextSteps({ review: REVIEW, created: [{ type: "SemanticModel", output: "semantic_model", name: "m" }], source: SOURCE })];
    for (const n of all) {
      expect(n.steps.map((s) => s.id)).not.toContain("drift");
      for (const s of n.steps) {
        expect(s.how.kind).not.toBe("ask");
        expect(`${s.note ?? ""} ${s.why}`).not.toMatch(/Ask Krusgraph in Claude|Copy the request/);
      }
    }
  });
});

describe("W13: the Data Science starter", () => {
  const g = proofOf(REVIEW).grains[0];
  const cells = featureCells(g, { name: "demo_lh", schema: "shop", checkedAt: "2026-11-17T00:40Z" });

  it("sums the lines per order before the join, checks the grain before it writes, and makes an Experiment", () => {
    const code = cells.join("\n");
    expect(code).toContain('spark.read.table("`shop`.`orders`")');
    expect(code).toContain('spark.read.table("`shop`.`order_items`")');
    expect(code.indexOf("groupBy")).toBeLessThan(code.indexOf("parent.join"));
    expect(code.indexOf("assert n_features == n_parent")).toBeLessThan(code.indexOf("saveAsTable"));
    expect(code).toContain('saveAsTable("orders_features")');
    expect(code).toContain('mlflow.set_experiment("orders_experiment")');
    expect(code).toContain("134 order_items rows over 60 orders rows");
    expect(code).not.toMatch(/openai|anthropic|llm|gpt/i);
    expect(code).toMatch(/skip = set\("order_id,line_no,product_id"\.split/);   // ids are never summed (found on local Spark)
  });

  it("is a notebook Fabric imports: nbformat 4, one code cell each, the PySpark kernel", () => {
    const nb = JSON.parse(toIpynb(cells));
    expect(nb.nbformat).toBe(4);
    expect(nb.metadata.kernelspec.name).toBe("synapse_pyspark");
    expect(nb.cells).toHaveLength(4);
    expect(nb.cells.every((c: { cell_type: string }) => c.cell_type === "code")).toBe(true);
    expect(nb.cells[1].source.join("")).toBe(cells[1]);
  });

  it("is real Python: every line is ASCII and no line ends in a stray continuation", () => {
    for (const c of cells) {
      expect(c).toMatch(/^[\x20-\x7E\n]*$/);
      expect(c).not.toMatch(/\\\n/);
    }
  });
});

describe("W13: the panel", () => {
  it("renders the proof, the cards with their status words and one button each, as a named section", () => {
    const html = renderToStaticMarkup(<NextStepsPanel review={REVIEW} created={[]} source={SOURCE} onBuild={() => undefined} />);
    expect(html).toContain('aria-labelledby="kg-next-title"');
    expect(html).toContain("Next, with other Fabric workloads");
    expect(html).toContain("Suggestions by rules from what was proven; no AI.");
    for (const w of ["Krusgraph builds it", "Starter to download"]) expect(html).toContain(w);
    expect(html).not.toContain("Copy the request for Claude");
    expect(html).toContain('data-file="orders_features.ipynb"');   // WB10: offered through fileOffer.tsx
    expect(html).toContain("Download notebook (.ipynb)");
    expect((html.match(/class="kg-next-card"/g) ?? []).length).toBe(7);
  });

  it("says what to do first when nothing is proven yet", () => {
    const html = renderToStaticMarkup(<NextStepsPanel review={unchecked()} created={[]} source={SOURCE} onBuild={() => undefined} />);
    expect(html).toContain("Check against the rows first");
    expect(html).not.toContain("kg-next-card");
  });
});

describe("W13: where you are", () => {
  it("marks the step now, the steps done and ahead, and which can be gone back to", () => {
    const s = flowSteps("outputs", { review: true, preview: false, built: false });
    expect(s.map((x) => `${x.label}:${x.state}:${x.canGo}`)).toEqual([
      "Your data:done:true", "Check:done:true", "Decide:now:false", "Dry run:ahead:false", "Create:ahead:false",
    ]);
    expect(stepLine(s)).toBe("Step 3 of 5 · Decide · Next: Dry run");   // SM3: the chat's five steps and words
    expect(stepLine(flowSteps("product", { review: true, preview: true, built: true }))).toBe("Step 5 of 5 · Create");
  });

  it("is a navigation landmark with aria-current on the step now", () => {
    const html = renderToStaticMarkup(<FlowSteps steps={flowSteps("review", { review: true, preview: false, built: false })} onGo={() => undefined} />);
    expect(html).toContain('<nav class="kg-steps" aria-label="Where you are">');
    expect(html).toMatch(/<li class="kg-step kg-step-now" aria-current="step">.*Check/);
    expect((html.match(/aria-current/g) ?? []).length).toBe(1);
  });

  it("starts with one sentence in the mascots' voice", () => {
    expect(FIRST_LINE.split(/[.!?]\s/).length).toBe(1);
    expect(FIRST_LINE.length).toBeLessThan(120);
  });
});
