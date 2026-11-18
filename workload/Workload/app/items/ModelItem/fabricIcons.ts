/**
 * n184: the Fabric item icon of each output, and the notices that go with Microsoft's icons. Pure data, no React, so
 * fabricIcons.test.ts runs it.
 *
 * Source: the npm package @fabric-msft/svg-icons (Microsoft's Fabric UX icons), which the Learn page "Microsoft Fabric
 * product, experience, and item icons" (https://learn.microsoft.com/fabric/fundamentals/icons) offers "for use in
 * Microsoft Fabric platform extension development". The files are used as they are: webpack copies them from the
 * package unchanged and the editor shows them with <img>, 20 px, left of the output's title, never next to the
 * Krusgraph logo or a mascot. The package has no item icon for an API for GraphQL; that card shows the package's
 * generic item placeholder, with "API for GraphQL" as its text.
 *
 * WB11 (Gustav, 18 Nov 2026: more Microsoft icons for the items you can choose to create): the same icons, from the same
 * package, beside every Fabric item type the editor names: the next steps' cards, the data product's list, Retire, the
 * catalog's "What would be written as you" and the source. `types` maps Fabric's REST item type to its icon; a type
 * without an icon in the package (API for GraphQL, Activator) shows the generic item icon (`fallback`), and a type not
 * listed shows its name with no icon. The icon is always next to the type's name in text, never on its own.
 */
import ICONS from "./fabricIcons.json";

export interface ItemIcon {
  src: string;
  alt: string;
}

export const ICON_PACKAGE = `${ICONS.package}@${ICONS.version}`;
export const ICON_SIZE = 20;

/** The icon of an output kind (silver_notebook, graphql, ...), or undefined for a kind without one. */
export function itemIcon(kind: string | undefined): ItemIcon | undefined {
  const k = (ICONS.kinds as Record<string, { file: string; alt: string }>)[kind ?? ""];
  return k ? { src: `${ICONS.servedAt}/${k.file}`, alt: k.alt } : undefined;
}

/** W13: the icon's alt text next to a label: empty (decorative) when the label already names the item type, so a screen
 * reader says "Semantic model" once, not "Semantic model Semantic model"; the type otherwise ("Notebook" beside "Silver
 * notebook" is kept: it says which Fabric item the output is). */
export function altBeside(alt: string, label: string | undefined): string {
  return label && label.toLowerCase().includes(alt.toLowerCase()) ? "" : alt;
}

/** WB11: the icon of a Fabric item type as the REST API names it (Lakehouse, Notebook, GraphQLApi, ...), or undefined. */
export function typeIcon(type: string | undefined): ItemIcon | undefined {
  const k = (ICONS.types as Record<string, { file: string; alt: string }>)[type ?? ""];
  return k ? { src: `${ICONS.servedAt}/${k.file}`, alt: k.alt } : undefined;
}

/** WB11: every Fabric item type the editor can name, with its icon (or the documented fallback). */
export const ICON_TYPES: string[] = Object.keys(ICONS.types);

/** WB11: the item type's word, as the icon's alt says it (Lakehouse, SQL database, Activator, ...). */
export function typeWord(type: string | undefined): string | undefined {
  return typeIcon(type)?.alt;
}

/** WB11: Fabric's REST item type of each output kind (what Create makes). */
export const KIND_TYPE: Record<string, string> = {
  silver_notebook: "Notebook", gold_views: "Notebook", ds_features: "Notebook", pipeline: "DataPipeline",
  semantic_model: "SemanticModel", report: "Report", graphql: "GraphQLApi", ontology: "Ontology", data_agent: "DataAgent",
  rayfin_app: "AppBackend",
};

export const TRADEMARK = "Microsoft, Microsoft Fabric and Power BI are trademarks of the Microsoft group of companies.";

/** What the editor's "About and notices" shows. */
export const NOTICES: string[] = [
  `The item icons beside the names of Fabric item types are Microsoft's Fabric icons from the npm package ${ICON_PACKAGE}, used unmodified ` +
    "under the terms on Microsoft Learn (Microsoft Fabric product, experience, and item icons, " +
    `${ICONS.terms}), which offer the package for use in Microsoft Fabric platform extension development. ` +
    "Microsoft reserves all other rights. They show which kind of Fabric item an output creates; Krusgraph is an " +
    "independent product, not made or endorsed by Microsoft.",
  TRADEMARK,
];
