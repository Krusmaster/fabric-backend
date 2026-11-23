// @vitest-environment jsdom
// W1 (23 November 2026): what Gustav found in the Model item in a real tenant, on the synthetic shop sample.
// 1. Choose a source: "_rsc (no tables)", a Fabric system schema, was a choice; Krusgraph's own schemas (silver, gold,
//    krusgraph, sap_silver, ...) sat among the source schemas. Now: system schemas left out, source schemas first,
//    Krusgraph's own labelled.
// 2. An empty lakehouse: "Schema 'dbo' has no tables in '<id>' (workspace <id>) ... list_tables ...". Now one plain
//    sentence, with the docs link kept.
// 3. Decide, "Suggested data products": the parts ran together ("products2 suggested", "ordersGrouped by",
//    "(domains.propose_plan).Suggestions") and showed developer words. Now each part on its own line, plain words.
// And the coordinator's additions from the dry run and the Create result page: the data agent card's lines, the BL54
// lines on the dry run, the Next list while a run goes on, the agent with no tables yet, and the Data Factory card.
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { BuildCard, ManyAnswer, SuggestedProduct, SuggestedProducts } from "./engineClient";
import {
  EMPTY_LAKEHOUSE, docsLink, editorError, everySchemaEmpty, isSystemSchema, krusgraphSchema, schemaOptions,
} from "./sourceWords";
import { ErrorBar, PreviewView, SchemaChoice } from "./ModelItemViews";
import { SuggestedProductsPanel } from "./SuggestedProductsView";
import { GROUPED_BY, noteLine, plainWords, productParts, unassignedLine } from "./productSuggestions";
import { AgentPanel } from "./JobsViews";
import { noTablesYet, portalSteps } from "./jobsWords";
import { nextSteps, LastCreate } from "./createWords";
import { builtKinds, factoryTitle, nextSteps as nextSteps2 } from "./nextSteps";
import { AdvancedAnalytics } from "./NextStepsView";
import { oneRowOf } from "./advancedStages";
import { NO_ID_SAVED, rowsOf } from "./productWords";
import type { OutputsDefinition, ReviewFile } from "./ModelItemDefinition";
import REVIEW_FIXTURE from "./w13Review.fixture.json";

const DOCS = "https://krusgraph.com/docs#first-time-errors";
/** The engine's answer for the review of an empty lakehouse (server._plan_read, errors._answer), with synthetic ids. */
const EMPTY_ERROR = {
  error: "Schema 'dbo' has no tables in '22222222-2222-2222-2222-222222222222' (workspace 11111111-1111-1111-1111-111111111111); it may not exist in this source.",
  kind: "schema_not_found",
  hint: "list_tables with another schema shows that schema's tables; a lakehouse's default schema is 'dbo' unless it was created with schemas. " +
    `Tables created minutes ago may not be in the SQL analytics endpoint yet: open the endpoint in Fabric and refresh its metadata. Step by step: ${DOCS}`,
};

/** The text of a rendered element, a newline after each block (what a person reads line by line). */
function lines(html: string): string[] {
  const doc = new DOMParser().parseFromString(`<div id="r">${html}</div>`, "text/html");
  const out: string[] = [];
  const blocks = new Set(["P", "H1", "H2", "H3", "LI", "DIV", "SECTION", "SUMMARY", "LABEL", "UL"]);
  let cur = "";
  const walk = (n: Node) => {
    if (n.nodeType === 3) { cur += n.textContent; return; }
    if (n.nodeName === "STYLE") return;
    const el = n as HTMLElement;
    const block = blocks.has(n.nodeName) || /display:\s*block/.test(el.getAttribute?.("style") ?? "") ||
      (el.className && /fui-Text/.test(String(el.className)) && /\b___\w+/.test(String(el.className)) && el.tagName !== "SPAN");
    if (block && cur.trim()) { out.push(cur.trim()); cur = ""; }
    n.childNodes.forEach(walk);
    if (block && cur.trim()) { out.push(cur.trim()); cur = ""; }
  };
  walk(doc.getElementById("r")!);
  if (cur.trim()) out.push(cur.trim());
  return out;
}

