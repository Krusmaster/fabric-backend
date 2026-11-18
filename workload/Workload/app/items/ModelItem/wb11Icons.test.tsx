// WB11 (Gustav, 18 Nov 2026: "kan vi lägga in fler Microsoft-loggor för de items man kan välja att skapa?"): the Fabric
// item icons of n184, from the same Microsoft package, beside every Fabric item type the editor names: the next steps'
// cards, Choose what to build, the dry run's cards, the data product's list, Retire, the catalog's "What would be written
// as you" and the source. Every type maps to an icon or the documented fallback; the icon always stands next to the
// type's name in text, with alt="" when that text names it; no product logo, no Microsoft logo.
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ICONS from "./fabricIcons.json";
import { ICON_TYPES, KIND_TYPE, NOTICES, typeIcon, typeWord } from "./fabricIcons";
import { KINDS } from "./buildWords";
import { TYPE_LABEL } from "./createWords";
import { SOURCE_TYPES, restType, sourceLabel, PICKER_TYPES } from "./sourceWords";
import FIXTURE from "./w13Review.fixture.json";
import { ReviewFile } from "./ModelItemDefinition";
import { nextSteps, workloadLine } from "./nextSteps";
import { NextStepsPanel } from "./NextStepsView";
import { CatalogView } from "./CatalogPanel";
import { CatalogAnswer } from "./catalogWords";
import { DataProductView } from "./DataProductView";
import { DELETED, DELETE_DRY_RUN, OUTPUTS, STATUS } from "./productPage.fixture";
import { EmptyView } from "./ModelItemViews";
import { TypeIcon, TypeName } from "./itemIcons";

