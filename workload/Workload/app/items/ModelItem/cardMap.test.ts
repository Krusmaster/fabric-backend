// n173: the map in the Model editor. The drawing is the MCP Apps cards' own (cardMap.generated.ts, checked current by
// tests/test_workload_check.py); here: the states the editor puts on it from the review file (decisions made in the
// editor, the check against the rows) and the classes it adds for a table's key check and for accepted links.
import { describe, expect, it } from "vitest";
import { ReviewFile } from "./ModelItemDefinition";
import { MapData, overlay, stateClasses } from "./cardMap";
import { STATE_WORD, drawMap } from "./cardMap.generated";
import { acceptAll } from "./modelWords";

// what /workload/v1/review sends (workload_api.map_of) for part of the shop
const MAP: MapData = {
  tables: [
    { name: "customers", key: ["customer_id"], key_rule: "K2", columns: 3, review: "proposed", key_check: "not_checked" },
    { name: "orders", key: ["order_id"], key_rule: "K2", columns: 4, review: "proposed", key_check: "not_checked" },
    { name: "audit_log", key: [], key_rule: "K3", columns: 3 },
  ],
  relationships: [
    { id: "orders.customer_id>customers", source: "orders", source_cols: ["customer_id"], target: "customers",
      target_cols: ["customer_id"], rule: "R1", state: "not_checked", review: "proposed" },
    { id: "audit_log.customer_id>customers", source: "audit_log", source_cols: ["customer_id"], target: "customers",
      target_cols: ["customer_id"], rule: "R1", state: "not_checked", review: "proposed" },
  ],
  checked: true,
  reviewed: true,
};

function review(): ReviewFile {
  return {
    format: "krusgraph-review", version: 1, plan_id: "p", source: {},
    items: [
      { id: "key:customers", type: "key", table: "customers", columns: ["customer_id"], rule: "K2", review: "proposed",
        check: { status: "failed", result: { rows: 51, nulls: 0, distinct: 50 } } },
      { id: "key:orders", type: "key", table: "orders", columns: ["order_id"], rule: "K2", review: "proposed",
        check: { status: "passed", result: { rows: 9, nulls: 0, distinct: 9 } } },
      { id: "rel:orders.customer_id>customers", type: "relationship", source: "orders", columns: ["customer_id"],
        target: "customers", target_columns: ["customer_id"], rule: "R1", review: "proposed",
        check: { status: "failed", result: { rows_with_value: 9, orphans: 1 } } },
      { id: "rel:audit_log.customer_id>customers", type: "relationship", source: "audit_log", columns: ["customer_id"],
        target: "customers", target_columns: ["customer_id"], rule: "R1", review: "rejected", check: { status: "not_checked" } },
    ],
  };
}

describe("check states on the map", () => {
  it("takes each link's state and orphans from the review's check", () => {
    const m = overlay(MAP, review());
    const by = Object.fromEntries(m.relationships.map((r) => [r.id, r]));
    expect(by["orders.customer_id>customers"]).toMatchObject({ state: "failed", orphans: 1, rows_with_value: 9 });
    expect(by["audit_log.customer_id>customers"].state).toBe("not_checked");
    expect(by["audit_log.customer_id>customers"].orphans).toBeUndefined();
    expect(m.checked).toBe(true);
  });

  it("marks each table's key check and the link states with the editor's classes", () => {
    const cls = stateClasses(overlay(MAP, review()));
    expect(cls.tables.customers).toContain("kg-key-failed");
    expect(cls.tables.orders).toContain("kg-key-passed");
    expect(cls.tables.audit_log).toEqual([]); // no key, nothing to check
    expect(cls.links["orders.customer_id>customers"]).toEqual(["kg-st-failed", "kg-rv-proposed"]);
    expect(cls.links["audit_log.customer_id>customers"]).toEqual(["kg-st-not_checked", "kg-rv-rejected"]);
  });

  it("before a check every link is not checked (grey)", () => {
    const rv = review();
    rv.items.forEach((it) => (it.check = { status: "not_checked" }));
    const m = overlay(MAP, rv);
    expect(new Set(m.relationships.map((r) => r.state))).toEqual(new Set(["not_checked"]));
    expect(m.checked).toBe(false);
  });
});

describe("review states on the map", () => {
  it("follows Accept all made in the editor, without a new call", () => {
    const m = overlay(MAP, acceptAll(review()));
    expect(m.tables.find((t) => t.name === "customers").review).toBe("accepted");
    const by = Object.fromEntries(m.relationships.map((r) => [r.id, r.review]));
    expect(by["orders.customer_id>customers"]).toBe("accepted");
    expect(by["audit_log.customer_id>customers"]).toBe("rejected");
    expect(stateClasses(m).links["orders.customer_id>customers"]).toContain("kg-rv-accepted");
  });
});

describe("the cards' own drawing", () => {
  it("is the cards' drawMap with the cards' words for each state", () => {
    expect(typeof drawMap).toBe("function");
    expect(STATE_WORD.passed).toBe("passed");
    expect(STATE_WORD.failed).toBe("failed");
    expect(STATE_WORD.not_checked).toBe("not checked");
  });
});