describe("W1 1: the schema list of Choose a source", () => {
  const LIST = {
    schemas: [
      { schema: "_rsc", tables: 0 }, { schema: "dbo", tables: 0 }, { schema: "gold", tables: 7 }, { schema: "krusgraph", tables: 2 },
      { schema: "queryinsights", tables: 4 }, { schema: "sap", tables: 18 }, { schema: "sap_gold", tables: 5 }, { schema: "sap_silver", tables: 18 },
      { schema: "shop", tables: 7 }, { schema: "silver", tables: 7 }, { schema: "sys", tables: 3 }, { schema: "krusgraph_quarantine", tables: 1 },
    ],
    preselect: null as string | null, note: "",
  };

  it("leaves out Fabric's and SQL's own schemas: names starting with _, sys, INFORMATION_SCHEMA, queryinsights", () => {
    for (const s of ["_rsc", "_anything", "sys", "SYS", "INFORMATION_SCHEMA", "queryinsights", "guest"]) expect(isSystemSchema(s)).toBe(true);
    for (const s of ["dbo", "shop", "sap", "silver", "sys_data", "rsc"]) expect(isSystemSchema(s)).toBe(false);
    expect(schemaOptions(LIST).map((o) => o.schema)).not.toContain("_rsc");
    expect(schemaOptions(LIST).map((o) => o.schema)).not.toContain("sys");
    expect(schemaOptions(LIST).map((o) => o.schema)).not.toContain("queryinsights");
  });

  it("tells Krusgraph's own schemas by the engine's naming: krusgraph* written, silver/gold and <name>_silver/_gold look so", () => {
    expect(krusgraphSchema("krusgraph")).toBe("written");
    expect(krusgraphSchema("krusgraph_quarantine")).toBe("written");
    expect(krusgraphSchema("krusgraph_analysis")).toBe("written");
    expect(krusgraphSchema("silver")).toBe("looks");
    expect(krusgraphSchema("GOLD")).toBe("looks");
    expect(krusgraphSchema("sap_silver")).toBe("looks");
    expect(krusgraphSchema("sap_gold")).toBe("looks");
    for (const s of ["dbo", "shop", "sap", "silverware", "golden", "silver_2025", "goldsmith", "krusgraphx"]) expect(krusgraphSchema(s)).toBeUndefined();
  });

  it("lists the source schemas first, then Krusgraph's own, each labelled, all still selectable", () => {
    const o = schemaOptions(LIST);
    expect(o.map((x) => x.schema)).toEqual(["dbo", "sap", "shop", "gold", "krusgraph", "sap_gold", "sap_silver", "silver", "krusgraph_quarantine"]);
    expect(o.map((x) => x.label)).toEqual([
      "dbo (no tables)", "sap (18 tables)", "shop (7 tables)",
      "gold (7 tables, looks like Krusgraph output)", "krusgraph (2 tables, written by Krusgraph)",
      "sap_gold (5 tables, looks like Krusgraph output)", "sap_silver (18 tables, looks like Krusgraph output)",
      "silver (7 tables, looks like Krusgraph output)", "krusgraph_quarantine (1 table, written by Krusgraph)",
    ]);
  });

  it("renders the list without _rsc, with the labels, and Krusgraph's own schemas enabled", () => {
    const html = renderToStaticMarkup(
      <SchemaChoice schema="shop" schemas={{ loading: false, list: LIST }} onSchemaChange={() => undefined} sourceName="demo_lh" />
    );
    expect(html).not.toContain("_rsc");
    expect(html).toContain("sap_silver (18 tables, looks like Krusgraph output)");
    expect(html).toContain("krusgraph (2 tables, written by Krusgraph)");
    const doc = new DOMParser().parseFromString(html, "text/html");
    const radios = Array.from(doc.querySelectorAll("input[type=radio]")) as HTMLInputElement[];
    expect(radios.map((r) => r.value)).toEqual(["dbo", "sap", "shop", "gold", "krusgraph", "sap_gold", "sap_silver", "silver", "krusgraph_quarantine"]);
    expect(radios.filter((r) => r.disabled).map((r) => r.value)).toEqual(["dbo"]);   // empty ones only
  });
});

