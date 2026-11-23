// @vitest-environment jsdom
// BL58: the row-level security roles the semantic model's dry run proposes (BL46: role_candidates, the card's `roles`)
// as tick boxes on the model's card in the editor. Unticked by default; each shows the role, its column, rule, the
// tables it filters (names only) and whether it fits this model's tables; a role that does not fit is disabled with the
// reason. A ticked role is saved in outputs.json and sent as `roles` on the semantic_model output; without a tick the
// request is exactly as before.
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { MemoryRouter, Route } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BuildCard, ManyAnswer } from "./engineClient";
import type { RolesCard } from "./roleWords";

const ROLES: RolesCard = {
  proposed: [
    { role: "Rows by company code (BUKRS)", column: "BUKRS", rule: "S1", filters: ["sap_t001", "sap_tvko", "sap_vbrk"],
      why: "S1: SAP's company code by its name (BUKRS), in 3 tables", fits: true, added: false },
    { role: "Rows by sales organisation (VKORG)", column: "VKORG", rule: "S2", filters: ["sap_tvko", "sap_vbak", "sap_likp", "sap_vbrk"],
      why: "S2: SAP's sales organisation", fits: true, added: false },
    { role: "Rows by client (MANDT)", column: "MANDT", rule: "S4", filters: ["sap_t001", "sap_kna1"], why: "S4: SAP's client",
      fits: false, added: false, why_not: "its tables sap_kna1 are not in this model" },
  ],
  how: "Proposed, not added: tick a role to add it to the model (the build's semantic_model output takes it as roles, by the column it filters on). Nothing is written until Create.",
  map_table: "security_user_map",
  written: false,
};

function modelCard(over: Partial<BuildCard> = {}): BuildCard {
  return {
    output: "semantic_model", label: "Semantic model", type: "SemanticModel", name: "demo_lh_model", dry_run: true, would: "create",
    updates_in_place: true, permissions: { needs: [], missing: null, execute: "" }, answer: { dry_run: true, summary: {} }, roles: ROLES, ...over,
  } as BuildCard;
}

vi.mock("./engineClient", async (orig) => {
  const real = await orig<typeof import("./engineClient")>();
  const review = { format: "krusgraph-review", version: 1, plan_id: "p1", source: { schema: "sap" }, items: [] as unknown[] };
  return {
    ...real,
    access: vi.fn(async () => null),
    schemas: vi.fn(async () => ({ schemas: [{ schema: "sap", tables: 18 }], preselect: "sap", note: "" })),
    review: vi.fn(async () => ({ review, summary: "", attention: [] as string[], note: "",
      counts: { keys: 0, relationships: 0, review: {}, open_questions: 0 } })),
    buildMany: vi.fn(async (_wc: unknown, _s: unknown, outputs: { kind: string; roles?: string[] }[]) => {
      const sent = outputs.find((o) => o.kind === "semantic_model")?.roles ?? [];
      const roles = { ...ROLES, proposed: ROLES.proposed.map((r) => ({ ...r, added: sent.includes(r.column) })) };
      return { dry_run: true, outputs: [modelCard({ roles })], order: ["semantic_model"], refused: 0, to_decide: 0, left_out_by_review: [],
        note: "Nothing was created or changed in Fabric.", row_check: { checked: 0 } } as unknown as ManyAnswer;
    }),
    buildOne: vi.fn(async () => ({ dry_run: false, outputs: [modelCard({ dry_run: false, status: "done",
      created: [{ id: "m1", type: "SemanticModel", name: "demo_lh_model", workspace: "w", output: "semantic_model" }] })],
      order: ["semantic_model"], refused: 0, left_out_by_review: [] as unknown[], note: "1 of 1 output(s) built.",
      created: [{ id: "m1", type: "SemanticModel", name: "demo_lh_model" }] })),
    finish: vi.fn(async () => ({ outputs: [] as unknown[], flow: null as unknown })),
    itemOperations: vi.fn(async () => ({ operations: [] as unknown[] })),
  };
});

