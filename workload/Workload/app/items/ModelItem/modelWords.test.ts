// n173: the Model editor's words and Accept all. The review file has the shape fabric_backend/review.py writes for the
// synthetic shop schema (fabric_backend/seed.py): names, rules, decisions and counts, never a row value.
import { describe, expect, it } from "vitest";
import { ReviewFile, ReviewItem } from "./ModelItemDefinition";
import { WORDS_WITH_ARGUMENTS } from "./cardMap.generated";
import {
  RULE_MEANING,
  acceptAll,
  acceptAllTargets,
  checkLines,
  checkText,
  dryRunCheckLine,
  hasArgumentSyntax,
  itemText,
  questions,
  ruleMeaning,
  sayings,
  summaryLines,
  totalsOf,
} from "./modelWords";

const passed = (extra: Record<string, number>) => ({ status: "passed", checked_at: "2026-11-08T21:40Z", result: extra });
const failed = (extra: Record<string, number>) => ({ status: "failed", checked_at: "2026-11-08T21:40Z", result: extra });

function shop(): ReviewFile {
  const items: ReviewItem[] = [
    { id: "key:customers", type: "key", table: "customers", columns: ["customer_id"], rule: "K2", review: "proposed" },
    { id: "key:orders", type: "key", table: "orders", columns: ["order_id"], rule: "K2", review: "accepted" },
    { id: "key:order_items", type: "key", table: "order_items", columns: ["order_id", "line_no"], rule: "K5", review: "rejected" },
    { id: "rel:orders.customer_id>customers", type: "relationship", source: "orders", columns: ["customer_id"],
      target: "customers", target_columns: ["customer_id"], rule: "R1", review: "proposed" },
    { id: "rel:orders.ship_to_id>addresses", type: "relationship", source: "orders", columns: ["ship_to_id"],
      target: "addresses", target_columns: ["address_id"], rule: "R5", review: "open" },
  ];
  return {
    format: "krusgraph-review", version: 1, plan_id: "plan-1", source: { platform: "fabric", source: "demo_lh", schema: "shop" },
    items,
    snapshot: {
      tables: {
        customers: { columns: { customer_id: "int", name: "string" }, key: ["customer_id"] },
        orders: { columns: { order_id: "int", customer_id: "int", ship_to_id: "int" }, key: ["order_id"] },
        order_items: { columns: { order_id: "int", line_no: "int" }, key: ["order_id", "line_no"] },
        addresses: { columns: { address_id: "int" }, key: ["address_id"] },
        audit_log: { columns: { event: "string", customer_id: "int", happened_at: "timestamp" }, key: [] },
      },
    },
    open_questions: [
      { about: "key:audit_log", question: "Does audit_log have a key? The rules found none; give one with keys, or keep it query only (it can reference others, nothing can reference it)." },
    ],
  };
}

function checked(): ReviewFile {
  const rv = shop();
  rv.items[0].check = passed({ rows: 50, nulls: 0, distinct: 50 });
  rv.items[1].check = failed({ rows: 12, nulls: 0, distinct: 10 });
  rv.items[3].check = failed({ rows_with_value: 12, orphans: 3 });
  rv.items[4].check = passed({ rows_with_value: 12, orphans: 0 });
  return rv;
}

describe("Accept all", () => {
  it("accepts every item still suggested or waiting, and never overturns a rejection", () => {
    const rv = shop();
    expect(acceptAllTargets(rv)).toEqual(["key:customers", "rel:orders.customer_id>customers", "rel:orders.ship_to_id>addresses"]);
    const after = acceptAll(rv);
    expect(after.items.map((it) => it.review)).toEqual(["accepted", "accepted", "rejected", "accepted", "accepted"]);
    expect(rv.items[0].review).toBe("proposed"); // the input is not changed
    expect(acceptAllTargets(after)).toEqual([]);
  });

  it("Accept all that passed the check takes only what passed", () => {
    const rv = checked();
    expect(acceptAllTargets(rv, true)).toEqual(["key:customers", "rel:orders.ship_to_id>addresses"]);
    const after = acceptAll(rv, true);
    const by = Object.fromEntries(after.items.map((it) => [it.id, it.review]));
    expect(by["key:customers"]).toBe("accepted");
    expect(by["rel:orders.customer_id>customers"]).toBe("proposed"); // failed: stays for the person
    expect(by["key:order_items"]).toBe("rejected");
  });

  it("before a check, Accept all that passed has nothing to take", () => {
    expect(acceptAllTargets(shop(), true)).toEqual([]);
  });
});

