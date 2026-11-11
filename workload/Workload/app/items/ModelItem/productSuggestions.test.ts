// n222: the words and the ticks of the suggested data products, and the dry run's progress line (productSuggestions.ts).
import { describe, expect, it } from "vitest";
import { SuggestedProduct, SuggestedProducts } from "./engineClient";
import { emptyDefinition, fromParts, toParts } from "./ModelItemDefinition";
import { PREPARING, chosenLine, chosenProducts, interfaceLines, panelLine, preparingLine, stale, toggle } from "./productSuggestions";

const P = (id: string, tables: string[], extra: Partial<SuggestedProduct> = {}): SuggestedProduct => ({
  id, name: id, tables, rule: "r", name_reason: "n", why: {}, interface: { provides: [], consumes: [] }, evidence: [], ...extra,
});
const S = (products: SuggestedProduct[], checked = false): SuggestedProducts => ({ products, unassigned: [], checked, from: "f", note: "n" });

describe("n222: suggested data products", () => {
  const all = [P("customers", ["customers", "orders"]), P("products", ["categories", "products"])];

  it("ticks and unticks in the engine's order, and keeps a tick this review no longer suggests (to say so)", () => {
    let list = toggle([], all[1], true, all);
    list = toggle(list, all[0], true, all);
    expect(list.map((t) => t.id)).toEqual(["customers", "products"]);
    expect(toggle(list, all[0], false, all).map((t) => t.id)).toEqual(["products"]);
    const old = [{ id: "sales", name: "sales" }, { id: "products", name: "products" }];
    expect(stale(old, S(all))).toEqual([{ id: "sales", name: "sales" }]);
    expect(toggle(old, all[0], true, all).map((t) => t.id)).toEqual(["customers", "products", "sales"]);
  });

  it("the interface in words: what it provides and what it uses, with the rule", () => {
    const p = P("products", [], { interface: { provides: [{ product: "customers", id: "customers", link: "order_items.product_id → products", rule: "R1" }],
      consumes: [{ product: "suppliers", id: "suppliers", link: "products.supplier_id → suppliers", rule: "" }] } });
    expect(interfaceLines(p)).toEqual(["Provides to customers: order_items.product_id → products (R1)", "Uses suppliers: products.supplier_id → suppliers"]);
  });

  it("the panel's line says whether the rows were checked, and when there is nothing to suggest", () => {
    expect(panelLine(S(all))).toMatch(/^2 suggested data products, from the keys and links you reviewed; check them/);
    expect(panelLine(S(all.slice(0, 1), true))).toBe("1 suggested data product, from the keys and links you reviewed and what the rows hold.");
    expect(panelLine(S([]))).toMatch(/No data product to suggest/);
    expect(panelLine(null)).toBe("");
  });

  it("outputs.json keeps the ticks across a save and a reload; the dry run sends them", () => {
    const d = emptyDefinition();
    d.outputs.products = [{ id: "products", name: "products" }];
    const back = fromParts(toParts(d));
    expect(back.outputs.products).toEqual([{ id: "products", name: "products" }]);
    expect(chosenProducts(back)).toEqual([{ id: "products", name: "products" }]);
    expect(chosenProducts(emptyDefinition())).toEqual([]);
  });

  it("the dry run's line for a ticked data product, and for one this plan no longer suggests", () => {
    expect(chosenLine({ id: "p", name: "products", tables: ["categories", "products"], words: "2 table(s)." })).toBe("products: categories, products. 2 table(s).");
    expect(chosenLine({ id: "s", name: "sales", gone: true, words: "This plan no longer suggests it." })).toBe("sales: This plan no longer suggests it.");
  });

  it("the dry run's busy line: the engine's words while it prepares, else the plain line", () => {
    expect(preparingLine(undefined)).toBe(PREPARING);
    expect(preparingLine({ progress: { words: "Dry run: 2 of 6 outputs prepared (API for GraphQL, Gold views)." } } as never)).toMatch(/^Dry run: 2 of 6/);
    expect(preparingLine({ progress: { words: "  " } } as never)).toBe(PREPARING);
  });
});
