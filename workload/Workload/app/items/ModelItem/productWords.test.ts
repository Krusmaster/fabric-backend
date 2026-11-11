// n198: the Data product page's words and rules (productWords.ts), from a fake outputs.json in every state.
import { describe, expect, it } from "vitest";
import { fromParts, toParts } from "./ModelItemDefinition";
import { FRESH, IDS, OUTPUTS, STATUS, UPDATES, WS } from "./productPage.fixture";
import {
  NO_OWNER, NOT_CHECKED, STATE, healthWords, lastRunWords, outOfDateSummary, ownerWords, rowsOf, summary, typedNameOk, withAdopted, withOwner,
  withRemoved,
} from "./productWords";

describe("the rows of the page", () => {
  it("has every state, each with its word and a mark that is not a colour", () => {
    const rows = rowsOf(OUTPUTS, STATUS);
    const by = Object.fromEntries(rows.map((r) => [r.name, r]));
    expect(by.silver_shop.state).toBe("built");
    expect(by.demo_lh_api.state).toBe("missing");
    expect(by.demo_lh_ontology.state).toBe("changed_outside");
    expect(by.demo_lh_app.state).toBe("pending");
    expect(by.demo_lh_agent.state).toBe("failed");
    expect(by.demo_lh_agent.why).toContain("HTTP 403");
    expect(by.demo_lh_report_2.state).toBe("removed");
    expect(by.demo_lh_report_2.why).toBe("Deleted from Fabric on 2026-11-11 08:30 UTC by Anna Berg.");
    expect(new Set(rows.map((r) => r.state))).toEqual(new Set(Object.keys(STATE)));
    for (const s of Object.values(STATE)) {
      expect(s.label.length).toBeGreaterThan(3);
      expect(s.mark).toMatch(/^[^\s]$/);
    }
    expect(by.demo_lh_api.openable).toBe(false);
    expect(by.silver_shop.openable).toBe(true);
  });

  it("without Fabric's answer, says the states are as recorded", () => {
    const rows = rowsOf(FRESH);
    expect(rows).toHaveLength(1);
    expect(rows[0].state).toBe("built");
    expect(rows[0].why).toContain("Fabric has not been read yet");
  });

  it("counts in words, the run, the owner and the health", () => {
    expect(summary(rowsOf(OUTPUTS, STATUS))).toBe("4 built, 1 pending, 1 failed, 1 changed outside Krusgraph, 1 missing, 1 removed");
    expect(lastRunWords(OUTPUTS)).toBe("Last pipeline run: succeeded, demo_lh_pipeline, started 2026-11-10 09:06 UTC.");
    expect(lastRunWords(FRESH)).toContain("none recorded");
    expect(ownerWords(OUTPUTS.product)).toBe("Owner: Anna Berg (anna@example.com) (chosen on 2026-11-10 10:00 UTC by Anna Berg).");
    expect(ownerWords(undefined)).toBe(NO_OWNER);
    expect(healthWords(undefined)).toBe(NOT_CHECKED);
    expect(healthWords(null)).toBe(NOT_CHECKED);
    expect(healthWords({ word: "green", words: "every check passed" })).toBe("Health: green. Every check passed");
  });
});

describe("what the page writes into outputs.json", () => {
  it("keeps the owner with when and by whom, and survives a save and a load", () => {
    const o = withOwner(FRESH, "Sales team", "Anna Berg", "2026-11-11T10:00:00Z", "Shop sales");
    expect(o.product?.owner).toBe("Sales team");
    expect(o.product?.owner_set).toEqual({ at: "2026-11-11T10:00:00Z", by: "Anna Berg" });
    const back = fromParts(toParts({ item: { version: 1, format: "krusgraph-model", view: "product" }, outputs: o }) as never);
    expect(back.outputs.product?.owner).toBe("Sales team");
    expect(back.item.view).toBe("product");
  });

  it("records a removal: out of created and the product, into removed with when and by whom", () => {
    const o = withRemoved({ ...OUTPUTS, product: { ...OUTPUTS.product!, items: [...OUTPUTS.created] } },
      [{ id: IDS.model, type: "SemanticModel", name: "demo_lh_model", workspace: WS, output: "semantic_model", removed_at: "2026-11-11T11:00:00+00:00", by: "Anna Berg" }]);
    expect(o.created.some((c) => c.id === IDS.model)).toBe(false);
    expect(o.product!.items.some((c) => c.id === IDS.model)).toBe(false);
    expect(o.removed!.map((r) => r.id)).toEqual([IDS.oldReport, IDS.model]);
    const back = fromParts(toParts({ item: { version: 1, format: "krusgraph-model", view: "product" }, outputs: o }) as never);
    expect(back.outputs.removed?.[1]).toMatchObject({ id: IDS.model, by: "Anna Berg" });
    expect(rowsOf(back.outputs).find((r) => r.id === IDS.model)?.state).toBe("removed");
  });

  it("adds an adopted leftover once", () => {
    const a = { id: IDS.left, type: "SemanticModel", name: "demo_lh_model4", workspace: WS, output: "semantic_model", adopted_at: "2026-11-11T11:00:00Z", adopted_by: "Anna Berg" };
    const o = withAdopted(withAdopted(FRESH, [a]), [a]);
    expect(o.created.filter((c) => c.id === IDS.left)).toHaveLength(1);
    expect(rowsOf(o).find((r) => r.id === IDS.left)?.state).toBe("built");
  });
});

describe("Update and Retire", () => {
  it("lists what is out of date with the existing Update path; an App only under a new name", () => {
    const by = Object.fromEntries(UPDATES.map((u) => [u.output, u]));
    expect(by.silver_notebook.kind).toBe("up_to_date");
    expect(by.semantic_model.kind).toBe("differs");
    expect(by.semantic_model.actions).toEqual(["update", "new_name"]);
    expect(by.ontology.actions).toEqual(["confirm_update"]);
    expect(by.rayfin_app.actions).toEqual(["new_name"]);
    expect(by.rayfin_app.words).toContain("An App is never updated in place");
    expect(by.graphql.kind).toBe("missing");
    expect(by.report.kind).toBe("stopped");
    expect(outOfDateSummary(UPDATES)).toBe("1 up to date, 3 out of date, 1 not in the workspace, 1 could not be checked.");
  });

  it("deletes only with the data product's name typed exactly", () => {
    expect(typedNameOk("Shop sales", "Shop sales")).toBe(true);
    expect(typedNameOk("  Shop sales ", "Shop sales")).toBe(true);
    for (const wrong of ["shop sales", "Shop", "", "Shop  sales"]) expect(typedNameOk(wrong, "Shop sales")).toBe(false);
    expect(typedNameOk("", "")).toBe(false);
  });
});
