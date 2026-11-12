// n225, from the founder's phone test in Fabric of 12 November 2026 (package 1.0.1074): after a Create that built 8
// outputs the Data product page said "Plan id: not recorded", listed "2 built", and showed "Health: red. 7 failed in the
// latest run (checked 2026-11-11 19:23 UTC)", a day-old result of another run, as current.
import { describe, expect, it } from "vitest";
import { OutputsDefinition } from "./ModelItemDefinition";
import { NO_ID_SAVED, OWNER_WHY, createdAtOf, healthFor, otherPlanRows, planOf, planWords, rowsOf, withPlan } from "./productWords";
import { saveWithRetry, savedWords } from "./saveState";
import { migrate } from "./ModelItemDefinition";
import { OUTPUTS } from "./productPage.fixture";

const WS = "0f0f0f0f-0000-4000-8000-000000000001";
const item = (n: number, plan?: string) => ({ id: `00000000-0000-4000-8000-0000000000${String(n).padStart(2, "0")}`, type: "Notebook",
  name: `nb_${n}`, workspace: WS, output: "silver_notebook", ...(plan ? { plan: { plan_id: plan } } : {}) });

describe("the plan of the latest Create", () => {
  it("is recorded by every Create, even with no data product, and kept through a save", () => {
    const o: OutputsDefinition = { version: 1, outputs: [], created: [item(1, "plan-aa")] };
    const got = withPlan(o, "plan-bb", "2026-11-12T09:05:00.000Z");
    expect(got.plan).toEqual({ plan_id: "plan-bb", at: "2026-11-12T09:05:00.000Z" });
    expect(planOf(got)).toBe("plan-bb");
    expect(planWords(got, "plan-bb")).toBe("Plan id: plan-bb (the plan of the Create of 2026-11-12 09:05 UTC).");
    expect(migrate({ item: { version: 1, format: "krusgraph-model", view: "product" }, outputs: got } as never).outputs.plan).toEqual(got.plan);
  });

  it("moves the stored product to the new plan, so its health is read for this plan", () => {
    const got = withPlan({ ...OUTPUTS }, "plan-ffff0000", "2026-11-12T09:05:00.000Z");
    expect(got.product?.plan.plan_id).toBe("plan-ffff0000");
    expect(got.product?.plan.schema_fingerprint).toBeUndefined();     // that fingerprint was the older plan's
  });

  it("falls back to the review's plan, then the newest mark; says when none is known", () => {
    const o: OutputsDefinition = { version: 1, outputs: [], created: [item(1, "plan-aa"), item(2, "plan-cc")] };
    expect(planOf(o, "plan-rr")).toBe("plan-rr");
    expect(planOf(o)).toBe("plan-cc");
    expect(planWords({ version: 1, outputs: [], created: [] }, undefined)).toBe("Plan id: not recorded yet. The next Create records it.");
  });
});

describe("the items: every item of this plan, never another plan's", () => {
  const o: OutputsDefinition = {
    version: 1, outputs: [], created: [item(1, "plan-old"), item(2, "plan-new"), item(3, "plan-new"), item(4)],
    last_create: { at: "2026-11-12T09:05:00.000Z", item: "m", outputs: [
      { output: "silver_notebook", label: "Silver notebook", name: "nb_2", state: "created" },
      { output: "ontology", label: "Ontology", name: "shop_ontology", state: "created" },
      { output: "report", label: "Report", name: "shop_report", state: "failed", reason: "no" },
    ] },
  };

  it("lists old and new items of the plan, and what the latest Create built whose id was not saved", () => {
    const rows = rowsOf(o, undefined, "plan-new");
    expect(rows.filter((r) => r.id).map((r) => r.name)).toEqual(["nb_2", "nb_3"]);
    const unsaved = rows.find((r) => r.name === "shop_ontology")!;
    expect([unsaved.state, unsaved.why, unsaved.openable]).toEqual(["built", NO_ID_SAVED, false]);
    expect(rows.find((r) => r.name === "shop_report")?.state).toBe("failed");
  });

  it("lists another plan's items, and items with no plan, apart", () => {
    expect(otherPlanRows(o, undefined, "plan-new").map((r) => [r.name, r.why])).toEqual([
      ["nb_1", "Built from another plan (plan-old)."], ["nb_4", "Built before plans were recorded."]]);
  });

  it("without a plan, lists everything as before", () => {
    expect(rowsOf(o).filter((r) => r.id)).toHaveLength(4);
    expect(otherPlanRows(o, undefined, undefined)).toEqual([]);
  });
});

