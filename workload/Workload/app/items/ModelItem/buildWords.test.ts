// n174: what the Krusgraph Model builds. The kinds mirror fabric_backend/workload_api.KINDS (tests/test_workload_build.py
// checks the copy); here: the order (model before report), Update or a new name on re-open, outputs.json after a Create
// with the data product, Open in Fabric per created item, and the card's words.
import { describe, expect, it } from "vitest";
import {
  KINDS,
  ORDER,
  afterCreate,
  cardProblem,
  cardTitle,
  choiceProblems,
  choicesFor,
  createLabel,
  defaultName,
  nameAction,
  openLinks,
  productToStore,
  toRequests,
} from "./buildWords";
import { BuildCard, ManyAnswer } from "./engineClient";
import { CreatedItem, OutputChoice, emptyDefinition, fromParts, toParts } from "./ModelItemDefinition";

const WS = "11111111-2222-3333-4444-555555555555";

function card(over: Partial<BuildCard>): BuildCard {
  return {
    output: "semantic_model", label: "Semantic model", type: "SemanticModel", name: "shop_sales", dry_run: true, would: "create",
    updates_in_place: true, permissions: { needs: ["SemanticModel.ReadWrite.All or Item.ReadWrite.All"], missing: null, execute: "none" },
    answer: { dry_run: true, summary: "7 tables" }, ...over,
  };
}

const ANSWER: ManyAnswer = {
  dry_run: false,
  outputs: [
    card({ dry_run: false, created: [{ type: "SemanticModel", id: "m1", name: "shop_sales", workspace: WS, output: "semantic_model" }],
      portal_steps: ["Refresh the model once"] }),
    card({ output: "report", label: "Report", type: "Report", name: "shop_report", dry_run: false, updates_in_place: false,
      created: [{ type: "Report", id: "r1", name: "shop_report", workspace: WS, output: "report" }] }),
  ],
  order: ["semantic_model", "report"],
  left_out_by_review: [],
  refused: 0,
  note: "2 of 2 output(s) built.",
  created: [
    { type: "SemanticModel", id: "m1", name: "shop_sales", workspace: WS, output: "semantic_model" },
    { type: "Report", id: "r1", name: "shop_report", workspace: WS, output: "report" },
  ],
  product: {
    name: "Shop sales", owner: null, owner_note: "Nobody has chosen an owner yet.", plan: { plan_id: "p1", schema_fingerprint: "sha256:ab" },
    source: { lakehouse: "demo_lh", schema: "shop" },
    items: [
      { type: "SemanticModel", id: "m1", name: "shop_sales", workspace: WS, output: "semantic_model", label: "Semantic model" },
      { type: "Report", id: "r1", name: "shop_report", workspace: WS, output: "report", label: "Report" },
    ],
    domains: [{ name: "customers", tables: ["customers", "orders"], why: "the hub" }], unassigned: [], from: "domain_draft",
  },
};

describe("the outputs", () => {
  it("are every output the MCP tools build, the data flow first and the model before its report", () => {
    expect(ORDER).toEqual(["silver_notebook", "gold_views", "pipeline", "semantic_model", "report", "graphql", "ontology", "data_agent", "rayfin_app"]);
    expect(KINDS.every((k) => k.needs.every((n) => !n.includes("Execute")))).toBe(true);
    expect(KINDS.find((k) => k.kind === "pipeline").needs).toEqual(["Notebook.ReadWrite.All or Item.ReadWrite.All",
      "DataPipeline.ReadWrite.All or Item.ReadWrite.All"]);
  });

  it("go to the engine enabled only and in the build's order", () => {
    const choices: OutputChoice[] = [
      { type: "report", name: "r", enabled: true },
      { type: "semantic_model", name: "m", enabled: true },
      { type: "ontology", name: "o", enabled: false },
      { type: "silver_notebook", name: "s", enabled: true },
    ];
    expect(toRequests(choices)).toEqual([{ kind: "silver_notebook", name: "s" }, { kind: "semantic_model", name: "m" }, { kind: "report", name: "r" }]);
    expect(toRequests([{ type: "report", name: "r", enabled: true, model: "existing" }])).toEqual([{ kind: "report", name: "r", model: "existing" }]);
  });

  it("start from what the item saved, else the API for GraphQL as in phase 1", () => {
    const fresh = choicesFor([], "demo lh");
    expect(fresh.filter((c) => c.enabled).map((c) => c.type)).toEqual(["graphql"]);
    expect(fresh.find((c) => c.type === "graphql").name).toBe("demo_lh_api");
    expect(defaultName("silver_notebook", "demo_lh")).toBe("demo_lh_silver");
    const saved = choicesFor([{ type: "graphql", name: "shop_api", enabled: true, writable: false }], "demo_lh");
    expect(saved.find((c) => c.type === "graphql")).toEqual({ type: "graphql", name: "shop_api", enabled: true, writable: false });
    expect(saved.find((c) => c.type === "pipeline").enabled).toBe(false);
  });

  it("say what is wrong before any call", () => {
    expect(choiceProblems([{ type: "report", name: "r", enabled: true }])[0]).toContain("needs a semantic model");
    expect(choiceProblems([{ type: "silver_notebook", name: "x", enabled: true }, { type: "gold_views", name: "X", enabled: true }])[0])
      .toContain("two different names");
    expect(choiceProblems([{ type: "ontology", name: "bad name", enabled: true }])[0]).toContain("letters, digits");
    expect(choiceProblems([])).toEqual(["Choose at least one thing to build."]);
  });
});