describe("W1 2: a lakehouse with no tables", () => {
  const EMPTY = { schemas: [{ schema: "_rsc", tables: 0 }, { schema: "dbo", tables: 0 }], preselect: null as string | null, note: "0 of 2 schema(s) hold tables." };

  it("knows when every schema is empty (system schemas aside)", () => {
    expect(everySchemaEmpty(EMPTY)).toBe(true);
    expect(everySchemaEmpty({ schemas: [{ schema: "_rsc", tables: 3 }, { schema: "dbo", tables: 0 }] })).toBe(true);
    expect(everySchemaEmpty({ schemas: [{ schema: "dbo", tables: 1 }] })).toBe(false);
    expect(everySchemaEmpty(undefined)).toBe(false);                 // not read: nothing is claimed
  });

  it("before: dbo, raw ids and list_tables; after: one plain sentence and the docs link", () => {
    const e = editorError(EMPTY_ERROR, EMPTY)!;
    expect(e.error).toBe(EMPTY_LAKEHOUSE);
    expect(e.error).toBe("This lakehouse has no tables the SQL analytics endpoint can see. If you just loaded data, open the SQL analytics " +
      "endpoint and choose Refresh. Files under Files must be loaded to Tables first (right-click, Load to Tables).");
    expect(e.hint).toBe(`Step by step: ${DOCS}`);
    expect(`${e.error} ${e.hint}`).not.toMatch(/list_tables|1111|2222|'dbo'/);
    expect(docsLink(EMPTY_ERROR.hint)).toBe(DOCS);
  });

  it("a schema without tables beside others with tables: the schema named, editor words, no MCP tool name, the link kept", () => {
    const e = editorError(EMPTY_ERROR, { schemas: [{ schema: "dbo", tables: 0 }, { schema: "shop", tables: 7 }] })!;
    expect(e.error).toBe("The schema 'dbo' has no tables the SQL analytics endpoint can see.");
    expect(e.hint).toContain("Choose a schema with tables in the list.");
    expect(e.hint).toContain(DOCS);
    expect(`${e.error} ${e.hint}`).not.toMatch(/list_tables|1111|2222/);
  });

  it("leaves every other error as the engine said it", () => {
    const other = { error: "No access", kind: "no_access", hint: "Ask" };
    expect(editorError(other, EMPTY)).toBe(other);
    expect(editorError(undefined, EMPTY)).toBeUndefined();
  });

  it("the error bar shows the docs address as a link; the schema step shows the sentence instead of greyed schemas", () => {
    const bar = renderToStaticMarkup(<ErrorBar error={editorError(EMPTY_ERROR, EMPTY)} />);
    expect(bar).toContain(`href="${DOCS}"`);
    expect(bar).toContain("Load to Tables");
    const step = renderToStaticMarkup(<SchemaChoice schema="dbo" schemas={{ loading: false, list: EMPTY }} onSchemaChange={() => undefined} />);
    expect(step).toContain("This lakehouse has no tables the SQL analytics endpoint can see.");
    expect(step).not.toContain("_rsc");
    expect(step).not.toContain("type=\"radio\"");
    // the error bar already says it: not twice
    expect(renderToStaticMarkup(<SchemaChoice schema="dbo" schemas={{ loading: false, list: EMPTY }} onSchemaChange={() => undefined} emptyShown />)).toBe("");
  });
});

