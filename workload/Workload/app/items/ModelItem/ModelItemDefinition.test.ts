// Unit tests for the Krusgraph Model's item definition (n166): save to parts and load back, the version field, the
// review list order and the rule pills. The review file below has the shape fabric_backend/review.py writes for the
// synthetic shop schema (fabric_backend/seed.py); only names, types, rules and decisions, no row values.
import { describe as group, expect, it } from "vitest";
import {
  DEFINITION_VERSION,
  DefinitionError,
  ModelDefinition,
  PARTS,
  ReviewFile,
  counts,
  decide,
  decodeJson,
  defaultApiName,
  describe,
  emptyDefinition,
  encodeJson,
  fromParts,
  rulePill,
  sortForReview,
  toParts,
} from "./ModelItemDefinition";

const REVIEW: ReviewFile = {
  format: "krusgraph-review",
  version: 1,
  plan_id: "plan-0123456789ab",
  source: { platform: "fabric", source: "shop_lh", schema: "shop" },
  items: [
    { id: "key:customers", type: "key", table: "customers", columns: ["customer_id"], rule: "K0", review: "proposed" },
    { id: "key:orders", type: "key", table: "orders", columns: ["order_id"], rule: "K0", review: "accepted" },
    {
      id: "rel:orders.customer_id>customers", type: "relationship", source: "orders", columns: ["customer_id"],
      target: "customers", target_columns: ["customer_id"], rule: "R0", review: "proposed",
    },
    {
      id: "rel:orders.ship_to_id>addresses", type: "relationship", source: "orders", columns: ["ship_to_id"],
      target: "addresses", target_columns: ["address_id"], rule: "confirmed", review: "open",
    },
  ],
  open_questions: [],
};

const FULL: ModelDefinition = {
  item: { version: 1, format: "krusgraph-model", view: "review" },
  source: {
    version: 1, platform: "fabric", workspaceId: "ws-1", itemId: "lh-1", itemType: "Lakehouse",
    displayName: "shop_lh", schema: "shop",
  },
  outputs: { version: 1, outputs: [{ type: "graphql", name: "shop_lh_api", enabled: true, writable: false }], created: [] },
  review: REVIEW,
};

const part = (path: string, value: unknown) => ({ path, payload: encodeJson(value), payloadType: "InlineBase64" });

group("save and load", () => {
  it("writes the four parts, each JSON in base64, and reads them back unchanged", () => {
    const parts = toParts(FULL);
    expect(parts.map((p) => p.path)).toEqual([PARTS.item, PARTS.source, PARTS.outputs, PARTS.review]);
    expect(parts.every((p) => p.payloadType === "InlineBase64")).toBe(true);
    expect(fromParts(parts)).toEqual(FULL);
  });

  it("keeps the review file byte for byte as the engine wrote it", () => {
    const parts = toParts(FULL);
    expect(decodeJson(parts.find((p) => p.path === PARTS.review)!.payload)).toEqual(REVIEW);
  });

  it("leaves out source and review until there is one", () => {
    const parts = toParts(emptyDefinition());
    expect(parts.map((p) => p.path)).toEqual([PARTS.item, PARTS.outputs]);
    expect(fromParts(parts)).toEqual(emptyDefinition());
  });

  it("opens a new item (no definition yet) on the empty view", () => {
    expect(fromParts(undefined).item.view).toBe("empty");
    expect(fromParts([]).source).toBeUndefined();
  });

  it("ignores parts it does not know, such as Fabric's .platform", () => {
    const parts = [...toParts(FULL), part(".platform", { metadata: { type: "Org.Krusgraph.Model" } })];
    expect(fromParts(parts)).toEqual(FULL);
  });

  it("keeps non-ASCII table and lakehouse names intact", () => {
    const d = { ...FULL, source: { ...FULL.source!, displayName: "försäljning_lh" } };
    expect(fromParts(toParts(d)).source!.displayName).toBe("försäljning_lh");
  });
});

