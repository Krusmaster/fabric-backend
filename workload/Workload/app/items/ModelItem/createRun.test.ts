// n197: Create in the background. The engine answers 202 and an operation id at once; the editor reads the operation
// until it ends (no request held open longer than REQUEST_WAIT_MS), keeps the operation ids and the pending items in
// outputs.json, and a reopened item resumes the same run from the engine's operations of the item.
import { afterEach, describe, expect, it } from "vitest";
import {
  BuildCard, EngineCallError, OPERATION_MAX_MS, OperationState, OutputRequest, REQUEST_WAIT_MS, buildOne, itemOperations,
} from "./engineClient";
import {
  canRetry, heldCard, itemsOf, knownOf, markEarlier, namesWithOneSuffix, settlePending, startRun, stoppedCard, toRetry, waitsForRun,
  withOperation, withPending, withProgress,
} from "./createRun";
import { cardTitle, createEach, previewLine } from "./buildWords";

const client = { auth: { acquireFrontendAccessToken: async () => ({ token: "t" }) } } as never;
const src = { workspace: "w", source: "s", source_name: "demo_lh", schema: "shop" };
const ALL: OutputRequest[] = [
  { kind: "silver_notebook", name: "demo_lh_silver" },
  { kind: "gold_views", name: "demo_lh_gold" },
  { kind: "pipeline", name: "demo_lh_pipeline", jobs: { run_once: true, schedule: null } },
  { kind: "semantic_model", name: "demo_lh_model" },
  { kind: "report", name: "demo_lh_report" },
];

function json(status: number, body: unknown): Response {
  return { ok: status < 400, status, json: async () => body } as Response;
}

function card(o: OutputRequest, extra: Partial<BuildCard> = {}): BuildCard {
  return { output: o.kind, label: o.kind, type: "", name: o.name, dry_run: false, would: "create", updates_in_place: true,
    permissions: { needs: [], missing: null, execute: "" }, answer: { dry_run: false }, ...extra } as BuildCard;
}

/** A fake engine: /build answers 202, /operation answers `states` one after another (an Error: the read fails). */
function engine(states: (Partial<OperationState> | Error)[]) {
  const seen: { route: string; body: any; prefer?: string; signal: boolean }[] = [];
  let n = 0;
  const fetchImpl = async (url: string, init: RequestInit) => {
    const route = url.split("/workload/v1/")[1];
    const body = JSON.parse(String(init.body));
    seen.push({ route, body, prefer: (init.headers as Record<string, string>).Prefer, signal: !!init.signal });
    if (route === "build") return json(202, { operation_id: "a".repeat(32), status: "running" });
    const s = states[Math.min(n++, states.length - 1)];
    if (s instanceof Error) throw s;
    if ((s as any).notFound) return json(404, { error: "No such operation", kind: "not_found" });
    return json(200, { operation_id: "a".repeat(32), id: "a".repeat(32), route: "build", ...s });
  };
  return { fetchImpl, seen };
}

const noSleep = async (): Promise<void> => undefined;

