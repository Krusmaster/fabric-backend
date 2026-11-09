// n174: the data flow in the Model editor. flow.fixture.json is what fabric_backend/data_flow.py sends for seed.py's shop
// schema (workload/scripts/build_flow_fixture.py; tests/test_workload_build.py fails when it is stale and checks each
// node's code against the dry run). Here: the layout places every node and edge, and the boxes' code stays folded until
// a box is opened, then shows exactly the engine's code.
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DataFlow } from "./engineClient";
import { BOX_W, boxLabel, layoutFlow, toggleOpen, togglesOn } from "./dataFlow";
import { FlowView } from "./FlowView";
import fixture from "./flow.fixture.json";

const FLOW = fixture as unknown as DataFlow;

function unescape(s: string): string {
  return s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#x27;/g, "'").replace(/&#39;/g, "'").replace(/&amp;/g, "&");
}

describe("the layout", () => {
  const lay = layoutFlow(FLOW);

  it("places every node of the engine's flow once, bronze to the left of silver, silver of gold", () => {
    expect(lay.boxes.map((b) => b.node.id).sort()).toEqual(FLOW.nodes.map((n) => n.id).sort());
    const x = (col: string) => lay.columns.find((c) => c.id === col)?.x;
    expect(x("bronze")).toBeLessThan(x("silver"));
    expect(x("silver")).toBeLessThan(x("gold"));
    expect(x("gold")).toBeLessThan(x("built"));
    for (const b of lay.boxes) expect(b.w).toBe(BOX_W);
  });

  it("draws one path per edge of the engine's flow, dashed where the build does not make it", () => {
    expect(lay.paths.map((p) => `${p.edge.from}>${p.edge.to}`)).toEqual(FLOW.edges.map((e) => `${e.from}>${e.to}`));
    for (const p of lay.paths) expect(p.dashed).toBe(!p.edge.built);
  });

  it("puts the pipeline's steps under the columns they run, in a row below", () => {
    const steps = lay.boxes.filter((b) => b.node.column === "pipeline");
    expect(steps.map((s) => s.node.notebook)).toEqual(["shop_silver", "shop_gold", "shop_flow_check"]);
    const lowest = Math.max(...lay.boxes.filter((b) => b.node.column !== "pipeline").map((b) => b.y + b.h));
    for (const s of steps) expect(s.y).toBeGreaterThan(lowest);
    expect(steps[0].x).toBe(lay.columns.find((c) => c.id === "silver")?.x);
    expect(lay.pipelineTitle?.text).toBe("Pipeline shop_flow");
  });

  it("leaves out a column the engine has nothing for (no gold without schemas)", () => {
    const noGold: DataFlow = { ...FLOW, nodes: FLOW.nodes.filter((n) => n.column !== "gold" && n.column !== "pipeline"), pipeline: null,
      edges: FLOW.edges.filter((e) => !e.to.startsWith("gold:") && !e.from.startsWith("pipeline:")) };
    expect(layoutFlow(noGold).columns.map((c) => c.id)).toEqual(["bronze", "silver", "built"]);
  });

  it("marks what is not part of the build", () => {
    const onlyGold = { ...FLOW, nodes: FLOW.nodes.map((n) => (n.column === "silver" ? { ...n, built: false } : n)) };
    const silver = onlyGold.nodes.find((n) => n.column === "silver");
    expect(boxLabel(silver, false)).toContain("not part of this build");
    expect(boxLabel(silver, false)).toContain("press Enter to show its code");
  });
});

describe("the boxes' code", () => {
  it("is folded by default: every box with code is a collapsed button, and no code is shown", () => {
    const html = renderToStaticMarkup(React.createElement(FlowView, { flow: FLOW, mascotsOn: false }));
    const withCode = FLOW.nodes.filter((n) => n.code).length;
    expect((html.match(/role="button"/g) ?? []).length).toBe(withCode);
    expect((html.match(/aria-expanded="false"/g) ?? []).length).toBe(withCode);
    expect(html).not.toContain('aria-expanded="true"');
    expect(html).not.toContain("<pre");
    expect(html).toMatch(/id="kg-flow-code"[^>]*hidden=""/);
  });

  it.each(["silver:orders", "gold:gold.orders", "pipeline:1", "item:semantic_model"])("opened, %s shows exactly the engine's code", (id) => {
    const node = FLOW.nodes.find((n) => n.id === id);
    const html = renderToStaticMarkup(React.createElement(FlowView, { flow: FLOW, mascotsOn: false, initialOpen: id }));
    const code = unescape(html.match(/<pre[^>]*><code>([\s\S]*?)<\/code><\/pre>/)[1]);
    expect(code).toBe(node.code);
    expect((html.match(/aria-expanded="true"/g) ?? []).length).toBe(1);
    expect(html).toContain(">Copy<");
    expect(html).toContain('aria-controls="kg-flow-code"');
  });

  it("a silver box's code is its notebook cell, a gold box's its CREATE, a step's its activity, the model's its TMDL", () => {
    const by = (col: string) => FLOW.nodes.find((n) => n.column === col);
    expect(by("silver").code.startsWith("# ---- ")).toBe(true);
    expect(by("gold").code).toContain("CREATE OR REPLACE MATERIALIZED LAKE VIEW");
    expect(JSON.parse(by("pipeline").code).type).toBe("TridentNotebook");
    expect(by("built").code.startsWith("// definition/relationships.tmdl")).toBe(true);
    expect(FLOW.nodes.filter((n) => n.column === "bronze").every((n) => n.code === null)).toBe(true);
  });

  it("Enter and Space toggle a box, one open at a time", () => {
    expect(togglesOn("Enter")).toBe(true);
    expect(togglesOn(" ")).toBe(true);
    expect(togglesOn("a")).toBe(false);
    expect(toggleOpen(undefined, "a")).toBe("a");
    expect(toggleOpen("a", "b")).toBe("b");
    expect(toggleOpen("b", "b")).toBeUndefined();
  });

  it("Builder presents the flow with the engine's sentence", () => {
    const html = renderToStaticMarkup(React.createElement(FlowView, { flow: FLOW }));
    expect(html).toContain('data-mascot="builder"');
    expect(html).toContain(FLOW.said.slice(0, 40));
  });
});
