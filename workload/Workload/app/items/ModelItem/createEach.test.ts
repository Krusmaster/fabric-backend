// n179: Create one output per request (the founder's live Create of 9 November 2026 showed only "Failed to fetch" while
// the server built six of eight items), the semantic model's words, and the schema picked from the lakehouse's list.
import { afterEach, describe, expect, it, vi } from "vitest";
import { CREATE_AT_ONCE, createEach, createOrder, modelFacts, requestFor, resultLine, schemaToUse } from "./buildWords";
import { toFinish } from "./ed2Create";
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
    // n222: what does not wait for another output is sent at once; ED2: the model waits for silver, the report for its model
    expect(sent.map((o) => o.kind)).toEqual(["silver_notebook", "graphql", "semantic_model", "report"]);
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
    // ED2: the report is not sent on a model whose answer was lost; it says once that it waits for the model
    expect(sent.find((o) => o.kind === "report")).toBeUndefined();
    expect(by.report.refusal?.kind).toBe("waiting_for");
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

// n207: the audit of 11 November 2026. The dry run refused an output (an item of its name that this Model did not build),
// Create sent it anyway with its names recorded as pending, and the engine adopted the colleague's item. Create now never
// sends a step its dry run refused: its card is the dry run's refusal, and the other outputs go on.
describe("createEach after a dry run that refused an output", () => {
  const refusal = { error: "SemanticModel 'demo_lh_model' already exists in this workspace and was not built by this Krusgraph Model; nothing was written.",
    kind: "already_exists", hint: "Choose another name." };
  const preview = (outputs: OutputRequest[], refused: OutputRequest["kind"][]): ManyAnswer => ({
    dry_run: true, order: outputs.map((o) => o.kind), left_out_by_review: [], refused: refused.length, note: "", created: [],
    outputs: outputs.map((o) => ({ ...answer(o).outputs[0], dry_run: true, ...(refused.includes(o.kind) ? { refusal } : {}) })),
  } as ManyAnswer);

  it("does not send the refused step and shows the dry run's refusal; the others are sent", async () => {
    const sent: OutputRequest[] = [];
    const run = await createEach(ALL, [], async (o) => { sent.push(o); return answer(o); }, () => undefined, preview(ALL, ["semantic_model"]));
    expect(sent.map((o) => o.kind)).toEqual(["silver_notebook", "graphql"]);   // n222: the API does not wait; ED2: the report waits for its model
    const card = run.cards.find((c) => c.output === "semantic_model")!;
    expect(card.status).toBe("done");
    expect(card.refusal?.kind).toBe("already_exists");
    expect(card.dry_run).toBe(false);
    expect(card.created).toEqual([]);
  });

  it("sends nothing when the dry run refused every output", async () => {
    const send = vi.fn(async (o: OutputRequest) => answer(o));
    const run = await createEach(ALL, [], send, () => undefined, preview(ALL, ALL.map((o) => o.kind)));
    expect(send).not.toHaveBeenCalled();
    // the dry run's own refusal on each, before ED2's "waiting for": the person sees why each was refused
    expect(run.cards.every((c) => c.refusal?.kind === "already_exists" && c.status === "done")).toBe(true);
  });

  it("sends the step when its name was changed after the dry run", async () => {
    const sent: OutputRequest[] = [];
    const renamed = ALL.map((o) => (o.kind === "semantic_model" ? { ...o, name: "demo_lh_model_2" } : o));
    await createEach(renamed, [], async (o) => { sent.push(o); return answer(o); }, () => undefined, preview(ALL, ["semantic_model"]));
    expect(sent.map((o) => o.name)).toContain("demo_lh_model_2");
  });
});