import { ModelItemEditor } from "./ModelItemEditor";
import { EditorErrorBoundary } from "./EditorErrorBoundary";
import { OutputCard } from "./ModelItemViews";
import { cleanChoice, decodeJson, encodeJson, OutputChoice } from "./ModelItemDefinition";
import { toRequests } from "./buildWords";
import { chosenRoles, keepOffered, roleLine, tickedRoles, ticksDiffer, toggleRole, withRoles } from "./roleWords";
import * as engine from "./engineClient";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const MODEL: OutputChoice = { type: "semantic_model", name: "demo_lh_model", enabled: true };

describe("BL58: the request", () => {
  it("without a tick the semantic model's request is exactly as before: no roles key", () => {
    expect(toRequests([MODEL])).toEqual([{ kind: "semantic_model", name: "demo_lh_model" }]);
    expect(toRequests([{ ...MODEL, roles: [] }])).toEqual([{ kind: "semantic_model", name: "demo_lh_model" }]);
    expect(toRequests(withRoles([MODEL], []))).toEqual([{ kind: "semantic_model", name: "demo_lh_model" }]);
    expect(withRoles([MODEL], [])[0]).toEqual(MODEL);
  });

  it("a ticked role is sent as roles on the semantic_model output, and only there", () => {
    const chosen = withRoles([MODEL, { type: "graphql", name: "api", enabled: true }], ["BUKRS"]);
    expect(toRequests(chosen)).toEqual([{ kind: "semantic_model", name: "demo_lh_model", roles: ["BUKRS"] }, { kind: "graphql", name: "api" }]);
    expect(toRequests([{ type: "graphql", name: "api", enabled: true, roles: ["BUKRS"] }])).toEqual([{ kind: "graphql", name: "api" }]);
    expect(toRequests([{ ...MODEL, enabled: false, roles: ["BUKRS"] }])).toEqual([]);
  });

  it("a model on the gold views (the pipeline or the gold views chosen too) is sent without roles: it takes none yet", () => {
    const ticked = { ...MODEL, roles: ["BUKRS"] };
    for (const t of ["pipeline", "gold_views"]) {
      expect(toRequests([ticked, { type: t, name: "x", enabled: true }]).find((r) => r.kind === "semantic_model")).toEqual({ kind: "semantic_model", name: "demo_lh_model" });
      expect(toRequests([ticked, { type: t, name: "x", enabled: false }]).find((r) => r.kind === "semantic_model")).toEqual({ kind: "semantic_model", name: "demo_lh_model", roles: ["BUKRS"] });
    }
    expect(toRequests([ticked, { type: "silver_notebook", name: "s", enabled: true }]).find((r) => r.kind === "semantic_model")?.roles).toEqual(["BUKRS"]);
  });

  it("outputs.json keeps only column names on the model's choice (a hand-edited value reads as none)", () => {
    expect(cleanChoice({ ...MODEL, roles: ["BUKRS", "VKORG", "BUKRS"] }).roles).toEqual(["BUKRS", "VKORG"]);
    expect(cleanChoice({ ...MODEL, roles: ["1=1; DROP"] as string[] })).toEqual(MODEL);
    expect(cleanChoice({ ...MODEL, roles: "BUKRS" as unknown as string[] })).toEqual(MODEL);
    expect(cleanChoice({ type: "graphql", name: "api", enabled: true, roles: ["BUKRS"] })).toEqual({ type: "graphql", name: "api", enabled: true });
  });
});