group("the version field", () => {
  it("writes version 1 on every part this editor owns", () => {
    const parts = toParts({ ...FULL, item: { ...FULL.item, version: 0 } });
    for (const path of [PARTS.item, PARTS.source, PARTS.outputs]) {
      expect(decodeJson<{ version: number }>(parts.find((p) => p.path === path)!.payload).version).toBe(DEFINITION_VERSION);
    }
    expect(DEFINITION_VERSION).toBe(1);
  });

  it("reads a version 1 definition without a version field (written before it existed) and fills defaults", () => {
    const parts = [
      part(PARTS.item, { format: "krusgraph-model" }),
      part(PARTS.source, { platform: "fabric", workspaceId: "ws-1", itemId: "lh-1", itemType: "Lakehouse", displayName: "shop_lh" }),
      part(PARTS.review, REVIEW),
    ];
    const d = fromParts(parts);
    expect(d.item).toEqual({ version: 1, format: "krusgraph-model", view: "review" });
    expect(d.source!.schema).toBe("dbo");
    expect(d.source!.version).toBe(1);
    expect(d.outputs).toEqual({ version: 1, outputs: [], created: [] });
  });

  it("refuses a definition saved by a newer version, instead of guessing", () => {
    const parts = toParts(FULL).map((p) => (p.path === PARTS.outputs ? part(PARTS.outputs, { ...FULL.outputs, version: 2 }) : p));
    expect(() => fromParts(parts)).toThrow(DefinitionError);
    expect(() => fromParts(parts)).toThrow(/newer/);
  });

  it("refuses an invalid version and parts that are not ours", () => {
    expect(() => fromParts([part(PARTS.item, { version: "1", format: "krusgraph-model" })])).toThrow(/invalid version/);
    expect(() => fromParts([part(PARTS.item, { version: 1, format: "something-else" })])).toThrow(DefinitionError);
    expect(() => fromParts([part(PARTS.review, { format: "other" })])).toThrow(/review file/);
    expect(() => fromParts([{ path: PARTS.item, payload: btoa("{not json"), payloadType: "InlineBase64" }])).toThrow(/not valid JSON/);
  });
});

group("review list", () => {
  it("shows open items first, then proposed, then decided; keys before relationships", () => {
    expect(sortForReview(REVIEW.items).map((it) => it.id)).toEqual([
      "rel:orders.ship_to_id>addresses",
      "key:customers",
      "rel:orders.customer_id>customers",
      "key:orders",
    ]);
  });

  it("labels keys K and relationships R, and describes each in plain words", () => {
    expect(REVIEW.items.map(rulePill)).toEqual(["K", "K", "R", "R"]);
    expect(describe(REVIEW.items[0])).toBe("customers: customer_id");
    expect(describe(REVIEW.items[2])).toBe("orders.customer_id → customers.customer_id");
  });

  it("records a decision on one item and counts from the file, not from anything else", () => {
    const r = decide(REVIEW, "rel:orders.customer_id>customers", "rejected", "not a reference");
    expect(r.items[2]).toMatchObject({ review: "rejected", reason: "not a reference" });
    expect(REVIEW.items[2].review).toBe("proposed"); // the saved file is not changed in place
    expect(counts(r)).toEqual({ open: 1, proposed: 1, accepted: 1, rejected: 1, keys: 2, relationships: 2 });
    expect(() => decide(REVIEW, "rel:nope", "accepted")).toThrow(DefinitionError);
  });

  it("proposes an API name Fabric accepts", () => {
    expect(defaultApiName("shop_lh")).toBe("shop_lh_api");
    expect(defaultApiName("Shop Lakehouse 2")).toBe("Shop_Lakehouse_2_api");
    expect(defaultApiName("")).toBe("model_api");
  });
});

group("n209: an App built earlier keeps its choices and its package", () => {
  const chosen = { kpis: ["rows:orders"], tables: ["table:orders"], charts: ["chart:cat"], accent: "teal" };
  const record = {
    name: "shop_lh_app", at: "2026-11-10T09:00:00Z", dry_run: false, chosen, labels: { "rows:orders": "Rows in orders" },
    pages: [{ id: "overview", title: "Overview", shows: ["Rows in orders"] }],
    package: { filename: "shop_lh_app_rayfin_app.zip", zip_base64: "UEs=" },
    one_command: { command: "bash publish.sh shop_lh_app_rayfin_app.zip", steps: ["Download the package below."] },
  };
  const built: ModelDefinition = {
    ...FULL,
    outputs: { version: 1, created: [{ type: "AppBackend", id: "app-1", name: "shop_lh_app", workspace: "ws-1", output: "rayfin_app" }],
      outputs: [{ type: "rayfin_app", name: "shop_lh_app", enabled: true, app: chosen, app_package: record }] },
  };

  it("reopens with the ticks and the package record as they were saved", () => {
    const back = fromParts(toParts(built));
    expect(back.outputs.outputs[0].app).toEqual(chosen);
    expect(back.outputs.outputs[0].app_package).toEqual(record);
    expect(back).toEqual(built);
  });

  it("reads an outputs.json from before n209 (no record) as before, and drops a record or ticks of another shape", () => {
    const old = { ...built, outputs: { ...built.outputs, outputs: [{ type: "rayfin_app", name: "shop_lh_app", enabled: true }] } };
    expect(fromParts(toParts(old)).outputs.outputs[0]).toEqual({ type: "rayfin_app", name: "shop_lh_app", enabled: true });
    const odd = toParts(built).map((p) => (p.path === PARTS.outputs
      ? part(PARTS.outputs, { ...built.outputs, outputs: [{ type: "rayfin_app", name: "shop_lh_app", enabled: true, app: "x", app_package: { name: 3 } }] })
      : p));
    expect(fromParts(odd).outputs.outputs[0]).toEqual({ type: "rayfin_app", name: "shop_lh_app", enabled: true });
  });
});