describe("re-opening the item", () => {
  const created: CreatedItem[] = [
    { type: "SemanticModel", id: "m1", name: "shop_sales", workspace: WS, output: "semantic_model" },
    { type: "Report", id: "r1", name: "shop_report", workspace: WS, output: "report" },
    { type: "GraphQLApi", id: "a1", name: "shop_api", workspace: WS },
  ];

  it("offers Update where the tool updates in place", () => {
    expect(nameAction("semantic_model", "shop_sales", created)).toMatchObject({ action: "update", button: "Update" });
    expect(nameAction("graphql", "shop_api", created).action).toBe("update");          // phase 1 saved it without `output`
    expect(nameAction("semantic_model", "other", created).action).toBe("create");
  });

  it("offers a new name for a report, which is never updated in place", () => {
    const a = nameAction("report", "shop_report", created);
    expect(a.action).toBe("new_name");
    expect(a.suggestion).toBe("shop_report_2");
  });
});

describe("after Create", () => {
  it("outputs.json keeps the choices, every created item and the data product with the ids, and reads back the same", () => {
    const choices: OutputChoice[] = [{ type: "semantic_model", name: "shop_sales", enabled: true }, { type: "report", name: "shop_report", enabled: true }];
    const def = emptyDefinition();
    const outputs = afterCreate(def.outputs, choices, ANSWER, "2026-11-09T10:00:00Z");
    expect(outputs.created.map((c) => c.id)).toEqual(["m1", "r1"]);
    expect(outputs.product).toMatchObject({ name: "Shop sales", owner: null, plan: { plan_id: "p1", schema_fingerprint: "sha256:ab" } });
    expect(outputs.product.items.map((x) => x.id)).toEqual(["m1", "r1"]);
    expect(outputs.product.domains).toEqual([{ name: "customers", tables: ["customers", "orders"], why: "the hub" }]);
    const back = fromParts(toParts({ ...def, outputs }));
    expect(back.outputs).toEqual({ ...outputs, version: 1 });
    // a second build of the same product adds to it; the same id is replaced, not repeated
    const again = afterCreate(back.outputs, choices, { ...ANSWER, created: [ANSWER.created[0]],
      product: { ...ANSWER.product, items: [ANSWER.product.items[0]] } }, "2026-11-09T11:00:00Z");
    expect(again.product.items.map((x) => x.id)).toEqual(["m1", "r1"]);
    expect(again.created.map((x) => x.id)).toEqual(["m1", "r1"]);
  });

  it("a dry run's product (no ids) is never stored", () => {
    expect(productToStore({ ...ANSWER.product, items: [{ type: "Report", id: undefined, name: "r", workspace: undefined, would: "create" }] }, "t"))
      .toBeUndefined();
  });

  it("gives one Open in Fabric per created item, with its id, workspace and type", () => {
    const links = openLinks(ANSWER.created);
    expect(links.map((l) => l.label)).toEqual(["Semantic model shop_sales", "Report shop_report"]);
    expect(links[1].item).toEqual({ id: "r1", workspaceId: WS, type: "Report", displayName: "shop_report" });
  });
});

describe("a card's words", () => {
  it("say create or update in the dry run, and why not when refused", () => {
    expect(cardTitle(card({}))).toBe("Create semantic model shop_sales");
    expect(cardTitle(card({ would: "update" }))).toBe("Update semantic model shop_sales");
    const refused = card({ refusal: { error: "taken", kind: "already_exists", hint: "Choose another name." }, answer: undefined });
    expect(cardTitle(refused)).toBe("Semantic model shop_sales: not built");
    expect(cardProblem(refused)).toMatchObject({ kind: "already_exists" });
  });

  it("name the missing permission with the Entra steps", () => {
    const steps = ["Entra admin centre … Krusgraph workload (dev)", "Tick DataPipeline.ReadWrite.All → Add permissions."];
    const c = card({ consent: { error: "no DataPipeline.ReadWrite.All", kind: "consent", scope: "DataPipeline.ReadWrite.All", entra_steps: steps } });
    expect(cardProblem(c)).toMatchObject({ kind: "consent", steps });
  });

  it("the Create button says when something is updated", () => {
    expect(createLabel({ ...ANSWER, outputs: [card({})] })).toBe("Create");
    expect(createLabel({ ...ANSWER, outputs: [card({ would: "update" })] })).toBe("Create and update");
  });
});