describe("BL58: the ticks", () => {
  it("are off by default; a role that does not fit cannot be ticked; the order is the dry run's", () => {
    expect(tickedRoles(ROLES, undefined)).toEqual([]);
    expect(toggleRole(ROLES, [], "MANDT", true)).toEqual([]);
    expect(toggleRole(ROLES, ["VKORG"], "BUKRS", true)).toEqual(["BUKRS", "VKORG"]);
    expect(toggleRole(ROLES, ["BUKRS", "VKORG"], "BUKRS", false)).toEqual(["VKORG"]);
    expect(tickedRoles(ROLES, ["MANDT", "BUKRS"])).toEqual(["BUKRS"]);
  });

  it("say when Create would differ from the dry run", () => {
    expect(ticksDiffer(ROLES, undefined)).toBe(false);
    expect(ticksDiffer(ROLES, ["BUKRS"])).toBe(true);
    const shown = { ...ROLES, proposed: ROLES.proposed.map((r) => ({ ...r, added: r.column === "BUKRS" })) };
    expect(ticksDiffer(shown, ["BUKRS"])).toBe(false);
    expect(ticksDiffer(shown, [])).toBe(true);
  });

  it("a role's line: column, rule, the tables it filters and whether it fits; names only", () => {
    expect(roleLine(ROLES.proposed[0])).toBe("Filters on BUKRS (rule S1) in sap_t001, sap_tvko, sap_vbrk. Fits this model's tables.");
    expect(roleLine(ROLES.proposed[2])).toBe("Filters on MANDT (rule S4) in sap_t001, sap_kna1. Cannot be added: its tables sap_kna1 are not in this model.");
  });

  it("after a dry run only the offered roles that fit stay ticked; a model refused for its roles loses them", () => {
    const chosen = withRoles([MODEL], ["BUKRS", "VKORG"]);
    expect(keepOffered(chosen, [modelCard()])).toBe(chosen);
    const fewer = { ...ROLES, proposed: ROLES.proposed.filter((r) => r.column !== "VKORG") };
    expect(chosenRoles(keepOffered(chosen, [modelCard({ roles: fewer })]))).toEqual(["BUKRS"]);
    expect(chosenRoles(keepOffered(chosen, [modelCard({ roles: undefined })]))).toEqual([]);   // e.g. the model reads gold
    const refused = modelCard({ roles: undefined, answer: { error: "roles: 'X' is not a role proposed for this source.", kind: "bad_input" } });
    expect(chosenRoles(keepOffered(chosen, [refused]))).toEqual([]);
    const capacity = modelCard({ roles: undefined, answer: { error: "Fabric is busy", kind: "capacity" } });
    expect(keepOffered(chosen, [capacity])).toBe(chosen);
    expect(keepOffered(chosen, [])).toBe(chosen);
  });
});

describe("BL58: the model card", () => {
  it("shows one labelled, described tick box per role, unticked; the one that does not fit is disabled with its reason", () => {
    const html = renderToStaticMarkup(<OutputCard card={modelCard()} onRoles={() => undefined} />);
    const doc = new DOMParser().parseFromString(html, "text/html");
    expect(doc.querySelector("fieldset.kg-roles legend")?.textContent).toBe("Row-level security roles (proposed, off by default)");
    const boxes = Array.from(doc.querySelectorAll<HTMLInputElement>(".kg-role input[type=checkbox]"));
    expect(boxes.length).toBe(3);
    expect(boxes.every((b) => !b.hasAttribute("checked"))).toBe(true);
    for (const b of boxes) {
      const label = doc.querySelector(`label[for="${b.id}"]`)?.textContent;
      const desc = doc.getElementById(b.getAttribute("aria-describedby") ?? "")?.textContent;
      expect(label).toMatch(/^Rows by /);
      expect(desc).toMatch(/^Filters on [A-Z]+ \(rule S\d\) in /);
    }
    expect(boxes.map((b) => b.hasAttribute("disabled"))).toEqual([false, false, true]);
    expect(doc.querySelector('[data-role="MANDT"]')?.textContent).toMatch(/Cannot be added: its tables sap_kna1 are not in this model/);
    expect(doc.body.textContent).toMatch(/security_user_map/);
  });

  it("after Create the roles are listed as added or not, without boxes", () => {
    const done = modelCard({ dry_run: false, roles: { ...ROLES, proposed: ROLES.proposed.map((r) => ({ ...r, added: r.column === "BUKRS" })) } });
    const html = renderToStaticMarkup(<OutputCard card={done} />);
    expect(html).not.toMatch(/type="checkbox"/);
    expect(html).toMatch(/Rows by company code \(BUKRS\): added to the model/);
    expect(html).toMatch(/Rows by sales organisation \(VKORG\): not added/);
  });

  it("a model card without proposed roles (the shop) shows nothing new", () => {
    const html = renderToStaticMarkup(<OutputCard card={modelCard({ roles: undefined })} onRoles={() => undefined} />);
    expect(html).not.toMatch(/kg-roles|Row-level security/);
  });
});

// ------------------------------------------------------------------ the real editor -----------------------------------

const WS = "11111111-1111-1111-1111-111111111111";
const LH = "22222222-2222-2222-2222-222222222222";
const ITEM = "33333333-3333-3333-3333-333333333333";
const part = (path: string, v: unknown) => ({ path, payload: encodeJson(v), payloadType: "InlineBase64" });

