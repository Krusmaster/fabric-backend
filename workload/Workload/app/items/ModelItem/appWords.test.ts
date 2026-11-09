import { describe, expect, it } from "vitest";
import { BuildCard } from "./engineClient";
import { OutputChoice } from "./ModelItemDefinition";
import { apiLines, featureOff, nothingTicked, packageHref, preflightWords, ticked, toggle, withAppChoices } from "./appWords";
import { toRequests } from "./buildWords";

const card = (answer: Record<string, any>, extra: Partial<BuildCard> = {}): BuildCard => ({
  output: "rayfin_app", label: "App (Rayfin, preview)", type: "AppBackend", name: "shop_app", dry_run: true, would: "create",
  updates_in_place: false, permissions: { needs: ["Item.ReadWrite.All"], missing: null, execute: "" }, answer, ...extra,
});

describe("n181: the App (Rayfin, preview) card", () => {
  it("shows the admin card when App items are off, never a generic error", () => {
    const off = featureOff(card({ error: "Fabric App items are turned off", kind: "feature_disabled", setting: "Enable Fabric App Items (preview)",
      where: "Admin portal → Tenant settings → Microsoft Fabric", admin_steps: ["a", "b"] }));
    expect(off?.setting).toBe("Enable Fabric App Items (preview)");
    expect(off?.steps).toEqual(["a", "b"]);
    expect(featureOff(card({ dry_run: true }))).toBeUndefined();
    expect(preflightWords({ status: "on", note: "On for the organisation." })).toBe("Fabric App items are on. On for the organisation.");
    expect(preflightWords({ status: "unknown", reason: "not a Fabric administrator" })).toContain("Could not check");
  });

  it("keeps the ticks in the outputs and sends them", () => {
    const c = card({ chosen: { kpis: ["rows:orders"], tables: [], charts: [] } });
    let t = ticked(c);
    expect(t.kpis).toEqual(["rows:orders"]);
    t = toggle(t, "charts", "chart:x", true);
    t = toggle(t, "kpis", "rows:orders", false);
    expect(t).toEqual({ kpis: [], tables: [], charts: ["chart:x"] });
    expect(nothingTicked({ kpis: [], tables: [], charts: [] })).toBe(true);
    const choices: OutputChoice[] = [{ type: "rayfin_app", name: "shop_app", enabled: true }, { type: "graphql", name: "shop_api", enabled: false }];
    const stored = withAppChoices(choices, t);
    expect(stored[0].app).toEqual(t);
    expect(ticked(c, stored[0].app)).toEqual(t);
    expect(toRequests(stored)).toEqual([{ kind: "rayfin_app", name: "shop_app", app: t }]);
  });

  it("says the API is read-only and lists every link", () => {
    const lines = apiLines({ connector: "shop", connector_type: "fabric-sqlanalytics", operations: ["read"], read_only: true, mutations: [],
      types: [{ type: "orders", queries: ["Query", "Query_by_pk"] }],
      links: [{ from: "orders.ship_to_id", to: "addresses.address_id", rule: "R5" }], note: "" });
    expect(lines[0]).toContain("read-only: queries only, no mutations");
    expect(lines).toContain("orders.ship_to_id → addresses.address_id (R5)");
    expect(packageHref({ zip_base64: "UEs=" })).toBe("data:application/zip;base64,UEs=");
  });
});