describe("health: the run it came from, and never an old run as current", () => {
  const red = { word: "red", words: "7 failed in the latest run", checked_at: "2026-11-11T19:23:00Z", run_id: "r-17", plan_id: "plan-new" };

  it("says the run and its date when it is newer than the Create", () => {
    expect(healthFor(red, "plan-new", "2026-11-11T08:00:00Z")).toBe("Health: red. 7 failed in the latest run (run r-17, checked 2026-11-11 19:23 UTC).");
  });

  it("says not checked since this Create when the run is older (the founder's case)", () => {
    expect(healthFor(red, "plan-new", "2026-11-12T09:05:00Z")).toBe(
      "Health: not checked since this Create (2026-11-12 09:05 UTC). The latest result is from run r-17, checked 2026-11-11 19:23 UTC: "
      + "red. 7 failed in the latest run.");
  });

  it("says so when the result is another plan's", () => {
    expect(healthFor({ ...red, plan_id: "plan-old" }, "plan-new", undefined)).toMatch(
      /^Health: not checked since this Create\. The latest health result is for another plan \(plan-old\), run r-17/);
  });

  it("no result: not checked", () => {
    expect(healthFor(null, "plan-new", "2026-11-12T09:05:00Z")).toBe("Health: not checked yet since this Create.");
    expect(healthFor({ word: "not checked yet" }, "plan-new", undefined)).toBe("Health: not checked yet.");
  });

  it("the Create's time is the stored finish's", () => {
    expect(createdAtOf(OUTPUTS)).toBe("2026-11-10T09:05:00.000Z");
  });
});

describe("Saved, Saving, Not saved", () => {
  const instant = async (): Promise<void> => undefined;

  it("a save Fabric did not confirm is tried again, and its outcome said", async () => {
    let n = 0;
    expect(await saveWithRetry(async () => (++n === 3 ? { ok: true } : undefined), () => true, [1, 1, 1], instant)).toEqual({ outcome: "saved", tries: 3 });
    expect(await saveWithRetry(async (): Promise<unknown> => { throw new Error("429"); }, () => true, [1, 1], instant)).toEqual({ outcome: "failed", tries: 3 });
  });

  it("an older copy is not sent again once a newer one waits", async () => {
    let newest = true;
    const sent: number[] = [];
    const got = await saveWithRetry(async (): Promise<unknown> => { sent.push(1); newest = false; return undefined; }, () => newest, [1, 1], instant);
    expect(got).toEqual({ outcome: "superseded", tries: 1 });
    expect(sent).toHaveLength(1);
  });

  it("in words, with a mark that is not a colour", () => {
    expect(savedWords(undefined).words).toBe("Saved: this list is what this item keeps in Fabric.");
    expect(savedWords({ state: "saved", at: "2026-11-12T09:06:00.000Z" }).words).toBe("Saved in this item in Fabric (2026-11-12 09:06 UTC).");
    const no = savedWords({ state: "failed", at: "2026-11-12T09:06:00.000Z", tries: 4 });
    expect([no.mark, no.tone]).toEqual(["✕", "bad"]);
    expect(no.words).toMatch(/^Not saved: Fabric did not confirm the save after 4 tries/);
  });

  it("the owner says why it matters, in one sentence", () => {
    expect(OWNER_WHY.split(". ").length).toBe(1);
  });
});