function client() {
  return {
    itemCrud: {
      getItem: vi.fn(async () => ({ item: { id: ITEM, workspaceId: WS, displayName: "Model 1", type: "Org.Krusgraph.Model" } })),
      getItemDefinition: vi.fn(async () => ({ definition: { parts: [
        part("item.json", { version: 1, format: "krusgraph-model", view: "review" }),
        part("source.json", { version: 1, platform: "fabric", workspaceId: WS, itemId: LH, itemType: "Lakehouse", displayName: "demo_lh", schema: "sap" }),
        part("outputs.json", { version: 1, outputs: [MODEL], created: [] }),
        part("review.json", { format: "krusgraph-review", version: 1, plan_id: "p1", source: {}, items: [] }),
      ] } })),
      updateItemDefinition: vi.fn(async () => ({})),
    },
    datahub: { openDialog: vi.fn() },
    notification: { open: vi.fn(async () => ({})) },
    navigation: { navigate: vi.fn() },
  };
}

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  vi.clearAllMocks();
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

async function flush() {
  for (let i = 0; i < 8; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}
function button(text: RegExp): HTMLButtonElement {
  const b = Array.from(host.querySelectorAll("button")).find((x) => text.test((x.textContent ?? "").trim()));
  if (!b) throw new Error(`no button ${text} in: ${host.textContent}`);
  return b as HTMLButtonElement;
}
const box = (col: string) => host.querySelector(`[data-role="${col}"] input[type="checkbox"]`) as HTMLInputElement;
const calls = (f: unknown) => (f as { mock: { calls: unknown[][] } }).mock.calls;

async function toDryRun(wc: ReturnType<typeof client>) {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[`/ModelItem-editor/${ITEM}`]}>
        <Route path="/ModelItem-editor/:itemObjectId">
          <EditorErrorBoundary><ModelItemEditor workloadClient={wc as never} /></EditorErrorBoundary>
        </Route>
      </MemoryRouter>
    );
  });
  await flush();
  await act(async () => { button(/^Next$/).click(); });
  await flush();
  await act(async () => { button(/^Dry run$/).click(); });
  await flush();
}

describe("BL58: in the editor", () => {
  it("without a tick, the dry run and Create send the model exactly as before", async () => {
    const wc = client();
    await toDryRun(wc);
    expect(calls(engine.buildMany)[0][2]).toEqual([{ kind: "semantic_model", name: "demo_lh_model" }]);
    expect(box("BUKRS").checked).toBe(false);
    expect(box("MANDT").disabled).toBe(true);
    await act(async () => { button(/^Create/).click(); });
    await flush();
    expect(calls(engine.buildOne)[0][2]).toEqual({ kind: "semantic_model", name: "demo_lh_model" });
  });

  it("a tick is saved in outputs.json, the dry run again shows it added, and Create sends roles", async () => {
    const wc = client();
    await toDryRun(wc);
    await act(async () => { box("BUKRS").click(); });
    await flush();
    expect(box("BUKRS").checked).toBe(true);
    const saved = calls(wc.itemCrud.updateItemDefinition).map((c) => (c[0] as { payload: { definition: { parts: { path: string; payload: string }[] } } }).payload.definition.parts)
      .map((ps) => decodeJson<{ outputs: OutputChoice[] }>(ps.find((p) => p.path === "outputs.json")!.payload));
    expect(saved[saved.length - 1].outputs.find((o) => o.type === "semantic_model")?.roles).toEqual(["BUKRS"]);
    expect(host.querySelector('.kg-roles [role="status"]')?.textContent).toMatch(/Choose Dry run again/);
    await act(async () => { button(/^Dry run again$/).click(); });
    await flush();
    expect(calls(engine.buildMany)[1][2]).toEqual([{ kind: "semantic_model", name: "demo_lh_model", roles: ["BUKRS"] }]);
    expect(host.querySelector('.kg-roles [role="status"]')?.textContent).toBe("");
    expect(box("BUKRS").checked).toBe(true);
    await act(async () => { button(/^Create/).click(); });
    await flush();
    expect(calls(engine.buildOne)[0][2]).toEqual({ kind: "semantic_model", name: "demo_lh_model", roles: ["BUKRS"] });
  });
});
