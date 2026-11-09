// n180: "already built" means built from this plan (the founder's re-run of 9 November 2026, 12:14 CET). The engine's
// cards for items built from another plan or with no plan recorded (tests/test_workload_plans.py), here in words: the
// title says which plan, Update is a dry run first, the counts are what the item holds and never a zero.
import { describe, expect, it } from "vitest";
import { cardFacts, cardTitle, existingFacts, mergeCreated, needsChoice, newNameFor, refreshWords, resultLine, runUpdate } from "./buildWords";
import { BuildCard, ManyAnswer, updateBody } from "./engineClient";
import { emptyDefinition, fromParts, toParts } from "./ModelItemDefinition";

const WS = "11111111-2222-3333-4444-555555555555";
const NOW = { plan_id: "plan-aaaaaaaaaaaa", schema_fingerprint: "sha256:1111222233334444", schema: "shop", links: 7 };
const WAS = { plan_id: "plan-0123456789ab", schema_fingerprint: "sha256:00112233aabbccdd", schema: "Shop", links: 6 };
const OLD = { type: "Notebook", id: "nb-old", name: "demo_lh_silver", workspace: WS, output: "silver_notebook" };

function card(over: Partial<BuildCard>): BuildCard {
  return {
    output: "silver_notebook", label: "Silver notebook", type: "Notebook", name: "demo_lh_silver", dry_run: false, would: "update",
    updates_in_place: true, permissions: { needs: [], missing: null, execute: "none" }, answer: { dry_run: false }, ...over,
  };
}

const different = card({
  built_from: { status: "different", was: WAS, now: NOW, words: "built from a different plan (schema Shop, 6 links; now shop, 7 links)" },
  choices: ["update", "new_name"], existing_items: [OLD], existing: { cells: 9 },
});
const unknown = card({
  built_from: { status: "unknown", was: null, now: NOW, words: "built by Krusgraph, plan unknown (now shop, 7 links)" },
  choices: ["update", "new_name"], existing_items: [OLD],
});

function answer(c: BuildCard, created: ManyAnswer["created"] = []): ManyAnswer {
  return { dry_run: c.dry_run, outputs: [c], order: [c.output], left_out_by_review: [], refused: 0, note: "", created };
}

describe("cards of items built from another plan", () => {
  it("say which plan in the title, and the same plan stays 'already built'", () => {
    expect(cardTitle(different)).toBe("Silver notebook demo_lh_silver: built from a different plan (schema Shop, 6 links; now shop, 7 links)");
    expect(cardTitle(unknown)).toBe("Silver notebook demo_lh_silver: built by Krusgraph, plan unknown (now shop, 7 links)");
    expect(cardTitle(card({ already_built: true, would: "create" }))).toBe("Silver notebook demo_lh_silver: already built");
    expect(needsChoice(different) && needsChoice(unknown)).toBe(true);
    expect(needsChoice({ ...different, dry_run: true })).toBe(false);
  });

  it("show what the existing item holds, or no count at all: never a zero", () => {
    expect(cardFacts(different)).toEqual(["Holds 9 notebook cells"]);
    expect(cardFacts(unknown)).toEqual([]);
    expect(cardFacts(card({ already_built: true, output: "report", existing: { pages: 1, visuals: 6 } }))).toEqual(["Holds 1 page with 6 visuals"]);
    expect(cardFacts(card({ already_built: true, output: "data_agent", existing: { questions: 4, data_sources: 1 } })))
      .toEqual(["Holds 4 example questions over 1 data source"]);
    expect(cardFacts(card({ already_built: true, output: "gold_views", existing: { cells: 3, views: 5 } }))).toEqual(["Holds 5 gold views"]);
    // the n179 cards said "0 silver table(s)", "0 visual(s)", "0 table(s) selected" for items that had them
    for (const kind of ["silver_notebook", "gold_views", "report", "data_agent", "semantic_model"] as const) {
      const facts = cardFacts(card({ already_built: true, output: kind, answer: { dry_run: false, already_built: true } }));
      expect(facts.join(" ")).not.toMatch(/\b0 /);
      expect(existingFacts(kind, { cells: 0, pages: 0, visuals: 0, questions: 0, tables: 0 })).toEqual([]);
    }
  });

  it("the result line asks for a choice and says nothing was written", () => {
    const line = resultLine(answer(different));
    expect(line).toContain("nothing was written");
    expect(line).toContain("Update (a dry run first) or a new name");
  });

  it("a new name is free of the existing item's and the taken names", () => {
    expect(newNameFor(different, ["demo_lh_silver_2"])).toBe("demo_lh_silver_3");
  });
});

