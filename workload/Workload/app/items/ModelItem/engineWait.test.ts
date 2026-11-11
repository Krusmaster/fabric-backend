// n223: the engine client tells the editor what a step waits on (onWait), stops a read-only step on Cancel, asks the
// Fabric host for the engine's token once instead of on every read, and reads a background step's state first after
// 300 ms instead of a full second. The numbers in the founder's note ("Del 1") come from these test doubles.
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  BuildCard, EngineCallError, OPERATION_POLL_MS, OperationState, OutputRequest, buildOne, engineToken, routeWait, tokenExpiry, waitOf,
} from "./engineClient";
import type { WaitSignal } from "./waitWords";

const src = { workspace: "w", source: "s", source_name: "demo_lh", schema: "shop" };
const OUT: OutputRequest = { kind: "semantic_model", name: "demo_lh_model" };
const DONE = { outputs: [{ output: "semantic_model", name: "demo_lh_model" } as BuildCard], created: [] as unknown[] };

function json(status: number, body: unknown): Response {
  return { ok: status < 400, status, json: async () => body } as Response;
}

/** a token the client can read the expiry of (header.payload.signature) */
function jwt(expSeconds: number): string {
  const b64 = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${b64({ alg: "none" })}.${b64({ exp: expSeconds })}.sig`;
}

function hostClient(token: string) {
  const asked: string[][] = [];
  return { asked, client: { auth: { acquireFrontendAccessToken: async (r: { scopes: string[] }) => { asked.push(r.scopes); return { token }; } } } as never };
}

/** a fake engine: 202 for the step, then `states` for each read of its state */
function fakeEngine(states: (Partial<OperationState> | Error)[]) {
  let n = 0;
  const routes: string[] = [];
  const fetchImpl = async (url: string, _init: RequestInit) => {
    const route = url.split("/workload/v1/")[1];
    routes.push(route);
    if (route === "build") return json(202, { operation_id: "a".repeat(32), status: "running" });
    const s = states[Math.min(n++, states.length - 1)];
    if (s instanceof Error) throw s;
    return json(200, { operation_id: "a".repeat(32), id: "a".repeat(32), route: "build", ...s });
  };
  return { fetchImpl, routes };
}

beforeEach(() => {
  process.env.KRUSGRAPH_ENGINE_SCOPE = "api://x/user_impersonation";
});
afterEach(() => {
  delete process.env.KRUSGRAPH_ENGINE_SCOPE;
});

describe("what a step waits on", () => {
  it("is SQL for the reads of review, check and schemas, and only 'the engine' for the rest", () => {
    expect(routeWait("review")).toBe("sql");
    expect(routeWait("check")).toBe("sql");
    expect(routeWait("schemas")).toBe("sql");
    expect(routeWait("build")).toBe("engine");
    expect(routeWait("product")).toBe("engine");
  });

  it("is the capacity on 429 (waiting_capacity), Fabric's operation on pending_fabric, with the engine's words and counts", () => {
    expect(waitOf("check", { status: "running", progress: { done: 3, total: 7, unit: "keys and links counted" } })).toEqual(
      { kind: "sql", progress: { done: 3, total: 7, unit: "keys and links counted" } });
    expect(waitOf("build", { status: "waiting_capacity", progress: { words: "Capacity busy (429), attempt 2" } })).toEqual(
      { kind: "capacity", words: "Capacity busy (429), attempt 2" });
    expect(waitOf("build", { status: "pending_fabric" }).kind).toBe("fabric");
    expect(waitOf("review", { status: "running" })).toEqual({ kind: "sql" });
  });

  it("is reported while the step runs, and a run of failed reads says the network", async () => {
    const { client } = hostClient("t");
    const signals: WaitSignal[] = [];
    const { fetchImpl } = fakeEngine([
      { status: "running" }, { status: "waiting_capacity", progress: { words: "busy" } }, new Error("Failed to fetch"), new Error("Failed to fetch"),
      { status: "pending_fabric" }, { status: "done", http: 200, answer: DONE },
    ]);
    await buildOne(client, src, OUT, [OUT], {} as never, [], fetchImpl, {}, { sleep: async () => undefined, onWait: (w) => signals.push(w) });
    expect(signals.map((s) => s.kind)).toEqual(["engine", "engine", "capacity", "network", "fabric"]);
  });
});

describe("Cancel on a read-only step", () => {
  it("stops reading at once and answers 'cancelled'", async () => {
    const { client } = hostClient("t");
    const stop = new AbortController();
    const { fetchImpl, routes } = fakeEngine([{ status: "running" }]);
    let reads = 0;
    const sleep = async () => { if (++reads === 3) stop.abort(); };
    const e = await buildOne(client, src, OUT, [OUT], {} as never, [], fetchImpl, {}, { sleep, signal: stop.signal }).catch((x) => x);
    expect(e).toBeInstanceOf(EngineCallError);
    expect(e.answer.kind).toBe("cancelled");
    expect(e.answer.error).toContain("nothing in Fabric changed");
    expect(routes.filter((r) => r === "operation").length).toBe(2);   // no read after Cancel
  });

  it("sends nothing when cancelled before it starts", async () => {
    const { client } = hostClient("t");
    const stop = new AbortController();
    stop.abort();
    const { fetchImpl, routes } = fakeEngine([{ status: "running" }]);
    const e = await buildOne(client, src, OUT, [OUT], {} as never, [], fetchImpl, {}, { signal: stop.signal }).catch((x) => x);
    expect(e.answer.kind).toBe("cancelled");
    expect(routes).toEqual([]);
  });
});

describe("the engine's token", () => {
  it("is asked of the Fabric host once per step instead of once per request (Del 1: 6 asks before, 1 after)", async () => {
    const { client, asked } = hostClient(jwt(Math.floor(Date.now() / 1000) + 3600));
    const { fetchImpl, routes } = fakeEngine([{ status: "running" }, { status: "running" }, { status: "running" }, { status: "running" },
      { status: "done", http: 200, answer: DONE }]);
    await buildOne(client, src, OUT, [OUT], {} as never, [], fetchImpl, {}, { sleep: async () => undefined });
    expect(routes.length).toBe(6);        // the step and five reads of its state
    expect(asked.length).toBe(1);         // before n223: 6
  });

  it("is asked again five minutes before it expires, and a token without a readable expiry is never kept", async () => {
    const now = 1_800_000_000_000;
    const soon = hostClient(jwt(now / 1000 + 4 * 60));
    await engineToken(soon.client, "s", () => now);
    await engineToken(soon.client, "s", () => now);
    expect(soon.asked.length).toBe(2);
    const opaque = hostClient("t");
    await engineToken(opaque.client, "s");
    await engineToken(opaque.client, "s");
    expect(opaque.asked.length).toBe(2);
    expect(tokenExpiry("t")).toBeUndefined();
    expect(tokenExpiry(jwt(1234))).toBe(1_234_000);
  });
});

describe("the first read of a background step", () => {
  it("comes after 300 ms, not a second (Del 1: a review the engine answers in 0.3 s is seen after 0.3 s, was 1 s)", async () => {
    expect(OPERATION_POLL_MS[0]).toBe(300);
    const { client } = hostClient("t");
    const slept: number[] = [];
    const { fetchImpl } = fakeEngine([{ status: "done", http: 200, answer: DONE }]);
    await buildOne(client, src, OUT, [OUT], {} as never, [], fetchImpl, {}, { sleep: async (ms) => { slept.push(ms); } });
    expect(slept).toEqual([300]);
  });

  it("then reads at 1, 2, 3.5, 5.5 and 8.5 s, then every 5 s as before (two more reads in the first 13 s, none after)", () => {
    const at: number[] = [];
    let t = 0;
    for (let i = 0; i < 9; i++) { t += OPERATION_POLL_MS[Math.min(i, OPERATION_POLL_MS.length - 1)]; at.push(t); }
    expect(at).toEqual([300, 1_000, 2_000, 3_500, 5_500, 8_500, 13_500, 18_500, 23_500]);
    expect(OPERATION_POLL_MS[OPERATION_POLL_MS.length - 1]).toBe(5_000);
  });
});