// n222: the founder's live test of 11 November 2026, "it must go faster": Create built the six outputs strictly one after
// another, each waiting for Fabric. Now the steps that do not depend on each other are sent at once.
describe("n222: createEach sends independent outputs at once", () => {
  const SIX: OutputRequest[] = [
    { kind: "silver_notebook", name: "s" }, { kind: "gold_views", name: "g" }, { kind: "pipeline", name: "p" },
    { kind: "semantic_model", name: "m" }, { kind: "report", name: "r" }, { kind: "graphql", name: "a" },
  ];

  /** send() that answers after `ms[kind]` fake milliseconds; records when each step started and ended. */
  function timed(ms: Partial<Record<OutputRequest["kind"], number>>) {
    let now = 0;
    const log: { kind: string; start: number; end: number }[] = [];
    const waiting: { at: number; go: () => void }[] = [];
    const send = (o: OutputRequest) => new Promise<ManyAnswer>((resolve) => {
      const start = now;
      waiting.push({ at: now + (ms[o.kind] ?? 10), go: () => { log.push({ kind: o.kind, start, end: now }); resolve(answer(o, o.kind === "semantic_model" ? [ref(o, "model-id")] : [])); } });
    });
    /** advances the fake clock to the next answer until nothing waits */
    async function drive(p: Promise<unknown>) {
      let finished = false;
      void p.then(() => { finished = true; });
      while (!finished) {
        await new Promise((r) => setTimeout(r, 0));
        if (!waiting.length) continue;
        waiting.sort((a, b) => a.at - b.at);
        const next = waiting.shift()!;
        now = next.at;
        next.go();
      }
      return p;
    }
    return { send, log, drive, clock: () => now };
  }

  it("ED2: the six outputs in build order: silver and the API at once, then gold, the pipeline, the model, its report", async () => {
    const t = timed({ silver_notebook: 20, gold_views: 20, semantic_model: 30, graphql: 20, pipeline: 40, report: 20 });
    const run = await t.drive(createEach(SIX, [], (o) => t.send(o), () => undefined)) as Awaited<ReturnType<typeof createEach>>;
    const at = Object.fromEntries(t.log.map((x) => [x.kind, x]));
    expect(CREATE_AT_ONCE).toBe(4);
    for (const k of ["silver_notebook", "graphql"]) expect(at[k].start).toBe(0);
    expect(at.gold_views.start).toBe(20);                       // after silver
    expect(at.pipeline.start).toBe(40);                         // after both notebooks
    expect(at.semantic_model.start).toBe(80);                   // after the flow
    expect(at.report.start).toBe(110);                          // after its model, on the model's new id
    expect(t.clock()).toBe(130);                                // one after another: 150
    expect(run.cards.map((c) => c.output)).toEqual(SIX.map((o) => o.kind));   // the cards keep the engine's order
    expect(run.cards.every((c) => c.status === "done")).toBe(true);
  });

  it("the report is built on the model's new id even when the model answers last", async () => {
    const sent: OutputRequest[] = [];
    const t = timed({ semantic_model: 50 });
    await t.drive(createEach(SIX, [], (o) => { sent.push(o); return t.send(o); }, () => undefined));
    expect(sent.find((o) => o.kind === "report")?.model).toBe("model-id");
  });

  it("never more than CREATE_AT_ONCE steps at a time, and one at a time when asked", async () => {
    let open = 0, most = 0;
    const send = async (o: OutputRequest) => { open++; most = Math.max(most, open); await new Promise((r) => setTimeout(r, 1)); open--; return answer(o); };
    const many: OutputRequest[] = [...SIX, { kind: "ontology", name: "o" }, { kind: "data_agent", name: "d" }];
    await createEach(many, [], send, () => undefined);
    expect(most).toBeGreaterThan(1);
    expect(most).toBeLessThanOrEqual(CREATE_AT_ONCE);
    open = 0; most = 0;
    await createEach(many, [], send, () => undefined, undefined, 1);
    expect(most).toBe(1);
  });

  it("each card shows its own state while several run: the progress line counts them", async () => {
    const seen: string[][] = [];
    const t = timed({});
    await t.drive(createEach(SIX, [], (o) => t.send(o), (cards) => seen.push(cards.map((c) => c.status ?? ""))));
    expect(seen.some((s) => s.filter((x) => x === "running").length === 2)).toBe(true);   // silver and the API
    expect(seen[seen.length - 1].every((x) => x === "done")).toBe(true);
  });

  it("ED2: a failed model: its report is not sent and says once that it waits for the model", async () => {
    const sent: string[] = [];
    const run = await createEach(SIX, [], async (o) => {
      sent.push(o.kind);
      if (o.kind === "semantic_model") throw new EngineCallError({ error: "failed", kind: "unexpected" }, 502);
      return answer(o);
    }, () => undefined);
    expect(sent).not.toContain("report");
    expect(run.cards.find((c) => c.output === "report")?.refusal?.error).toBe("Waiting for the semantic model: not sent, because the semantic model was not built.");
  });

  it("ED2: silver fails: gold, the pipeline and the model are not created, each said once", async () => {
    const sent: string[] = [];
    const run = await createEach(SIX, [], async (o) => {
      sent.push(o.kind);
      if (o.kind === "silver_notebook") return answer(o, [], { answer: { dry_run: false, error: "Fabric answered HTTP 400" } });
      return answer(o);
    }, () => undefined);
    expect(sent.sort()).toEqual(["graphql", "silver_notebook"]);
    const by = Object.fromEntries(run.cards.map((c) => [c.output, c]));
    expect(by.gold_views.refusal?.error).toBe("Waiting for silver: not sent, because silver was not built.");
    expect(by.pipeline.refusal?.kind).toBe("waiting_for");
    expect(by.report.refusal?.kind).toBe("waiting_for");
  });

  it("ED2: Fix and finish after a partial result sends only what is missing, reusing what exists", async () => {
    const first = await createEach(SIX, [], async (o) =>
      o.kind === "silver_notebook" ? answer(o, [], { answer: { dry_run: false, error: "boom" } }) : answer(o, [ref(o, `${o.kind}-1`)]), () => undefined);
    const missing = toFinish(first.cards).map((c) => SIX.find((o) => o.kind === c.output)!);
    expect(missing.map((o) => o.kind)).toEqual(["silver_notebook", "gold_views", "pipeline", "semantic_model", "report"]);
    const sent: string[] = [];
    const again = await createEach(missing, first.created, async (o, made) => {
      sent.push(o.kind);
      expect(made.some((c) => c.output === "graphql")).toBe(true);           // what exists is passed on, never sent again
      return answer(o, [ref(o, `${o.kind}-2`)]);
    }, () => undefined);
    expect(sent).not.toContain("graphql");
    expect(sent).toEqual(["silver_notebook", "gold_views", "pipeline", "semantic_model", "report"]);
    expect(again.cards.every((c) => !c.refusal)).toBe(true);
  });
});
