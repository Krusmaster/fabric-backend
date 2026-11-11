// n209, item 3: a link the rows hold (0 orphans) says so next to Reject, and rejecting it says plainly that the semantic
// model, the API and the ontology will have one relationship fewer (live, 10 November 2026: two holding links were
// rejected and the outputs had 5 relationships instead of 7).
import { describe, expect, it } from "vitest";
import { holdsText, keptLinks, rejectedHoldingText, rejectedRowText } from "./modelWords";
import { ReviewFile, ReviewItem } from "./ModelItemDefinition";

function link(id: string, review: ReviewItem["review"], result?: Record<string, number>, status = "passed"): ReviewItem {
  return { id, type: "relationship", rule: "R1", columns: ["customer_id"], source: "orders", target: "customers",
    target_columns: ["customer_id"], review, ...(result ? { check: { status, result } } : {}) };
}

function file(items: ReviewItem[]): ReviewFile {
  return { format: "krusgraph-review", version: 1, plan_id: "plan-1", source: {}, items } as unknown as ReviewFile;
}

describe("links that hold in the rows", () => {
  it("says so for a passed link with 0 orphans", () => {
    expect(holdsText(link("a", "proposed", { orphans: 0, rows_with_value: 9 }))).toBe(
      "This link holds in the rows: 0 of 9 rows point at nothing.");
    expect(holdsText(link("a", "proposed", { orphans: 0, rows_with_value: 1 }))).toBe(
      "This link holds in the rows: 0 of 1 row points at nothing.");
  });

  it("says nothing for a link with orphans, not checked, stale or a key", () => {
    expect(holdsText(link("a", "proposed", { orphans: 2, rows_with_value: 9 }, "failed"))).toBeUndefined();
    expect(holdsText(link("a", "proposed"))).toBeUndefined();
    expect(holdsText(link("a", "proposed", { orphans: 0, rows_with_value: 9 }, "stale"))).toBeUndefined();
    expect(holdsText({ ...link("a", "proposed", { orphans: 0, rows_with_value: 9 }), type: "key" })).toBeUndefined();
  });

  it("rejecting holding links says the outputs have that many relationships fewer", () => {
    const items = [
      ...["a", "b", "c", "d", "e"].map((id) => link(id, "accepted", { orphans: 0, rows_with_value: 9 })),
      link("f", "rejected", { orphans: 0, rows_with_value: 9 }),
      link("g", "rejected", { orphans: 0, rows_with_value: 4 }),
    ];
    expect(keptLinks(file(items))).toBe(5);
    expect(rejectedHoldingText(file(items))).toBe(
      "You rejected 2 links that hold in the rows. The semantic model, the API and the ontology will have 2 relationships " +
      "fewer: 5 relationships instead of 7. Accept them to keep them.");
    expect(rejectedRowText(items[5])).toBe(
      "Rejected, though it holds in the rows: the semantic model, the API and the ontology will have one relationship fewer.");
  });

  it("one rejected holding link: one relationship fewer", () => {
    const items = [link("a", "accepted", { orphans: 0, rows_with_value: 9 }), link("b", "rejected", { orphans: 0, rows_with_value: 9 })];
    expect(rejectedHoldingText(file(items))).toBe(
      "You rejected a link that holds in the rows. The semantic model, the API and the ontology will have one relationship " +
      "fewer: 1 relationship instead of 2. Accept it to keep it.");
  });

  it("a rejected link with orphans is not called holding", () => {
    const items = [link("a", "rejected", { orphans: 3, rows_with_value: 9 }, "failed")];
    expect(rejectedHoldingText(file(items))).toBeUndefined();
    expect(rejectedRowText(items[0])).toBeUndefined();
  });
});