describe("W1 3: Suggested data products on the Decide step", () => {
  const P = (id: string, tables: string[], extra: Partial<SuggestedProduct> = {}): SuggestedProduct => ({
    id, name: id, tables, rule: "Tables joined by their keys and links, cut where the links are weakest (Leiden-style communities on the key graph, domain_draft's method); a table whose key holds its parent's key stays with that parent.",
    name_reason: "customers is the table the others point at", why: {}, interface: { provides: [], consumes: [] }, evidence: ["key customers.customer_id (K1; not checked against the rows)"], ...extra,
  });
  // the engine's answer as Gustav saw it (an engine from before W1: the method's name in rule and from)
  const S: SuggestedProducts = {
    products: [P("customers", ["addresses", "customers", "order_items", "orders"]), P("products", ["categories", "products"])],
    unassigned: [{ table: "audit_log", reason: "no key: nothing to group it by" }], checked: false,
    from: "domain_draft's proposal (domains.propose_plan)",
    note: "Suggestions, not decisions: tick the ones to build. Each becomes a data product over this Model's outputs; a Fabric domain itself needs a Fabric administrator.",
  };

  it("plain words: no method names, every sentence closed", () => {
    expect(plainWords(S.products[0].rule)).toBe(GROUPED_BY);
    expect(plainWords("from domain_draft's proposal (domains.propose_plan)")).toBe("from domain_draft's proposal.");
    expect(productParts(S.products[0])).toEqual({
      title: "customers: 4 tables",
      tables: "Tables: addresses, customers, order_items, orders.",
      grouped: `Grouped by: ${GROUPED_BY}`,
      named: "Named so because customers is the table the others point at.",
    });
    expect(unassignedLine(S)).toBe("Not in a suggestion: audit_log (no key: nothing to group it by).");
    expect(noteLine(S)).toBe(S.note);
  });

  it("each part on its own line: no 'products2', no 'ordersGrouped', no '.Suggestions', no developer words", () => {
    const html = renderToStaticMarkup(<SuggestedProductsPanel suggested={S} ticked={[]} onTicked={() => undefined} />);
    const got = lines(html);
    expect(got[0]).toBe("Suggested data products");
    expect(got[1]).toBe("2 suggested data products, from the keys and links you reviewed; check them against the rows to weigh each link by its rows.");
    expect(got).toContain("customers: 4 tables");
    expect(got).toContain("Tables: addresses, customers, order_items, orders.");
    expect(got).toContain(`Grouped by: ${GROUPED_BY}`);
    expect(got).toContain("Not in a suggestion: audit_log (no key: nothing to group it by).");
    expect(got[got.length - 1]).toBe(S.note);
    const text = got.join("\n");
    expect(text).not.toMatch(/products2|ordersGrouped|\)\.Suggestions|domain_draft|propose_plan|Leiden/);
    expect(html).toMatch(/<h3[^>]*>Suggested data products<\/h3>/);
    expect(html).toContain('class="krusgraph-suggested"');
  });

  it("the panel is as wide as the output cards above it (880 px), and so is the fold it sits in", async () => {
    const { readFileSync } = await import("fs");
    const { join } = await import("path");
    const scss = readFileSync(join(__dirname, "ModelItem.scss"), "utf8");
    const rule = (sel: string) => new RegExp(`\\n${sel.replace(".", "\\.")} \\{[^}]*max-width: 880px`).test(scss);
    expect(rule(".krusgraph-outputs")).toBe(true);
    expect(rule(".krusgraph-suggested")).toBe(true);
    expect(rule(".kg-more-outputs")).toBe(true);
  });
});

// ------------------------------------------------------------------ the coordinator's additions ---------------------

function agentCard(over: Partial<BuildCard> = {}, agent: Record<string, unknown> = {}): BuildCard {
  return {
    output: "data_agent", label: "Data agent", type: "DataAgent", name: "demo_lh_agent", dry_run: true, would: "create",
    agent: {
      layer: "silver", publish: false, copilot: false,
      layer_words: "The agent reads the silver tables in silver only (cleaned, keys and links held), when they are in the lakehouse; otherwise the source tables in shop. Never two layers at once.",
      where_examples: "Krusgraph's example questions are the agent's example queries (Example queries pane, per data source): Fabric uses them to answer.",
      ...agent,
    },
    ...over,
  } as unknown as BuildCard;
}

describe("W1 additions: the data agent card", () => {
  it("its sentences are separate lines ('Never two layers at once.Krusgraph's ...' ran together)", () => {
    const html = renderToStaticMarkup(<AgentPanel card={agentCard()} />);
    const got = lines(html);
    expect(got).toContain("The agent reads the silver tables in silver only (cleaned, keys and links held), when they are in the lakehouse; otherwise the source tables in shop. Never two layers at once.");
    expect(got.join("\n")).not.toMatch(/once\.Krusgraph/);
    expect(html).toContain('class="kg-stack"');
  });

  it("'selected 0 of 7 tables' after Create says plainly that the agent has no tables yet and what to do", () => {
    const made = agentCard({ dry_run: false } as Partial<BuildCard>, {
      selection: { layer: "silver", schema: "silver", selected: 0, deselected: 0, one_layer: false, words: "selected 0 of 7 tables in silver (silver)" },
      examples: { status: "not_checked", count: 4, words: "Example queries: not checked yet." },
    });
    const line = noTablesYet(made)!;
    expect(line).toContain("The agent has no tables selected yet");
    expect(line).toContain("open this item again after the run, or select the tables in silver in the agent in Fabric");
    const got = lines(renderToStaticMarkup(<AgentPanel card={made} />));
    expect(got.join("\n")).not.toMatch(/\(silver\)Example/);
    expect(got.join("\n")).toContain("The agent has no tables selected yet");
    expect(noTablesYet(agentCard())).toBeUndefined();                                   // a dry run selects nothing
    expect(noTablesYet(agentCard({ dry_run: false } as Partial<BuildCard>, { selection: { selected: 7, schema: "silver" } }))).toBeUndefined();
  });
});

