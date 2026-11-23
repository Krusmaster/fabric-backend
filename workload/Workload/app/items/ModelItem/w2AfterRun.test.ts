// W2 (Gustav's Create of 23 November 2026: source demo_lh in one workspace, build into another, a new build lakehouse;
// five items, the pipeline's run succeeded in 5m41s). Synthetic names only; no Fabric client.
import { describe, expect, it } from "vitest";
import { getFrontendPath, hasExplicitPath, VERIFIED_PATHS_SOURCE } from "../../controller/NavigationController";
import { FABRIC_PORTAL, fabricItemUrl } from "./openInFabric";
import { itemsOf } from "./createRun";
import { ORDER, mergeCreated } from "./buildWords";
import { rowsOf } from "./productWords";
import { lastCreateOf } from "./createWords";
import { MAX_SELECT_TRIES, refreshOffer, selectTablesExtra, selectTablesOffer, tablesNotSelected } from "./afterRun";
import type { BuildCard, OutputKind, OutputRequest } from "./engineClient";
import type { OutputsDefinition } from "./ModelItemDefinition";

const WS = "11111111-1111-1111-1111-111111111111";
const ID = "22222222-2222-2222-2222-222222222222";

// Source: Gustav's workspace list, 23 Nov 2026 (the addresses he copied from the portal's item list)
const VERIFIED: Record<string, string> = {
  DataAgent: `/groups/${WS}/aiskills/${ID}`,
  Notebook: `/groups/${WS}/synapsenotebooks/${ID}`,
  SemanticModel: `/groups/${WS}/datasets/${ID}/details`,
  DataPipeline: `/groups/${WS}/pipelines/${ID}`,
  Lakehouse: `/groups/${WS}/lakehouses/${ID}`,
  SQLEndpoint: `/groups/${WS}/sqlanalyticsendpoints/${ID}`,
  "Org.Krusgraph.Model": `/groups/${WS}/Org.Krusgraph.Model/${ID}`,
};
// Kinds the editor can create that are not in that list, with where their address comes from
const OTHER_SOURCES: Record<string, string> = {
  Report: "the Power BI report path the engine has used since n169 (mcp_apps_build.ITEM_PATHS)",
  Ontology: "Learn, Use Ontology MCP Server (ms.date 2026-04-14)",
  GraphQLApi: "not verified (mcp_apps_build.LINK_UNVERIFIED)",
  AppBackend: "not verified: the App (preview) opens by the kit's fallback",
};

function creatableTypes(): string[] {
  const all: OutputRequest[] = ORDER.map((kind) => ({ kind, name: `x_${kind}` }) as OutputRequest);
  const types = new Set<string>(["Lakehouse"]);                 // Create makes the build lakehouse (ED2)
  for (const o of all) for (const it of itemsOf(o, all, "shop")) types.add(it.type);
  return [...types].sort();
}

describe("Open in Fabric: every item kind Krusgraph creates has its verified portal address", () => {
  it.each(Object.entries(VERIFIED))(`%s opens the address from ${VERIFIED_PATHS_SOURCE}`, (type, path) => {
    expect(VERIFIED_PATHS_SOURCE).toBe("Gustav's workspace list, 23 Nov 2026");
    expect(getFrontendPath(type, WS, ID)).toBe(path);
    expect(fabricItemUrl({ id: ID, workspaceId: WS, type })).toBe(FABRIC_PORTAL + path);
  });
  it("every kind the editor can create has an explicit path, verified or with its source named", () => {
    for (const type of creatableTypes()) {
      if (type === "AppBackend") continue;                      // the App (preview): no verified address yet; the kit's fallback
      expect(hasExplicitPath(type), type).toBe(true);
      expect(type in VERIFIED || type in OTHER_SOURCES, type).toBe(true);
    }
    expect(creatableTypes()).toEqual(expect.arrayContaining(["DataAgent", "DataPipeline", "Lakehouse", "Notebook", "SemanticModel"]));
  });
  it("the data agent no longer opens /dataagents/ (Fabric's 404 page)", () => {
    expect(fabricItemUrl({ id: ID, workspaceId: WS, type: "DataAgent" })).not.toContain("/dataagents/");
  });
});

// ------------------------------------------------------------------ issue 2: the data agent's tables ------------------

function agentCard(selected: number, missing: string[], extra: Partial<BuildCard> = {}): BuildCard {
  return {
    output: "data_agent", label: "Data agent", type: "DataAgent", name: "demo_agent", dry_run: false, would: "update",
    updates_in_place: true, permissions: { needs: [], missing: null, execute: "" },
    created: [{ type: "DataAgent", id: ID, name: "demo_agent", workspace: WS, output: "data_agent" }],
    agent: { layer: "silver", publish: false, copilot: false, where_examples: "",
      selection: { layer: "silver", schema: "silver", selected, deselected: 0, one_layer: false, words: "", total: 7, missing } },
    ...extra,
  } as BuildCard;
}

