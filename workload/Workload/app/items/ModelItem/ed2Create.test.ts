// ED2: Gustav's editor test of 21 November 2026, part 2. The build order, the dry run's blocker, Fix and finish, the
// same error once, the freshest review, this build's items and earlier builds, one owner and one plan sentence.
import { describe, expect, it } from "vitest";
import {
  OLDER_REVIEW_LINE, blockedBy, createBlocker, dependsOn, finishLabel, freshestReview, inSentence, itemStatus, ownerLine,
  planLine, retryState, sameErrorLine, sharedErrors, splitBuilds, staleLine, toFinish, waitingCard,
} from "./ed2Create";
import type { BuildCard, ManyAnswer, OutputKind, OutputRequest } from "./engineClient";
import type { ReviewFile } from "./ModelItemDefinition";

const SIX: OutputRequest[] = [
  { kind: "data_agent", name: "shop_agent" },
  { kind: "report", name: "shop_report" },
  { kind: "semantic_model", name: "shop_model" },
  { kind: "pipeline", name: "shop_pipeline" },
  { kind: "gold_views", name: "shop_gold" },
  { kind: "silver_notebook", name: "shop_silver" },
];

function card(kind: OutputKind, extra: Partial<BuildCard> = {}): BuildCard {
  return { output: kind, label: kind, type: "", name: `shop_${kind}`, dry_run: false, would: "create", updates_in_place: true,
    permissions: { needs: [], missing: null, execute: "" }, status: "done", ...extra } as BuildCard;
}

describe("build order", () => {
  it("lakehouse -> silver -> gold -> pipeline -> model -> report and agent", () => {
    const of = (k: OutputKind) => dependsOn(SIX.find((o) => o.kind === k)!, SIX).sort();
    expect(of("silver_notebook")).toEqual([]);
    expect(of("gold_views")).toEqual(["silver_notebook"]);
    expect(of("pipeline")).toEqual(["gold_views", "silver_notebook"]);
    expect(of("semantic_model")).toEqual(["gold_views", "pipeline", "silver_notebook"]);
    expect(of("report")).toEqual(["semantic_model"]);
    expect(of("data_agent")).toEqual(["gold_views", "pipeline", "silver_notebook"]);
    expect(dependsOn({ kind: "graphql" }, SIX)).toEqual([]);
    expect(dependsOn({ kind: "report", model: "existing" }, SIX)).not.toContain("semantic_model");
  });

  it("silver failed: gold is not sent and says once it waits for silver", () => {
    const cards: Partial<Record<OutputKind, BuildCard>> = { silver_notebook: card("silver_notebook", { answer: { error: "boom" } }) };
    const dep = blockedBy(SIX.find((o) => o.kind === "gold_views")!, SIX, (k) => cards[k]);
    expect(dep).toBe("silver_notebook");
    const w = waitingCard(card("gold_views"), dep!);
    expect(w.refusal?.error).toBe("Waiting for silver: not sent, because silver was not built.");
    expect(itemStatus(w)).toBe("waiting for silver");
    expect(retryState(w)).toEqual({ can: false, why: "Built by Fix and finish once silver is built." });
  });
});

describe("the same error once", () => {
  it("one long error on three outputs is said once; each card points above", () => {
    const err = { error: "Fabric answered HTTP 403 for the workspace: no permission.", hint: "Ask for Contributor.", kind: "consent" };
    const cards = [card("silver_notebook", { refusal: err }), card("gold_views", { refusal: err }), card("pipeline", { refusal: err }),
      card("semantic_model", { created: [] })];
    const shared = sharedErrors(cards);
    expect(shared).toHaveLength(1);
    expect(shared[0].outputs).toEqual(["silver_notebook", "gold_views", "pipeline"]);
    expect(sameErrorLine(cards[1], shared)).toBe("Not built: the error is said once, above.");
    expect(sameErrorLine(cards[3], shared)).toBeUndefined();
  });
});