describe("the engine call in the background", () => {
  afterEach(() => {
    delete process.env.KRUSGRAPH_ENGINE_SCOPE;
  });

  it("sends Prefer: respond-async, keeps the operation id and reads the state until the answer", async () => {
    process.env.KRUSGRAPH_ENGINE_SCOPE = "api://x/user_impersonation";
    const done = { outputs: [card(ALL[3], { created: [{ type: "SemanticModel", id: "m1", name: "demo_lh_model", workspace: "w" }] })], created: [] as unknown[] };
    const { fetchImpl, seen } = engine([{ status: "running" }, { status: "waiting_capacity", progress: { words: "Waiting for capacity" } },
      { status: "pending_fabric" }, { status: "done", http: 200, answer: done }]);
    const started: string[] = [];
    const progress: string[] = [];
    const a = await buildOne(client, src, ALL[3], ALL, {} as never, [], fetchImpl, { item_id: "i", create_id: "c1", pending: [] },
      { onStarted: (id) => started.push(id), onProgress: (s) => progress.push(s.status), sleep: noSleep });
    expect(a.outputs[0].created?.[0].id).toBe("m1");
    expect(seen[0].prefer).toBe("respond-async");
    expect(seen[0].body).toMatchObject({ only: ["semantic_model"], item_id: "i", create_id: "c1", skip_built: true });
    expect(seen.slice(1).every((x) => x.route === "operation" && x.prefer === undefined && x.body.operation_id === "a".repeat(32))).toBe(true);
    expect(seen.every((x) => x.signal)).toBe(true);                       // every request is bounded by REQUEST_WAIT_MS
    expect(started).toEqual(["a".repeat(32)]);
    expect(progress).toEqual(["running", "waiting_capacity", "pending_fabric"]);
  });

  it("holds no request open longer than 30 s", () => {
    expect(REQUEST_WAIT_MS).toBeLessThanOrEqual(30_000);
    expect(OPERATION_MAX_MS).toBeGreaterThan(40 * 60_000);             // capacity waits and Fabric's operations fit
  });

  it("keeps reading through failed reads (a phone asleep) and says the engine's error with its status", async () => {
    process.env.KRUSGRAPH_ENGINE_SCOPE = "api://x/user_impersonation";
    const { fetchImpl } = engine([new TypeError("Failed to fetch"), new TypeError("Failed to fetch"),
      { status: "done", http: 409, answer: { error: "taken", kind: "already_exists" } }]);
    const e = await buildOne(client, src, ALL[0], ALL, {} as never, [], fetchImpl, {}, { sleep: noSleep }).catch((x) => x);
    expect(e).toBeInstanceOf(EngineCallError);
    expect(e.status).toBe(409);
    expect(e.answer.kind).toBe("already_exists");
  });

  it("a 404 (the other replica of an engine without a shared store) is read again, and lost only after many", async () => {
    process.env.KRUSGRAPH_ENGINE_SCOPE = "api://x/user_impersonation";
    const flaky = engine([{ notFound: true } as never, { notFound: true } as never, { status: "done", http: 200, answer: { outputs: [card(ALL[0])] } }]);
    const a = await buildOne(client, src, ALL[0], ALL, {} as never, [], flaky.fetchImpl, {}, { sleep: noSleep });
    expect(a.outputs[0].output).toBe("silver_notebook");
    const gone = engine([{ notFound: true } as never]);
    const e = await buildOne(client, src, ALL[0], ALL, {} as never, [], gone.fetchImpl, {}, { sleep: noSleep }).catch((x) => x);
    expect(e.answer.kind).toBe("no_answer");
  });

  it("a lost operation is no answer, to be tried again; resume reads without sending again", async () => {
    process.env.KRUSGRAPH_ENGINE_SCOPE = "api://x/user_impersonation";
    const lost = engine([{ status: "lost", lost: "The engine stopped working on this step (no sign of it for 120 s)." }]);
    const e = await buildOne(client, src, ALL[0], ALL, {} as never, [], lost.fetchImpl, {}, { sleep: noSleep }).catch((x) => x);
    expect(e.answer.kind).toBe("no_answer");
    expect(e.answer.hint).toContain("adopted");
    const again = engine([{ status: "done", http: 200, answer: { outputs: [card(ALL[0])] } }]);
    await buildOne(client, src, ALL[0], ALL, {} as never, [], again.fetchImpl, {}, { resume: "b".repeat(32), sleep: noSleep });
    expect(again.seen.map((x) => x.route)).toEqual(["operation"]);       // nothing was sent to /build
  });

  it("an engine that answers at once (no store for operations) is taken as it answers", async () => {
    process.env.KRUSGRAPH_ENGINE_SCOPE = "api://x/user_impersonation";
    const direct = async () => json(200, { outputs: [card(ALL[0])], created: [] });
    const a = await buildOne(client, src, ALL[0], ALL, {} as never, [], direct, {}, { sleep: noSleep });
    expect(a.outputs[0].output).toBe("silver_notebook");
    expect((a as any).__status).toBeUndefined();
  });

  it("lists the item's operations", async () => {
    process.env.KRUSGRAPH_ENGINE_SCOPE = "api://x/user_impersonation";
    const list = async (_u: string, init: RequestInit) => json(200, { item: JSON.parse(String(init.body)).item_id, create: "c1", operations: [] });
    expect((await itemOperations(client, "i-1", list)).item).toBe("i-1");
  });
});

