// n179: Create one output per request (the founder's live Create of 9 November 2026 showed only "Failed to fetch" while
// the server built six of eight items), the semantic model's words, and the schema picked from the lakehouse's list.
import { afterEach, describe, expect, it, vi } from "vitest";
import { createEach, createOrder, modelFacts, requestFor, resultLine, schemaToUse } from "./buildWords";
import { BUILD_WAIT_MS, BuildCard, CreatedRef, EngineCallError, ManyAnswer, OutputRequest, buildOne, lostAnswer } from "./engineClient";

const ALL: OutputRequest[] = [
  { kind: "report", name: "demo_lh_report" },
  { kind: "graphql", name: "shop_api" },
  { kind: "semantic_model", name: "demo_lh_model" },
  { kind: "silver_notebook", name: "demo_lh_silver" },
];

function answer(o: OutputRequest, created: CreatedRef[] = [], extra: Partial<BuildCard> = {}): ManyAnswer {
  const card = {
    output: o.kind, label: o.kind, type: "", name: o.name, dry_run: false, would: "create", updates_in_place: true,
    permissions: { needs: [], missing: null, execute: "" }, answer: { dry_run: false }, created, ...extra,
  } as BuildCard;
  return { dry_run: false, outputs: [card], order: [o.kind], left_out_by_review: [], refused: 0, note: "", created };
}

const ref = (o: OutputRequest, id: string): CreatedRef => ({ type: "T", id, name: o.name, workspace: "ws", output: o.kind });

describe("createEach", () => {
  it("sends one request per output in the engine's order, the model before its report, and the report gets the new model's id", async () => {
    const sent: OutputRequest[] = [];
    const run = await createEach(ALL, [], async (o) => {
      sent.push(o);
      return answer(o, o.kind === "semantic_model" ? [ref(o, "model-id")] : o.kind === "report" ? [ref(o, "report-id")] : []);
    }, () => undefined);
    expect(sent.map((o) => o.kind)).toEqual(["silver_notebook", "semantic_model", "report", "graphql"]);
    expect(sent.find((o) => o.kind === "report")?.model).toBe("model-id");
    expect(run.created.map((c) => c.id)).toEqual(["model-id", "report-id"]);
    expect(run.cards.every((c) => c.status === "done")).toBe(true);
  });

  it("shows each card's progress: all waiting, then one running at a time", async () => {
    const seen: string[][] = [];
    await createEach(ALL.slice(2), [], async (o) => answer(o), (cards) => seen.push(cards.map((c) => c.status ?? "")));
    expect(seen[0]).toEqual(["waiting", "waiting"]);
    expect(seen[1]).toEqual(["running", "waiting"]);
    expect(seen[seen.length - 1]).toEqual(["done", "done"]);
  });

  it("a lost answer costs one card, not the others, and says it may still be running", async () => {
    const sent: OutputRequest[] = [];
    const run = await createEach(ALL, [], async (o) => {
      sent.push(o);
      if (o.kind === "semantic_model") throw new EngineCallError(lostAnswer("build", 60, false), 0);
      return answer(o);
    }, () => undefined);
    const by = Object.fromEntries(run.cards.map((c) => [c.output, c]));
    expect(by.semantic_model.status).toBe("lost");
    expect(by.semantic_model.refusal?.kind).toBe("no_answer");
    expect(by.semantic_model.refusal?.hint).toContain("still be running in Fabric");
    expect(by.graphql.status).toBe("done");
    expect(sent.find((o) => o.kind === "report")?.model).toBe("demo_lh_model");   // no id: the engine looks it up by name
    const line = resultLine({ dry_run: false, outputs: run.cards, order: [], left_out_by_review: [], refused: 1, note: "" });
    expect(line).toContain("Reopen this item in a minute");
  });

  it("an engine error is its own card with its reason", async () => {
    const run = await createEach([ALL[1]], [], async () => {
      throw new EngineCallError({ error: "the API failed", kind: "unexpected", hint: "look" }, 502);
    }, () => undefined);
    expect(run.cards[0].status).toBe("done");
    expect(run.cards[0].refusal?.error).toBe("the API failed");
  });

  it("a re-run starts from the created ids, so the engine can skip what is built", async () => {
    const before = [ref(ALL[2], "model-id")];
    const got: CreatedRef[][] = [];
    await createEach(ALL.slice(0, 1).concat(ALL[2]), before, async (o, created) => {
      got.push(created);
      return answer(o, [], o.kind === "semantic_model" ? { already_built: true, created: before } : {});
    }, () => undefined);
    expect(got[0].map((c) => c.id)).toEqual(["model-id"]);
    expect(requestFor(ALL[0], ALL, before).model).toBe("model-id");
  });

  it("orders like the engine", () => {
    expect(createOrder(ALL).map((o) => o.kind)).toEqual(["silver_notebook", "semantic_model", "report", "graphql"]);
  });
});

