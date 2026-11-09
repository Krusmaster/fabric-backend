// n184: the Fabric item icons on the output cards: one per output, with the item type as text, only from Microsoft's
// package at the pinned version, byte for byte (sha256), and the notices with the trademark line. The default names.
import { createHash } from "crypto";
import { readFileSync } from "fs";
import { join } from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ICONS from "./fabricIcons.json";
import { ICON_SIZE, NOTICES, TRADEMARK, itemIcon } from "./fabricIcons";
import { KINDS, choicesFor, defaultName } from "./buildWords";
import { AboutNotices, ItemTitle, OutputCard, OutputsView } from "./ModelItemViews";
import { BuildCard } from "./engineClient";

const ROOT = join(__dirname, "..", "..", "..");
const PKG = join(ROOT, ICONS.sourceDir, "..");

describe("the Fabric item icons", () => {
  it("are one per output, with the item type as alt text, at 20 px", () => {
    expect(Object.keys(ICONS.kinds).sort()).toEqual(KINDS.map((k) => k.kind).sort());
    for (const k of KINDS) {
      const icon = itemIcon(k.kind);
      expect(icon.alt).toBeTruthy();
      expect(icon.src).toMatch(/^\/assets\/fabric-icons\/[a-z_]+_24_item\.svg$/);
    }
    expect(itemIcon("silver_notebook").alt).toBe("Notebook");
    expect(itemIcon("gold_views").alt).toBe("Notebook");
    expect(itemIcon("graphql").alt).toBe("API for GraphQL");
    expect(ICON_SIZE).toBeGreaterThanOrEqual(20);
    expect(ICON_SIZE).toBeLessThanOrEqual(24);
  });

  it("come from Microsoft's package at the pinned version, unmodified", () => {
    const pkg = JSON.parse(readFileSync(join(PKG, "package.json"), "utf8"));
    expect(pkg.name).toBe(ICONS.package);
    expect(pkg.version).toBe(ICONS.version);
    const lock = JSON.parse(readFileSync(join(ROOT, "package-lock.json"), "utf8"));
    expect(lock.packages[`node_modules/${ICONS.package}`]).toMatchObject({ version: ICONS.version, integrity: ICONS.integrity });
    const used = new Set(Object.values(ICONS.kinds).map((k) => k.file));
    expect([...used].sort()).toEqual(Object.keys(ICONS.files).sort());
    for (const [file, sha] of Object.entries(ICONS.files)) {
      const bytes = readFileSync(join(ROOT, ICONS.sourceDir, file));
      expect(createHash("sha256").update(bytes).digest("hex"), file).toBe(sha);
    }
  });

  it("render at the left of every output card's title on Choose what to build", () => {
    const choices = choicesFor([], "demo_lh").map((c) => ({ ...c, enabled: true }));
    const html = renderToStaticMarkup(
      React.createElement(OutputsView, {
        choices, created: [], product: { on: false, name: "" }, onChange: (): void => undefined, onProduct: (): void => undefined,
        onOpen: (): void => undefined, onPreview: (): void => undefined,
      } as never)
    );
    for (const k of KINDS) {
      const icon = itemIcon(k.kind);
      const section = html.split(`aria-label="${k.label}"`)[1].split("</section>")[0];
      expect(section).toContain(`<span class="krusgraph-item-title"><img class="krusgraph-item-icon" src="${icon.src}" alt="${icon.alt}" width="20" height="20"/>${k.label}`);
    }
    expect(html).not.toMatch(/krusgraph-item-icon[^>]*(mascot|krusgraph-icon|krusgraph-item-icon\.png)/);
    expect(html).toContain(TRADEMARK);
  });

  it("render on the dry run's and Create's cards", () => {
    for (const k of KINDS) {
      for (const dry of [true, false]) {
        const card = { output: k.kind, label: k.label, dry_run: dry, name: defaultName(k.kind, "demo_lh"), permissions: { needs: [] } } as unknown as BuildCard;
        const html = renderToStaticMarkup(React.createElement(OutputCard, { card }));
        expect(html).toMatch(new RegExp(`^<section[^>]*><span class="krusgraph-item-title"><img class="krusgraph-item-icon" src="${itemIcon(k.kind).src}" alt="${itemIcon(k.kind).alt}"`));
      }
    }
    expect(renderToStaticMarkup(React.createElement(ItemTitle, { kind: "unknown", children: "x" }))).not.toContain("<img");
  });

  it("come with the terms and the trademark line in About and notices", () => {
    expect(TRADEMARK).toBe("Microsoft, Microsoft Fabric and Power BI are trademarks of the Microsoft group of companies.");
    expect(NOTICES).toContain(TRADEMARK);
    expect(NOTICES[0]).toContain(`${ICONS.package}@${ICONS.version}`);
    expect(NOTICES[0]).toContain("https://learn.microsoft.com/fabric/fundamentals/icons");
    expect(NOTICES[0]).toContain("unmodified");
    const html = renderToStaticMarkup(React.createElement(AboutNotices));
    expect(html).toContain("About and notices");
    expect(html).toContain(TRADEMARK);
  });
});

describe("default output names (n184)", () => {
  const PATTERN = ["demo_lh_silver", "demo_lh_gold", "demo_lh_pipeline", "demo_lh_model", "demo_lh_report", "demo_lh_api",
    "demo_lh_ontology", "demo_lh_agent", "demo_lh_app"];

  it("follow one pattern from the lakehouse", () => {
    expect(choicesFor([], "demo_lh").map((c) => c.name)).toEqual(PATTERN);
    expect(KINDS.map((k) => defaultName(k.kind, "demo_lh"))).toEqual(PATTERN);
  });

  it("follow the lakehouse once it is chosen, when the name was the Model item's default (demo_api)", () => {
    const before = choicesFor([], "demo");                                     // no lakehouse yet: the item's name
    expect(before.find((c) => c.type === "graphql")).toMatchObject({ name: "demo_api", enabled: true });
    const after = choicesFor(before.filter((c) => c.enabled), "demo_lh", { displayName: "demo" });
    expect(after.map((c) => c.name)).toEqual(PATTERN);
    // a saved definition with demo_api and a lakehouse, opened again
    const reopened = choicesFor([{ type: "graphql", name: "demo_api", enabled: true }], "demo_lh", { displayName: "demo", created: [] });
    expect(reopened.find((c) => c.type === "graphql").name).toBe("demo_lh_api");
  });

  it("keep a name typed by hand or an item already built", () => {
    const typed = choicesFor([{ type: "graphql", name: "shop_api", enabled: true }], "demo_lh", { displayName: "demo" });
    expect(typed.find((c) => c.type === "graphql").name).toBe("shop_api");
    const built = choicesFor([{ type: "graphql", name: "demo_api", enabled: true }], "demo_lh",
      { displayName: "demo", created: [{ type: "GraphQLApi", id: "a1", name: "demo_api", workspace: "w" }] });
    expect(built.find((c) => c.type === "graphql").name).toBe("demo_api");
  });
});