describe("W1 additions: the dry run's BL54 lines", () => {
  it("shows the workspace roles and the data contract under the Builder's line, when the engine sends them", () => {
    const answer = {
      dry_run: true, outputs: [], order: [], refused: 0, to_decide: 0, left_out_by_review: [], note: "Nothing was created or changed in Fabric.",
      row_check: { checked: 0 },
      access: "Workspace roles proposed: data engineers Contributor, report readers Viewer, access managers Member. Labels read, never set. Nothing is written.",
      contract: "Data contract: an ODCS v3.1.0 draft from the counted checks comes with the data product. Nothing is written to Fabric.",
    } as unknown as ManyAnswer;
    const html = renderToStaticMarkup(<PreviewView answer={answer} onCreate={() => undefined} mascotsOn={false} createLabel="Create" />);
    const got = lines(html);
    const builder = got.findIndex((l) => l.startsWith("Workspace roles proposed"));
    expect(builder).toBeGreaterThan(0);
    expect(got[builder + 1]).toMatch(/^Data contract: an ODCS v3\.1\.0 draft/);
    expect(html).not.toContain("data_contract.draft");
    const without = renderToStaticMarkup(<PreviewView answer={{ ...answer, access: undefined, contract: undefined }} onCreate={() => undefined} mascotsOn={false} createLabel="Create" />);
    expect(without).not.toContain("data-bl54");
  });
});

describe("W1 additions: the Create result page", () => {
  const lc = (run?: string): LastCreate => ({
    at: "2026-11-23T10:00:00.000Z", item: "Model 1",
    outputs: [
      { output: "pipeline", label: "Pipeline", name: "demo_lh_pipeline", state: "created", ...(run ? { run } : {}) },
      { output: "semantic_model", label: "Semantic model", name: "demo_lh_model", state: "created", refresh: "not_run" },
      { output: "data_agent", label: "Data agent", name: "demo_lh_agent", state: "created" },
    ],
  });

  it("a run Create started is followed, not 'nothing has run yet', also before its first read (Unknown)", () => {
    for (const run of ["Running", "Unknown"]) {
      const n = nextSteps(lc(run));
      expect(n[0]).toMatch(/^Follow the run of demo_lh_pipeline in Fabric/);
      expect(n.join(" ")).not.toContain("nothing has run yet");
      expect(n).toContain("Refresh the semantic model demo_lh_model once in Fabric when the run has succeeded.");
      expect(n.join(" ")).toContain("When the run has succeeded, check the data agent demo_lh_agent");
    }
    expect(nextSteps(lc())[0]).toContain("nothing has run yet");                        // no run was started: as before
    expect(nextSteps(lc("NotStarted"))[0]).toBe("The run of demo_lh_pipeline did not start: see its card for why, then run it once in Fabric (Run).");
  });

  it("the pipeline card's Still to do drops 'Run the pipeline once' when Create started a run", () => {
    const steps = ["Run the pipeline once in Fabric (Run) to fill the silver tables and the gold views.", "No schedule: tick Schedule ..."];
    const pipe = { output: "pipeline", portal_steps: steps, jobs: { run: { run_id: "r-1", status: "Unknown" } } };
    expect(portalSteps(pipe)).toEqual(["No schedule: tick Schedule ..."]);
    expect(portalSteps({ ...pipe, jobs: { run: { run_id: "r-1", status: "Failed" } } })).toEqual(steps);
    expect(portalSteps({ ...pipe, jobs: {} })).toEqual(steps);
  });

  it("the Data Factory card knows the silver and gold notebooks the pipeline wrote (recorded with output pipeline)", () => {
    const created = [
      { type: "DataPipeline", output: "pipeline", name: "demo_lh_pipeline" },
      { type: "Notebook", output: "pipeline", name: "demo_lh_silver" },
      { type: "Notebook", output: "pipeline", name: "demo_lh_gold" },
      { type: "Notebook", output: "pipeline", name: "demo_lh_pipeline_check" },
    ];
    const built = builtKinds(created);
    expect([...built].sort()).toEqual(["gold_views", "pipeline", "silver_notebook"]);
    expect(builtKinds([{ type: "Notebook", output: "pipeline", name: "silver_shop" }]).has("silver_notebook")).toBe(true);
    // the title before W1 for this Create, kept for the case it describes (only the pipeline built)
    expect(factoryTitle(["silver_notebook", "gold_views"], ["pipeline"])).toBe("Silver notebook and gold views; the pipeline exists but has nothing to run until they are built");
  });
});

