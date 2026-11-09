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

export const TRADEMARK = "Microsoft, Microsoft Fabric and Power BI are trademarks of the Microsoft group of companies.";

/** What the editor's "About and notices" shows. */
export const NOTICES: string[] = [
  `The item icons on the output cards are Microsoft's Fabric icons from the npm package ${ICON_PACKAGE}, used unmodified ` +
    "under the terms on Microsoft Learn (Microsoft Fabric product, experience, and item icons, " +
    `${ICONS.terms}), which offer the package for use in Microsoft Fabric platform extension development. ` +
    "Microsoft reserves all other rights. They show which kind of Fabric item an output creates; Krusgraph is an " +
    "independent product, not made or endorsed by Microsoft.",
  TRADEMARK,
];