describe("the check in words", () => {
  it("counts passed, failed and not checked from the review file", () => {
    const t = totalsOf(checked());
    expect(t.checked).toBe(4);
    expect(t.keys).toEqual({ passed: 1, failed: 1, stale: 0, not_checked: 1 });
    expect(t.relationships).toEqual({ passed: 1, failed: 1, stale: 0, not_checked: 0 });
    expect(t.checked_at).toBe("2026-11-08T21:40Z");
  });

  it("says orphans and duplicates as a person would", () => {
    const rv = checked();
    expect(checkText(rv.items[0])).toBe("Passed the check.");
    expect(checkText(rv.items[1])).toBe("Failed: 2 duplicates.");
    expect(checkText(rv.items[3])).toBe("Failed: 3 rows point at nothing.");
    expect(checkText(rv.items[2])).toBe("Not checked yet.");
    expect(checkLines(rv)).toEqual([
      "1 of 2 keys is unique in the rows.",
      "1 of 2 links holds; 1 has rows that point at nothing.",
      "1 item was not checked.",
    ]);
  });

  it("the dry run says what passed after a check, and what to do before one", () => {
    expect(dryRunCheckLine(undefined)).toMatch(/^Not checked against the rows yet/);
    const t = totalsOf(checked());
    expect(dryRunCheckLine(t)).toBe("Checked against the rows (2026-11-08 21:40 UTC): 1 of 2 keys and 1 of 2 links passed; 2 failed.");
    expect(dryRunCheckLine(t)).not.toMatch(/validate_plan/);
  });
});

describe("plain English", () => {
  it("the summary is short sentences, without pill jargon", () => {
    const lines = summaryLines(shop());
    expect(lines[0]).toBe("5 tables, 3 with a key, and 2 links between them.");
    expect(lines[1]).toBe("3 still wait for you; 1 accepted, 1 rejected.");
    for (const l of lines) expect(l).not.toMatch(/pill|proposed|K pills|R pills/);
  });

  it("rows read as sentences and every rule has a tooltip", () => {
    const rv = shop();
    expect(itemText(rv.items[0])).toBe("Key of customers: customer_id");
    expect(itemText(rv.items[3])).toBe("orders → customers (customer_id)");
    expect(itemText(rv.items[4])).toBe("orders → addresses (ship_to_id → address_id)");
    for (const r of ["K0", "K1", "K2", "K3", "K4", "K5", "R0", "R1", "R2", "R3", "R4", "R5", "confirmed"]) {
      expect(RULE_MEANING[r]).toBeTruthy();
      expect(ruleMeaning(r)).toMatch(/\.$/);
    }
  });

  it("Thinker asks about audit_log with the choices inline, and never names an argument", () => {
    const qs = questions(shop());
    expect(qs).toHaveLength(1);
    expect(qs[0].text).toBe("audit_log has no key that I could find, so nothing can point to it. Is that right?");
    expect(qs[0].choices.map((c) => c.label)).toEqual([
      "Yes, keep it without a key", "Its key is event", "Its key is customer_id", "Its key is happened_at",
    ]);
    expect(qs[0].choices[1].action).toEqual({ kind: "key", table: "audit_log", columns: ["event"] });
    expect(questions(shop(), { "key:audit_log": "keep" })).toEqual([]);
  });

  it("an ambiguous column becomes a choice of tables", () => {
    const rv = shop();
    rv.open_questions = [{ about: "orders.ship_to_id", question: "Which table does orders.ship_to_id refer to: addresses or customers? Add it with confirmed, or leave it unlinked." }];
    const [q] = questions(rv);
    expect(q.text).toBe("orders.ship_to_id could point to addresses and customers. Which one?");
    expect(q.choices.map((c) => c.label)).toEqual(["It points to addresses", "It points to customers", "Leave it unlinked"]);
    expect(q.choices[0].action).toEqual({ kind: "link", source: "orders", column: "ship_to_id", target: "addresses", targetColumns: ["address_id"] });
  });

  it("no bubble carries argument syntax, before or after a check", () => {
    const answered = [{}, { "key:audit_log": "keep" }];
    for (const rv of [shop(), checked(), acceptAll(checked())]) {
      for (const a of answered) {
        const s = sayings(rv, a);
        for (const text of [s.onto, s.thinker, s.builder, ...questions(rv, a).map((q) => q.text)]) {
          expect(text).toBeTruthy();
          expect(hasArgumentSyntax(text)).toBe(false);
          expect(WORDS_WITH_ARGUMENTS.test(text)).toBe(false); // the cards' own rule
        }
      }
    }
    expect(hasArgumentSyntax('run validate_plan with workspace="demo"')).toBe(true);
    expect(hasArgumentSyntax("give one with keys")).toBe(true);
  });

  it("a mascot is glad only after a check where nothing failed", () => {
    expect(sayings(shop()).glad).toBe(false);
    expect(sayings(checked()).glad).toBe(false);
    const ok = checked();
    ok.items[1].check = passed({ rows: 12, nulls: 0, distinct: 12 });
    ok.items[3].check = passed({ rows_with_value: 12, orphans: 0 });
    expect(sayings(ok).glad).toBe(true);
    expect(sayings(ok).thinker).toMatch(/^Everything I checked holds/);
    expect(sayings(shop()).thinker).toMatch(/^Shall I check these against the rows\?/);
  });
});