describe("Update: the dry run first", () => {
  it("from the choice card the first call is a dry run and nothing is kept; its card's confirmation then updates", async () => {
    const calls: { dryRun: boolean; confirm?: string }[] = [];
    const dry = card({ dry_run: true, would: "update", built_from: different.built_from, confirm_update: "upd-0011223344556677" });
    const done = card({ would: "update", created: [{ ...OLD, plan: NOW }] });
    const send = async (dryRun: boolean, confirm?: string) => {
      calls.push({ dryRun, confirm });
      return dryRun ? answer(dry) : answer(done, done.created);
    };
    const first = await runUpdate(different, send);
    expect(calls).toEqual([{ dryRun: true, confirm: undefined }]);
    expect(first.created).toEqual([]);
    expect(first.card.confirm_update).toBe("upd-0011223344556677");
    const second = await runUpdate(first.card, send);
    expect(calls[1]).toEqual({ dryRun: false, confirm: "upd-0011223344556677" });
    expect(second.created[0].plan).toEqual(NOW);
  });

  it("the request body sends update and, only after the dry run, the confirmation", () => {
    const src = { workspace: WS, source: "demo_lh", source_name: "demo_lh", schema: "shop" };
    const o = { kind: "silver_notebook" as const, name: "demo_lh_silver" };
    const rv = emptyDefinition().review as never;
    const dry = updateBody(src, o, [o], rv, [], true);
    expect(dry).toMatchObject({ dry_run: true, update: ["silver_notebook"], only: ["silver_notebook"] });
    expect(dry).not.toHaveProperty("confirm");
    expect(() => updateBody(src, o, [o], rv, [], false)).toThrow(/dry run/);
    expect(updateBody(src, o, [o], rv, [], false, "upd-1")).toMatchObject({ dry_run: false, confirm: { silver_notebook: "upd-1" } });
  });
});

describe("outputs.json keeps the plan of each item", () => {
  it("merged, saved and read back with its plan", () => {
    const created = mergeCreated([{ ...OLD }], [{ ...OLD, plan: NOW }, { ...OLD, id: "nb-new", name: "x", plan: NOW }]);
    expect(created.map((c) => c.plan)).toEqual([NOW, NOW]);
    const def = emptyDefinition();
    const back = fromParts(toParts({ ...def, outputs: { ...def.outputs, created } }) as never);
    expect(back.outputs.created[0].plan).toEqual(NOW);
  });
});

// n180, addition 4: the semantic model's one refresh on its card (tests/test_workload_refresh.py for the engine)

describe("the semantic model's refresh on its card", () => {
  const model = (refresh: BuildCard["refresh"]) => card({ output: "semantic_model", label: "Semantic model", name: "demo_lh_model3", refresh });
  it("says what the dry run plans and how Create's refresh ended", () => {
    expect(refreshWords(model({ status: "planned" }))).toBe("Create refreshes the model once; nothing else is run or scheduled.");
    expect(refreshWords(model({ status: "planned", scope: "Dataset.ReadWrite.All" }))).toContain("lacks Dataset.ReadWrite.All");
    expect(refreshWords(model({ status: "refreshed" }))).toMatch(/^Refreshed once/);
    expect(refreshWords(model({ status: "refreshing", reason: "still running after 120 s" }))).toMatch(/^Refreshing: still running after 120 s/);
    expect(refreshWords(model({ status: "failed", reason: "ModelRefreshFailed_CredentialsNotSpecified" })))
      .toBe("Refresh failed: ModelRefreshFailed_CredentialsNotSpecified. Refresh the model once in the portal before opening the report.");
    expect(refreshWords(model({ status: "not_run", reason: "Your sign-in does not carry Dataset.ReadWrite.All." }))).toMatch(/^Not refreshed: .*Dataset\.ReadWrite\.All/);
    expect(refreshWords(card({}))).toBeUndefined();
  });
});
