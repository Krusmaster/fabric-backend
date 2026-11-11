// n221, item 1: where the Krusgraph Model builds. The founder's live test of 11 November 2026: a new Model item in the
// workspace demo_Sandvik read demo_lh of the workspace demo and the dry run linked to demo_lh_silver ... in demo.
import { describe, expect, it } from "vitest";
import {
  buildInLine,
  buildWorkspace,
  crossWorkspace,
  defaultLakehouseName,
  keptTarget,
  lakehouseProblem,
  productWorkspace,
  targetRequest,
} from "./buildPlace";
import { previewLine } from "./buildWords";
import type { SourceDefinition } from "./ModelItemDefinition";

const DEMO = "11111111-1111-1111-1111-111111111111";      // the source's workspace (demo)
const SANDVIK = "22222222-2222-2222-2222-222222222222";   // the Model item's own, new workspace (demo_Sandvik)
const LH = "33333333-3333-3333-3333-333333333333";

const source = (patch: Partial<SourceDefinition> = {}): SourceDefinition => ({
  version: 1, platform: "fabric", workspaceId: DEMO, itemId: LH, itemType: "Lakehouse", displayName: "demo_lh", schema: "dbo", ...patch,
});

describe("Build in", () => {
  it("builds in the item's own workspace by default, not the source's", () => {
    expect(buildWorkspace(source(), SANDVIK)).toBe(SANDVIK);
    expect(crossWorkspace(source(), SANDVIK)).toBe(true);
    expect(targetRequest(source(), SANDVIK)).toEqual({ lakehouse: null, workspace: SANDVIK, where: "item" });
    expect(buildInLine(source(), SANDVIK)).toContain("built in this item's workspace, so it gets its own data product");
  });

  it("builds beside the source when the person chooses the source's workspace", () => {
    const s = source({ buildIn: "source" });
    expect(buildWorkspace(s, SANDVIK)).toBe(DEMO);
    expect(crossWorkspace(s, SANDVIK)).toBe(false);
    expect(targetRequest(s, SANDVIK)).toEqual({ lakehouse: null, workspace: DEMO, where: "source" });
  });

  it("an item in the source's own workspace builds there as before", () => {
    expect(crossWorkspace(source(), DEMO)).toBe(false);
    expect(buildInLine(source(), DEMO)).toContain("also demo_lh's");
  });

  it("sends Make a lakehouse only when ticked and no lakehouse is chosen in the build's workspace", () => {
    const name = defaultLakehouseName("demo_lh");
    expect(name).toBe("demo_lh_krusgraph");
    expect(targetRequest(source({ createLakehouse: name }), SANDVIK)).toEqual(
      { lakehouse: null, workspace: SANDVIK, where: "item", create_lakehouse: "demo_lh_krusgraph" });
    const chosen = source({ createLakehouse: name, target: { itemId: "lh-s", displayName: "sandvik_lh", workspaceId: SANDVIK } });
    expect(targetRequest(chosen, SANDVIK)).toEqual({ lakehouse: "lh-s", workspace: SANDVIK, where: "item" });
    expect(targetRequest(source({ createLakehouse: "1 bad" }), SANDVIK).create_lakehouse).toBeUndefined();
  });

  it("a lakehouse chosen in another workspace is not sent: it counts only where it was chosen", () => {
    const s = source({ target: { itemId: "lh-demo", displayName: "other", workspaceId: DEMO } });
    expect(targetRequest(s, SANDVIK).lakehouse).toBeNull();
    expect(targetRequest({ ...s, buildIn: "source" }, SANDVIK).lakehouse).toBe("lh-demo");
    expect(lakehouseProblem(SANDVIK, { workspaceId: DEMO, type: "Lakehouse" })).toContain("workspace the outputs are built in");
    expect(lakehouseProblem(SANDVIK, { workspaceId: SANDVIK, type: "Lakehouse" })).toBeUndefined();
  });

  it("the data product's workspace is where its items were built, else where it builds", () => {
    expect(productWorkspace(source(), [], SANDVIK)).toBe(SANDVIK);
    expect(productWorkspace(source(), [{ type: "Notebook", id: "n", name: "x", workspace: DEMO }], SANDVIK)).toBe(DEMO);
  });

  it("keeps the lakehouse Create wrote to, never the dry run's planned one", () => {
    expect(keptTarget({ lakehouse: "demo_lh_krusgraph", id: "<the lakehouse Create makes first>" }, SANDVIK)).toBeUndefined();
    expect(keptTarget({ lakehouse: "demo_lh_krusgraph", id: LH, workspace_id: SANDVIK }, SANDVIK)).toEqual(
      { itemId: LH, displayName: "demo_lh_krusgraph", workspaceId: SANDVIK });
  });

  it("the dry run's first line names the workspace the outputs are built in", () => {
    const a = {
      dry_run: true, outputs: [{ output: "silver_notebook", would: "create" }], refused: 0, order: [] as string[], left_out_by_review: [] as unknown[],
      build_in: { workspace_id: SANDVIK, name: "demo_Sandvik", where: "item", cross: true,
        words: "Builds in the workspace demo_Sandvik (this item's workspace; the source demo_lh is read from its own workspace)." },
    };
    expect(previewLine(a as never)).toBe(
      "Builds in the workspace demo_Sandvik (this item's workspace; the source demo_lh is read from its own workspace). " +
      "This is the dry run: nothing is written yet. Create makes 1 of 1. Nothing is run or scheduled.");
  });
});
