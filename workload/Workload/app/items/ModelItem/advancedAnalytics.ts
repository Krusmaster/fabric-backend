/**
 * ED3: Advanced analytics on the Data product step (Gustav, 21 November 2026: "vart är advanced analytics-spåret?").
 * The analyses analysis_plan recommends (round AP1, shown since WB4) become notebooks Krusgraph can create in this
 * item's workspace with a dry run first, through the starter route. Pure helpers (advancedAnalytics.test.ts).
 */
import type { AnalysisCard } from "./analysisPlan";
import type { CreatedItem } from "./ModelItemDefinition";
import { ident } from "./nextSteps";

/** The notebook's name in Fabric: the downloaded file's name without .ipynb (letters, digits and underscores). */
export function analysisName(c: AnalysisCard, _where?: { displayName: string; schema: string }): string {
  const base = c.action.kind === "notebook" ? c.action.filename.replace(/\.ipynb$/i, "") : `${c.id}_${c.title}`;
  return ident(base).slice(0, 123);
}

/** The code cells of an .ipynb (nbformat 4), else the code split where the notebook's cell markers are. */
export function ipynbCells(content: string | undefined, code?: string): string[] {
  try {
    const nb = JSON.parse(content ?? "") as { cells?: { cell_type?: string; source?: string | string[] }[] };
    const cells = (nb.cells ?? []).filter((c) => c.cell_type === "code")
      .map((c) => (Array.isArray(c.source) ? c.source.join("") : c.source ?? "")).filter((t) => t.trim());
    if (cells.length) return cells.slice(0, 12);
  } catch {
    /* not JSON: the code below */
  }
  const parts = (code ?? "").split(/\n# ----\n/).map((t) => t.trim()).filter(Boolean);
  return (parts.length ? parts : [code ?? ""]).slice(0, 12);
}

/** The notebook this item already created for the analysis (outputs.json), if any. */
export function madeFor(c: AnalysisCard, created: CreatedItem[] | undefined, where?: { displayName: string; schema: string }): CreatedItem | undefined {
  const name = analysisName(c, where).toLowerCase();
  return [...(created ?? [])].reverse().find((x) => x.type === "Notebook" && x.id
    && (x.output === `analysis_${c.id}` || x.name.toLowerCase() === name));
}

/** The default tick: the top recommendation that has a notebook here, and only that one. */
export function pickedByDefault(cards: AnalysisCard[]): string[] {
  const top = cards.find((c) => c.readiness !== "missing" && c.action.kind === "notebook");
  return top ? [top.id] : [];
}
