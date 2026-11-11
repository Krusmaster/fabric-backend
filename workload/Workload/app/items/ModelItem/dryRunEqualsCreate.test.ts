// n209, item 1: the dry run says what Create will do. An output already built from this plan is "already built from this
// plan, will be skipped" (never red, never "would be updated"); one built from another plan waits for a choice in Create,
// so the dry run says Create will ask (never "updated in place"); the data product's list uses the same words.
import { describe, expect, it } from "vitest";
import { cardTitle, previewLine } from "./buildWords";
import { BuildCard, ManyAnswer } from "./engineClient";
import { productWould } from "./ModelItemViews";

function card(over: Partial<BuildCard>): BuildCard {
  return {
    output: "semantic_model", label: "Semantic model", type: "SemanticModel", name: "shop_sales", dry_run: true, would: "create",
    updates_in_place: true, permissions: { needs: [], missing: null, execute: "none" }, answer: { dry_run: true }, ...over,
  };
}

const differs = { status: "different" as const, words: "built from a different plan (schema Shop, 6 links; now shop, 7 links)", was: null as unknown, now: {} };

describe("the dry run predicts Create", () => {
  it("an output built from this plan will be skipped", () => {
    const c = card({ already_built: true, decision: { action: "skip", words: "Already built from this plan; Create will skip it." } });
    expect(cardTitle(c)).toBe("Semantic model shop_sales: already built from this plan, will be skipped");
  });

  it("an output built from another plan: Create will ask, not 'Update'", () => {
    const c = card({ would: "update", built_from: differs as never, choices: ["update", "new_name"] });
    expect(cardTitle(c)).toBe("Semantic model shop_sales: built from a different plan (schema Shop, 6 links; now shop, 7 links); Create will ask: Update or a new name");
    expect(cardTitle(c)).not.toMatch(/^Update /);
  });

  it("the summary counts only what Create writes as made or updated", () => {
    const a = {
      dry_run: true, refused: 0, order: [], left_out_by_review: [], note: "",
      outputs: [
        card({ output: "silver_notebook", already_built: true }),
        card({ output: "gold_views", already_built: true }),
        card({ output: "semantic_model", would: "update", built_from: differs as never, choices: ["update", "new_name"] }),
        card({ output: "ontology", would: "update" }),
        card({ output: "graphql" }),
      ],
    } as unknown as ManyAnswer;
    expect(previewLine(a)).toBe(
      "This is the dry run: nothing is written yet. Create makes 2 of 5 (1 updated in place); 2 already built from this plan, " +
      "will be skipped; 1 built from another plan, Create will ask: Update or a new name. Nothing is run or scheduled."
    );
  });

  it("the data product's items use the same words", () => {
    expect(productWould({ would: "create", decision: "skip" })).toBe("already built from this plan, will be skipped");
    expect(productWould({ would: "update", decision: "choose" })).toBe("built from another plan: Create will ask");
    expect(productWould({ would: "update", decision: "update" })).toBe("would be updated");
    expect(productWould({ would: "create" })).toBe("would be created");
  });
});