describe("the dry run's blocker", () => {
  const dry = (outputs: BuildCard[]): ManyAnswer =>
    ({ dry_run: true, outputs, order: [], left_out_by_review: [], refused: outputs.filter((c) => c.refusal).length, note: "" }) as ManyAnswer;

  it("Create may start when no card is refused", () => {
    expect(createBlocker(dry([card("silver_notebook"), card("graphql")]))).toBeUndefined();
  });

  it("a name taken: Create off, one line, Use free names", () => {
    const b = createBlocker(dry([card("graphql", { label: "API for GraphQL",
      refusal: { error: "GraphQLApi 'shop_api' already exists in this workspace and was not built by this Krusgraph Model; nothing was written.", kind: "already_exists" } })]));
    expect(b?.fix).toBe("free_names");
    expect(b?.button).toBe("Use free names");
    expect(b?.line.startsWith("Create is off: GraphQLApi 'shop_api' already exists")).toBe(true);
  });

  it("a missing permission: leave that output out", () => {
    const b = createBlocker(dry([card("data_agent", { label: "Data agent", refusal: { error: "Needs a permission.", kind: "consent" } }), card("graphql")]));
    expect(b?.fix).toBe("leave_out");
    expect(b?.button).toBe("Leave out the data agent");
    expect(b?.outputs).toEqual(["data_agent"]);
  });

  it("labels keep their case inside a sentence: API for GraphQL", () => {
    expect(inSentence("API for GraphQL")).toBe("API for GraphQL");
    expect(inSentence("Silver notebook")).toBe("silver notebook");
  });
});

describe("Fix and finish", () => {
  it("only what is missing, in build order; what was built is not sent again", () => {
    const cards = [
      card("report", { refusal: { error: "Fabric did not give the definition", kind: "source_not_ready" } }),
      card("silver_notebook", { created: [{ type: "Notebook", id: "1", name: "s", workspace: "w" }] }),
      waitingCard(card("gold_views"), "silver_notebook"),
      card("semantic_model", { status: "lost" }),
      card("pipeline", { already_built: true }),
    ];
    expect(toFinish(cards).map((c) => c.output)).toEqual(["gold_views", "semantic_model", "report"]);
    expect(finishLabel(3)).toBe("Fix and finish (3 not built)");
  });

  it("Try again is offered where a retry can work, else the reason", () => {
    expect(retryState(card("report", { refusal: { error: "404", kind: "source_not_ready" } }))).toEqual({ can: true });
    expect(retryState(card("graphql", { refusal: { error: "taken", kind: "already_exists" } })).can).toBe(false);
    expect(retryState(card("graphql", { refusal: { error: "taken", kind: "already_exists" } })).why).toContain("choose another name");
    expect(retryState(card("graphql", { created: [] }))).toEqual({ can: false });
  });
});

describe("the result's items", () => {
  it("this build's items, and earlier builds apart", () => {
    const items = [{ id: "a", name: "shop_silver" }, { id: "b", name: "shop_silver9" }, { id: "c", name: "shop_model" }];
    const s = splitBuilds(items, [{ type: "Notebook", id: "a", name: "shop_silver", workspace: "w" }, { type: "SemanticModel", id: "c", name: "shop_model", workspace: "w" }]);
    expect(s.now.map((x) => x.id)).toEqual(["a", "c"]);
    expect(s.earlier.map((x) => x.id)).toEqual(["b"]);
  });
});

describe("one owner and one plan sentence", () => {
  it("the owner is said the same everywhere and the plan is never '?'", () => {
    expect(ownerLine("someone@example.com")).toBe("Owner: someone@example.com. Change it on the Choose step.");
    expect(ownerLine(null)).not.toContain("nobody");
    expect(planLine({ plan_id: null })).toBe("");
    expect(planLine({ plan_id: "plan-1", schema_fingerprint: "sha256:ab" })).toBe("Plan plan-1, schema sha256:ab.");
  });
});

describe("the freshest review", () => {
  const rv = (at: string): ReviewFile => ({ format: "krusgraph-review", version: 1, plan_id: "plan-1", source: {},
    items: [{ id: "key:orders", type: "key", review: "accepted", check: { status: "passed", checked_at: at } } as never] });

  it("a re-read of the old saved review never replaces the check the person just ran", () => {
    const now = rv("2026-11-21T12:44:00Z"), old = rv("2026-11-11T20:23:00Z");
    expect(freshestReview(now, old)).toEqual({ review: now, kept: "current" });
    expect(freshestReview(old, now)).toEqual({ review: now, kept: "incoming" });
    expect(staleLine(old, now)).toBe(OLDER_REVIEW_LINE);
    expect(staleLine(now, now)).toBeUndefined();
  });
});