const REVIEW = FIXTURE.review as unknown as ReviewFile;
const SOURCE = { displayName: "shop_lh", schema: "shop", itemType: "Lakehouse" };
const IMG = /<img class="krusgraph-item-icon" src="([^"]+)" alt="([^"]*)" width="20" height="20"\/>/g;
const imgs = (html: string) => [...html.matchAll(IMG)].map((m) => ({ src: m[1], alt: m[2] }));
const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

describe("WB11: every Fabric item type the editor names has its icon", () => {
  it("maps each type, from every list that names one, to Microsoft's icon or the documented fallback", () => {
    const named = new Set<string>([
      ...Object.keys(TYPE_LABEL),                         // the data product, Retire, the Open links
      ...Object.values(KIND_TYPE),                        // Choose what to build, the dry run and Create
      ...SOURCE_TYPES,                                    // the source
      ...PICKER_TYPES.map((t) => restType(t)!).filter((t) => SOURCE_TYPES.includes(t)),
      ...nextSteps({ review: REVIEW, created: [], source: SOURCE }).steps.flatMap((s) => s.items),
    ]);
    for (const t of named) expect(typeIcon(t), t).toBeTruthy();
    expect(ICON_TYPES.sort()).toEqual([...named].sort());
    for (const k of KINDS) expect(KIND_TYPE[k.kind], k.kind).toBeTruthy();
    // the fallback is the package's generic item icon, for exactly the two types the package has no icon for
    const fallback = ICON_TYPES.filter((t) => typeIcon(t)!.src.endsWith(`/${ICONS.fallback.file}`));
    expect(fallback.sort()).toEqual(["GraphQLApi", "Reflex"]);
    expect(ICONS.fallback.why).toContain("API for GraphQL");
    expect(ICONS.fallback.why).toContain("Activator");
    expect(typeIcon("SomethingElse")).toBeUndefined();
  });

  it("names each type with the same word everywhere", () => {
    for (const [t, word] of Object.entries(TYPE_LABEL)) expect(typeWord(t), t).toBe(word);
    for (const t of SOURCE_TYPES) expect(typeWord(t), t).toBe(sourceLabel(t));
    expect(typeWord("Reflex")).toBe("Activator");
    expect(typeWord("MLExperiment")).toBe("Experiment");
    // the kinds' n184 icons are the types' icons
    for (const [kind, t] of Object.entries(KIND_TYPE)) {
      const k = (ICONS.kinds as Record<string, { file: string }>)[kind];
      if (k) expect(typeIcon(t)!.src.endsWith(`/${k.file}`), kind).toBe(true);
    }
  });

  it("uses item icons only: no product, experience or Microsoft logo", () => {
    for (const t of ICON_TYPES) {
      const src = typeIcon(t)!.src;
      expect(src).toMatch(/^\/assets\/fabric-icons\/[a-z_]+_24_item\.svg$/);
      expect(src).not.toMatch(/power_bi|fabric_24|microsoft|data_science_|real_time_intelligence_|data_factory_24_(color|filled|regular)/);
    }
    expect(NOTICES[0]).toContain("beside the names of Fabric item types");
    expect(NOTICES[0]).toContain("not made or endorsed by Microsoft");
  });
});

describe("WB11: the next steps' cards", () => {
  const html = renderToStaticMarkup(<NextStepsPanel review={REVIEW} created={[]} source={SOURCE} onBuild={() => undefined} />);
  const steps = nextSteps({ review: REVIEW, created: [], source: SOURCE }).steps;

  it("show the icons of the item types each step makes at the card's top left, beside the workload and the types' names", () => {
    expect(steps.map((s) => [s.id, workloadLine(s)])).toEqual([
      ["ds-features", "Data Science · Notebook, Experiment"],
      ["pbi", "Power BI · Semantic model, Report"],
      ["agent", "Data agent"],
      ["factory", "Data Factory · Pipeline, Notebook"],
      ["api", "Data Engineering · API for GraphQL"],
      ["iq", "Fabric IQ · Ontology"],
      ["drift", "Real-Time Intelligence · Activator"],
      ["app", "Apps · App"],
    ]);
    for (const s of steps) {
      const card = html.split(`data-step="${s.id}"`)[1].split("</li>")[0];
      const head = card.split('class="kg-next-head"')[1].split("</h3>")[0];
      const icons = imgs(head);
      expect(icons.map((i) => i.src), s.id).toEqual(s.items.map((t) => typeIcon(t)!.src));
      for (const i of icons) expect(i.alt, s.id).toBe("");        // the line beside them names every type
      expect(text(head)).toContain(workloadLine(s));
      expect(head.indexOf("<img")).toBeLessThan(head.indexOf(workloadLine(s)));   // top left: before the words
    }
  });

  it("say what is left: a Power BI card with the model built shows the report only", () => {
    const n = nextSteps({ review: REVIEW, created: [{ type: "SemanticModel", name: "m", output: "semantic_model" }], source: SOURCE });
    expect(workloadLine(n.steps.find((s) => s.id === "pbi")!)).toBe("Power BI · Report");
  });

  it("match the snapshot", () => {
    expect(html).toMatchSnapshot();
  });
});

describe("WB11: the data product, Retire, the catalog and the source", () => {
  it("the Built list names each item's type with its icon", () => {
    const html = renderToStaticMarkup(<DataProductView productName="Shop sales" outputs={OUTPUTS} status={STATUS} />);
    const rows = html.split('class="kg-dp-row"').slice(1);
    const typed = rows.filter((r) => r.includes("krusgraph-item-title"));
    expect(typed.length).toBeGreaterThanOrEqual(5);
    for (const r of typed) {
      const [icon] = imgs(r);
      expect(icon, r.slice(0, 200)).toBeTruthy();
      expect(icon.alt).toBe("");
      const word = text(r.split('class="krusgraph-item-title">')[1].split("</span>")[0]).trim();
      expect(ICON_TYPES.map((t) => typeWord(t))).toContain(word);
    }
    expect(html).toContain(".kg-dp .krusgraph-item-icon{width:20px;height:20px;flex:none}");
    expect(html).toMatchSnapshot();
  });

  it("Retire's dry run and result name each item's type with its icon", () => {
    for (const retire of [DELETE_DRY_RUN, DELETED]) {
      const html = renderToStaticMarkup(<DataProductView productName="Shop sales" outputs={OUTPUTS} status={STATUS} retire={retire} />);
      const panel = html.split('class="kg-dp-panel"')[1];
      const listed = (retire.items ?? retire.results ?? []).filter((x) => typeIcon(x.type));
      expect(listed.length).toBeGreaterThan(0);
      for (const x of listed) expect(panel).toContain(`src="${typeIcon(x.type)!.src}" alt="" width="20" height="20"/>${typeWord(x.type)}</span><span class="kg-dp-name">${x.name}</span>`);
    }
  });

  it("the catalog's What would be written as you cards show the item's type and icon before its name", () => {
    const answer = {
      summary: "s", products: [], kept: [], missing_tags: [], quality_rules: [], requests: [],
      diff: [
        { item: "shop_lh", type: "Lakehouse", field: "tags", before: [], after: ["Krusgraph"], action: "write" },
        { item: "shop_lh_silver", type: "Notebook", field: "description", before: "", after: "x", action: "write" },
        { item: "shop_lh_api", type: "GraphQLApi", field: "description", before: "", after: "x", action: "write" },
        { item: "shop_wh", item_id: "w1", type: "Warehouse", field: "description and tags", before: null, after: "x", action: "optional", why: "Krusgraph did not build it" },
        { item: "odd", field: "tags", before: [], after: ["a"], action: "write" },
      ],
      confirm: "c", writable: false, handover: { requests: [], files: {} },
    } as unknown as CatalogAnswer;
    const html = renderToStaticMarkup(<CatalogView answer={answer} busy={false} owner="" checked={false} onOwner={() => undefined}
      onPrepare={() => undefined} onChecked={() => undefined} onWrite={() => undefined} />);
    for (const [type, item] of [["Lakehouse", "shop_lh"], ["Notebook", "shop_lh_silver"], ["GraphQLApi", "shop_lh_api"]]) {
      expect(html).toContain(`<img class="krusgraph-item-icon" src="${typeIcon(type)!.src}" alt="" width="20" height="20"/><span>${typeWord(type)}</span><strong>${item}</strong>`);
    }
    expect(text(html)).toContain("Also write the description and tags of the warehouse shop_wh");
    expect(html).toContain(`src="${typeIcon("Warehouse")!.src}" alt=""`);
    expect(html).toContain("<strong>odd</strong>");                       // no type: the name alone, no icon
    expect(html).toMatchSnapshot();
  });

  it("the source button shows the picked type's icon; a source of unknown type shows none", () => {
    const schemas = { loading: false };
    const base = { schema: "shop", schemas, onSchemaChange: (): void => undefined, onChooseLakehouse: (): void => undefined, onReview: (): void => undefined };
    for (const t of SOURCE_TYPES) {
      const html = renderToStaticMarkup(<EmptyView {...base} source={{ itemId: "i", workspaceId: "w", displayName: "src", itemType: t } as never} />);
      expect(html).toContain(`src="${typeIcon(t)!.src}" alt=""`);
      expect(text(html)).toContain(`${sourceLabel(t)}: src`);
      if (t !== "Lakehouse") expect(html).toContain(`src="${typeIcon("Lakehouse")!.src}" alt=""`);   // the target lakehouse
    }
    const none = renderToStaticMarkup(<EmptyView {...base} />);
    expect(imgs(none)).toEqual([]);
  });
});

describe("WB11: the icon component", () => {
  it("is decorative beside its type's name, the type otherwise, and sized so nothing moves when it loads", () => {
    expect(renderToStaticMarkup(<TypeName type="SQLDatabase" text="SQL database" />))
      .toBe('<span class="krusgraph-item-title"><img class="krusgraph-item-icon" src="/assets/fabric-icons/sql_database_24_item.svg" alt="" width="20" height="20"/>SQL database</span>');
    expect(renderToStaticMarkup(<TypeIcon type="Lakehouse" beside="Source: demo" />)).toContain('alt="Lakehouse"');
    expect(renderToStaticMarkup(<TypeName type="Unknown" text="Unknown" />)).toBe('<span class="krusgraph-item-title">Unknown</span>');
  });
});