describe("pending items, operation ids and resume", () => {
  it("records every item a step writes before it is sent; the pipeline writes its notebooks too", () => {
    expect(itemsOf(ALL[2], ALL, "shop").map((i) => i.name)).toEqual(["demo_lh_pipeline", "demo_lh_silver", "demo_lh_gold", "demo_lh_pipeline_check"]);
    const p = withPending(withPending([], ALL[3], ALL, "shop", "t"), ALL[3], ALL, "shop", "t");
    expect(p).toEqual([{ output: "semantic_model", type: "SemanticModel", name: "demo_lh_model", at: "t" }]);
    const made = [{ type: "SemanticModel", id: "m1", name: "demo_lh_model", workspace: "w" }];
    expect(settlePending(p, card(ALL[3]), made)).toEqual([]);
    expect(settlePending(p, card(ALL[3], { status: "lost" }), [])).toEqual(p);   // may still finish in Fabric: kept
    expect(settlePending(p, card(ALL[3], { answer: { error: "x", kind: "timeout" } }), [])).toEqual(p);
  });

  it("a reopened item takes the answers of finished steps, reads running ones again and sends lost ones again", () => {
    let run = startRun("c1", ALL, "2026-11-10T10:00:00Z");
    run = withOperation(withOperation(withOperation(run, "silver_notebook", "op1"), "gold_views", "op2"), "pipeline", "op3");
    const ops = [
      { operation_id: "op1", id: "op1", route: "build", status: "done", http: 200, answer: { outputs: [card(ALL[0])] } },
      { operation_id: "op2", id: "op2", route: "build", status: "waiting_capacity" },
      { operation_id: "op3", id: "op3", route: "build", status: "lost" },
      { operation_id: "op4", id: "op4", route: "build", status: "running", output: "semantic_model", create: "c1" },
    ] as OperationState[];
    const k = knownOf(run, ops);
    expect(Object.keys(k.answers)).toEqual(["silver_notebook"]);
    expect(k.running).toEqual({ gold_views: "op2", semantic_model: "op4" });     // op4: its id was not saved before the reload
    expect(k.answers.pipeline).toBeUndefined();
    expect(k.running.pipeline).toBeUndefined();
  });

  it("createEach shows a held card as waiting for the run and a running card with its state", async () => {
    const seen: string[][] = [];
    const run = await createEach(ALL.slice(3), [], async (o) => ({ outputs: [o.kind === "report" ? heldCard(card(o)) : card(o)], created: [] } as never),
      (cards) => seen.push(cards.map((c) => c.status ?? "")));
    expect(run.cards.map((c) => c.status)).toEqual(["done", "waiting"]);
    expect(cardTitle(run.cards[1])).toBe("report demo_lh_report: waits for the pipeline's run");
    const busy = withProgress({ ...card(ALL[3]), status: "running" }, { status: "waiting_capacity", operation_id: "x", id: "x", route: "build",
      progress: { words: "Waiting for capacity", capacity_app: "https://learn.microsoft.com/fabric/enterprise/metrics-app" } });
    expect(cardTitle(busy)).toBe("semantic_model demo_lh_model: waiting for capacity");
    expect(busy.progress?.capacity_app).toContain("metrics-app");
  });
});

describe("chaining on the run, Try again and Create the rest", () => {
  it("only the report waits for the run, and only with Run once ticked", () => {
    expect(waitsForRun(ALL)).toEqual(["report"]);
    expect(waitsForRun(ALL.map((o) => (o.kind === "pipeline" ? { ...o, jobs: { run_once: false, schedule: null } } : o)))).toEqual([]);
  });

  it("a failed run stops the report with the reason and Try again", () => {
    const c = stoppedCard(heldCard(card(ALL[4])), "Check keys failed: 1 orphan");
    expect(c.refusal?.error).toContain("did not succeed (Check keys failed: 1 orphan)");
    expect(canRetry(c)).toBe(true);
    expect(cardTitle(c)).toBe("report demo_lh_report: not built, the pipeline's run did not succeed");
  });

  it("Try again is on red and unanswered cards, not on a name someone else holds or a choice", () => {
    const red = card(ALL[3], { answer: { error: "x", kind: "fabric_error" } });
    const lost = card(ALL[4], { status: "lost", refusal: { error: "no answer", kind: "no_answer" } });
    const taken = card(ALL[0], { refusal: { error: "taken", kind: "already_exists" } });
    const ok = card(ALL[1]);
    expect(toRetry([red, lost, taken, ok, { ...red, status: "running" }]).map((c) => c.output)).toEqual(["semantic_model", "report"]);
  });
});

describe("truthful words", () => {
  it("the dry run predicts Create: already built from this plan is skipped, and Run once is said", () => {
    const built = card(ALL[0], { dry_run: true, already_built: true });
    const pipe = card(ALL[2], { dry_run: true, jobs: { run_once: true, schedule: null, permission: { granted: true, scope: "DataPipeline.Execute.All", or: "Item.Execute.All" }, words: [] } });
    const a = { dry_run: true, outputs: [built, pipe, card(ALL[3], { dry_run: true })], order: [] as string[], left_out_by_review: [] as unknown[], refused: 0, note: "" };
    expect(cardTitle(built)).toBe("silver_notebook demo_lh_silver: already built from this plan, will be skipped");
    expect(previewLine(a as never)).toBe("This is the dry run: nothing is written yet. Create makes 2 of 3; 1 already built from this plan, will be skipped, then runs the pipeline once.");
  });

  it("one name suffix per Create, and the product marks what an earlier Create built", () => {
    const choices = [
      { type: "semantic_model", name: "demo_lh_model", enabled: true },
      { type: "report", name: "demo_lh_report_2", enabled: true },
      { type: "graphql", name: "demo_lh_api", enabled: false },
    ] as never;
    const named = namesWithOneSuffix(choices, ["demo_lh_model_2", "demo_lh_report"]);
    expect((named as { name: string }[]).map((c) => c.name)).toEqual(["demo_lh_model_3", "demo_lh_report_3", "demo_lh_api"]);
    const items = [{ id: "a", name: "m" }, { id: "b", name: "m_2" }];
    expect(markEarlier(items, [{ id: "b", type: "T", name: "m_2", workspace: "w" }])).toEqual([{ id: "a", name: "m", earlier: true }, { id: "b", name: "m_2" }]);
  });
});