describe("buildOne", () => {
  afterEach(() => {
    vi.useRealTimers();
    delete process.env.KRUSGRAPH_ENGINE_SCOPE;
  });
  const client = { auth: { acquireFrontendAccessToken: async () => ({ token: "t" }) } } as never;
  const src = { workspace: "w", source: "s", source_name: "demo_lh", schema: "shop" };

  it("turns 'Failed to fetch' into an answer that names the cause and the next step", async () => {
    process.env.KRUSGRAPH_ENGINE_SCOPE = "api://x/user_impersonation";
    const failing = async () => {
      throw new TypeError("Failed to fetch");
    };
    const e = await buildOne(client, src, ALL[1], ALL, {} as never, [], failing).catch((x) => x);
    expect(e).toBeInstanceOf(EngineCallError);
    expect(e.answer.kind).toBe("no_answer");
    expect(e.answer.error).toContain("Failed to fetch");
    expect(e.answer.hint).toContain("Create again");
  });

  it("sends one output with skip_built and stops waiting before the 240 s ingress timeout", async () => {
    process.env.KRUSGRAPH_ENGINE_SCOPE = "api://x/user_impersonation";
    vi.useFakeTimers();
    let body: any;
    const slow = (_u: string, init: RequestInit) =>
      new Promise<Response>((_, reject) => {
        body = JSON.parse(String(init.body));
        init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      });
    const p = buildOne(client, src, ALL[1], ALL, {} as never, [], slow).catch((x) => x);
    await vi.advanceTimersByTimeAsync(BUILD_WAIT_MS + 10);
    const e = await p;
    expect(BUILD_WAIT_MS).toBeLessThan(240_000);
    expect(e.answer.kind).toBe("no_answer");
    expect(e.answer.error).toContain("stopped waiting");
    expect(body.outputs).toEqual(ALL);
    expect(body.only).toEqual(["graphql"]);
    expect(body.skip_built).toBe(true);
    expect(body.dry_run).toBe(false);
  });
});

describe("modelFacts", () => {
  it("says the model in words, never [object Object]", () => {
    const lines = modelFacts({
      tables: 7, storage_mode: "directLake (SQL analytics endpoint)", relationships_active: 6, relationships_inactive: 1,
      relationships_not_expressible: 0, measures: [{}, {}, {}], order_amount: { measures: [{}] },
      date_table: { name: "Calendar", related: [{}, {}] },
    });
    expect(lines.join(" ")).not.toContain("[object Object]");
    expect(lines).toContain("7 tables in Direct Lake");
    expect(lines[1]).toBe("6 relationships active, 1 inactive (another path joins the same tables)");
    expect(lines).toContain("4 measures");
    expect(lines).toContain("Date table Calendar, marked as the date table, related to 2 date columns");
    expect(modelFacts("one line\nmore")).toEqual(["one line"]);
    expect(modelFacts({ tables: 1, relationships_active: 0, measures: [], date_table: null })).toContain("No date table: no date column to relate one to");
  });
});

describe("schemaToUse", () => {
  const list = { schemas: [{ schema: "dbo", tables: 0 }, { schema: "shop", tables: 7 }], preselect: "shop" };
  it("preselects the only schema with tables", () => expect(schemaToUse(list)).toBe("shop"));
  it("keeps a saved schema and corrects its case", () => {
    expect(schemaToUse(list, "shop")).toBe("shop");
    expect(schemaToUse(list, "Shop")).toBe("shop");
  });
  it("leaves the choice to the person when several schemas hold tables", () => {
    expect(schemaToUse({ schemas: [{ schema: "sap", tables: 9 }, { schema: "shop", tables: 7 }], preselect: null })).toBeUndefined();
  });
  it("does not guess between two that differ only by case", () => {
    const two = { schemas: [{ schema: "Shop", tables: 7 }, { schema: "shop", tables: 7 }], preselect: null as string | null };
    expect(schemaToUse(two, "SHOP")).toBeUndefined();
    expect(schemaToUse(two, "Shop")).toBe("Shop");
  });
});