describe("Select tables now: after the run, bounded", () => {
  const seven = ["addresses", "audit_log", "categories", "customers", "order_items", "orders", "products"];
  it("0 of 7 selected after a succeeded run: offered, with the reason", () => {
    const o = selectTablesOffer(agentCard(0, seven), 0, { status: "Succeeded" });
    expect(o.offer).toBe(true);
    expect(o.line).toContain("7 tables not selected yet");
    expect(tablesNotSelected(agentCard(0, seven))).toBe(7);
  });
  it("all selected: nothing offered", () => {
    expect(selectTablesOffer(agentCard(7, []), 0, { status: "Succeeded" }).offer).toBe(false);
  });
  it("never more than MAX_SELECT_TRIES times; then the way in Fabric", () => {
    const o = selectTablesOffer(agentCard(0, seven), MAX_SELECT_TRIES, { status: "Succeeded" });
    expect(o.offer).toBe(false);
    expect(o.line).toContain("select the tables in the agent in Fabric");
  });
  it("while the run has not succeeded: no button, one line", () => {
    const o = selectTablesOffer(agentCard(0, seven), 0, { status: "Running" });
    expect(o.offer).toBe(false);
    expect(o.line).toContain("once the pipeline's run has succeeded");
  });
  it("a dry run or an agent on the source tables: nothing", () => {
    expect(selectTablesOffer(agentCard(0, seven, { dry_run: true }), 0).offer).toBe(false);
  });
  it("the request says select_tables and the run's end", () => {
    expect(selectTablesExtra({ status: "Succeeded" })).toEqual({ select_tables: true, after_run: { status: "Succeeded" } });
    expect(selectTablesExtra()).toEqual({ select_tables: true });
  });
  it("the stored finish keeps how many tables are left, for Next", () => {
    const lc = lastCreateOf([agentCard(0, seven)], "demo_model", "2026-11-23T12:00:00Z");
    expect(lc.outputs[0].tables_left).toBe(7);
  });
});

// ------------------------------------------------------------------ issue 3: the refresh waits for the run -------------

function modelCard(status: string): BuildCard {
  return {
    output: "semantic_model", label: "Semantic model", type: "SemanticModel", name: "demo_lh_model", dry_run: false, would: "create",
    updates_in_place: true, permissions: { needs: [], missing: null, execute: "" },
    created: [{ type: "SemanticModel", id: ID, name: "demo_lh_model", workspace: WS, output: "semantic_model" }],
    refresh: { status: status as never },
  } as BuildCard;
}

describe("Refresh now: only when the refresh failed or did not run, never while the run goes on", () => {
  it("failed after the run: Refresh now", () => {
    expect(refreshOffer(modelCard("failed"), { status: "Succeeded" }).offer).toBe(true);
  });
  it("planned while the run goes on: says it refreshes after the run, no button", () => {
    const o = refreshOffer(modelCard("planned"), { status: "Running" });
    expect(o.offer).toBe(false);
    expect(o.line).toBe("Refreshed after the pipeline's run has succeeded.");
  });
  it("refreshed: nothing", () => {
    expect(refreshOffer(modelCard("refreshed")).offer).toBe(false);
  });
  it("the stored finish knows a run was started, whatever its status reads", () => {
    const pipe = { ...modelCard("planned"), output: "pipeline" as OutputKind, label: "Pipeline", type: "DataPipeline", refresh: undefined,
      jobs: { run_once: true, schedule: null, permission: { granted: true }, run: { status: "Unknown", run_id: "r1" } } } as unknown as BuildCard;
    const lc = lastCreateOf([pipe], "demo_model", "2026-11-23T12:00:00Z");
    expect(lc.outputs[0]).toMatchObject({ run: "Unknown", run_started: true });
  });
});

// ------------------------------------------------------------------ issue 5: the gold notebook keeps its id ------------

describe("the gold notebook's id is kept under its own output", () => {
  const gold = { type: "Notebook", id: "nb-gold", name: "demo_lh_gold", workspace: WS };
  it("the pipeline's answer with the same notebook does not take it from the gold views output", () => {
    const after = mergeCreated([{ ...gold, output: "gold_views" }], [{ ...gold, output: "pipeline" }]);
    expect(after).toHaveLength(1);
    expect(after[0].output).toBe("gold_views");
  });
  it("an outputs.json written before W2 (the notebook under the pipeline) shows no 'no id saved' row", () => {
    const outputs = {
      version: 1, outputs: [], created: [{ ...gold, output: "pipeline" }],
      last_create: { at: "2026-11-23T12:00:00Z", item: "demo_model", outputs: [{ output: "gold_views", label: "Gold views", name: "demo_lh_gold", state: "created" }] },
    } as unknown as OutputsDefinition;
    const rows = rowsOf(outputs, undefined, undefined);
    expect(rows.some((r) => r.key.startsWith("unsaved:"))).toBe(false);
    const withPlan = rowsOf({ ...outputs, created: [{ ...gold, output: "pipeline", plan: { plan_id: "plan-1" } }] } as never, undefined, "plan-1");
    expect(withPlan.some((r) => r.key.startsWith("unsaved:"))).toBe(false);
  });
});