// ------------------------------------------------------------------ the Data product step (findings 7 to 10) --------

describe("W1 additions: the Data product step", () => {
  const REVIEW = REVIEW_FIXTURE.review as unknown as ReviewFile;
  const SOURCE = { displayName: "demo_lh", schema: "shop", itemType: "Lakehouse" };

  it("'Advanced analytics' is a heading of its own, and its sentences are paragraphs that wrap", () => {
    const html = renderToStaticMarkup(<AdvancedAnalytics review={REVIEW} source={SOURCE} created={[]} />);
    const got = lines(html);
    expect(got[0]).toBe("Advanced analytics");
    expect(got[1]).toMatch(/^Notebooks Krusgraph writes by rules/);
    expect(got.join("\n")).not.toMatch(/analyticsNotebooks/);
    const doc = new DOMParser().parseFromString(html, "text/html");
    expect(doc.querySelector("#kg-advanced-title")!.tagName).toBe("H2");
    const stages = Array.from(doc.querySelectorAll("p.kg-wrap-text")).map((p) => p.textContent ?? "");
    expect(stages.some((t) => t.startsWith("Each analysis in three stages"))).toBe(true);
  });

  it("the CSS wraps those lines inside the panel", async () => {
    const { readFileSync } = await import("fs");
    const { join } = await import("path");
    const scss = readFileSync(join(__dirname, "ModelItem.scss"), "utf8");
    expect(scss).toMatch(/\.kg-wrap-text \{[^}]*overflow-wrap: anywhere/);
    expect(scss).toMatch(/\.kg-advanced,\n\.kg-adv \{[^}]*min-width: 0/);
  });

  it("'One row per order', not 'One row per orders'; 'the text columns of orders', not 'orders's'", () => {
    expect(["orders", "order_items", "categories", "addresses", "boxes", "people", "status", "VBRK", "sap_vbak"].map(oneRowOf))
      .toEqual(["order", "order item", "category", "address", "box", "person", "status", "VBRK", "sap_vbak"]);
    const step = nextSteps2({ review: REVIEW, created: [], source: SOURCE }).steps.find((s) => s.id === "ds-features")!;
    const why = step.advanced!.analyses.map((a) => a.why).join("\n");
    expect(why).toContain("One row per order with its date: the number of orders per week");
    expect(why).toContain("the text columns of orders");
    expect(why).not.toMatch(/per orders with|orders's/);
  });

  it("Manage: an item the pipeline wrote under its name is not listed as 'no id saved'", () => {
    const WS = "0f0f0f0f-0000-4000-8000-000000000001";
    const o: OutputsDefinition = {
      version: 1, outputs: [], plan: { plan_id: "plan-w1", at: "2026-11-23T10:00:00.000Z" },
      created: [
        { id: "00000000-0000-4000-8000-000000000001", type: "DataPipeline", name: "demo_lh_pipeline", workspace: WS, output: "pipeline", plan: { plan_id: "plan-w1" } },
        { id: "00000000-0000-4000-8000-000000000002", type: "Notebook", name: "demo_lh_silver", workspace: WS, output: "pipeline", plan: { plan_id: "plan-w1" } },
        { id: "00000000-0000-4000-8000-000000000003", type: "Notebook", name: "demo_lh_gold", workspace: WS, output: "pipeline", plan: { plan_id: "plan-w1" } },
      ],
      last_create: { at: "2026-11-23T10:00:00.000Z", item: "m", outputs: [
        { output: "pipeline", label: "Pipeline", name: "demo_lh_pipeline", state: "created" },
        { output: "gold_views", label: "Gold views", name: "demo_lh_gold", state: "created" },
        { output: "semantic_model", label: "Semantic model", name: "demo_lh_model", state: "created" },
      ] },
    } as unknown as OutputsDefinition;
    const rows = rowsOf(o, undefined, "plan-w1");
    expect(rows.filter((r) => r.why === NO_ID_SAVED).map((r) => r.name)).toEqual(["demo_lh_model"]);   // really without an id
    expect(rows.find((r) => r.name === "demo_lh_gold")!.id).toBe("00000000-0000-4000-8000-000000000003");
  });
});
