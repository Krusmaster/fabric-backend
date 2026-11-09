/**
 * n181: the App (Rayfin, preview) output in words and as data the card reads (fabric_backend/rayfin_app.py). Pure
 * functions, no React, no Fabric client, so they run in unit tests (appWords.test.ts).
 *
 * The dry run of the App gives: the preflight (is "Enable Fabric App Items (preview)" on), the options with their
 * defaults (key figures, list pages, charts: rules over the plan, no AI), the pages, the read-only connector and its
 * GraphQL API with every link, the package (zip) and the commands. The ticks are stored in outputs.json
 * (OutputChoice.app) and sent with the next dry run and Create.
 */
import { OutputChoice } from "./ModelItemDefinition";
import { AppChartType, AppChoices, BuildCard } from "./engineClient";

export interface AppOption {
  id: string;
  label: string;
  default: boolean;
  why: string;
}

export interface AppChartOption extends AppOption {
  kind?: "category" | "time";
  types?: AppChartType[];
  type?: AppChartType;
}

export interface AppOptions {
  kpis: AppOption[];
  tables: AppOption[];
  charts: AppChartOption[];
  /** n189: the slicers; each applies to the key figures and charts whose table links to it */
  filters?: AppOption[];
  pages?: { id: string; label: string }[];
  accents?: { id: string; label: string; light: string; dark: string }[];
  left_out?: string[];
}

/** n189: the look and the layout the dry run used (rayfin_app.package's `design`). */
export interface AppDesign {
  accent: string;
  accent_colours: { light: string; dark: string };
  page_order: string[];
  charts: { id: string; label: string; type: AppChartType }[];
  filters: { id: string; label: string; kind: "values" | "dates"; reaches: string[] }[];
  last_refresh: string | null;
  look: string;
}

type TickGroup = "kpis" | "tables" | "charts" | "filters";

export interface AppPreflight {
  status: "on" | "off" | "unknown";
  setting?: string;
  note?: string;
  reason?: string;
}

export interface AppApi {
  connector: string;
  connector_type: string;
  operations: string[];
  read_only: boolean;
  mutations: string[];
  types: { type: string; queries: string[] }[];
  links: { from: string; to: string; rule: string }[];
  note: string;
}

export const GROUPS: { key: TickGroup; title: string }[] = [
  { key: "kpis", title: "Key figures" },
  { key: "tables", title: "List pages" },
  { key: "charts", title: "Charts" },
  { key: "filters", title: "Filters (slicers on the overview)" },
];

export const CHART_TYPE_WORDS: Record<AppChartType, string> = { bar: "Bar", line: "Line", table: "Table" };

/** n189: the link on the card to the package's EDIT-WITH-AI.md */
export const EDIT_TITLE = "Change the app yourself";
export const EDIT_NOTE = "Open the project in Claude (with Krusgraph for Claude), VS Code or Lovable: a prompt to start from, the "
  + "rules (read-only connector, no secrets in code, keep the type check green) and how to publish again with npx rayfin up. "
  + "The same file is in the package.";

export const PREVIEW_NOTE = "Fabric Apps and Rayfin are in preview.";

export function isApp(c: BuildCard): boolean {
  return c.output === "rayfin_app";
}

/** The admin card: the App item setting is off (preflight, or Fabric's own 403 "The feature is not available"). */
export function featureOff(c: BuildCard): { error: string; setting: string; where: string; steps: string[] } | undefined {
  const a = (c.refusal ?? c.answer) as Record<string, any> | undefined;
  if (!a || a.kind !== "feature_disabled") return undefined;
  return { error: String(a.error), setting: String(a.setting ?? "Enable Fabric App Items (preview)"), where: String(a.where ?? ""), steps: a.admin_steps ?? [] };
}

export function optionsOf(c: BuildCard): AppOptions | undefined {
  return c.answer?.options as AppOptions | undefined;
}

/** The ticks to show: the person's own (outputs.json), else what the dry run used (the defaults). n189: the filters,
 * chart types, page order and accent come along when the dry run (or the person) has them. */
export function ticked(c: BuildCard, saved?: AppChoices): AppChoices {
  const ch = c.answer?.chosen as AppChoices | undefined;
  if (saved) {
    // an outputs.json from before n189 has no filters, types, order or accent: show what the dry run used for them
    return {
      ...(ch?.filters && !saved.filters ? { filters: ch.filters } : {}),
      ...(ch?.chart_types && !saved.chart_types ? { chart_types: ch.chart_types } : {}),
      ...(ch?.page_order && !saved.page_order ? { page_order: ch.page_order } : {}),
      ...(ch?.accent && !saved.accent ? { accent: ch.accent } : {}),
      ...saved,
    };
  }
  return {
    kpis: ch?.kpis ?? [], tables: ch?.tables ?? [], charts: ch?.charts ?? [],
    ...(ch?.filters ? { filters: ch.filters } : {}),
    ...(ch?.chart_types ? { chart_types: ch.chart_types } : {}),
    ...(ch?.page_order ? { page_order: ch.page_order } : {}),
    ...(ch?.accent ? { accent: ch.accent } : {}),
  };
}

export function toggle(choices: AppChoices, group: TickGroup, id: string, on: boolean): AppChoices {
  const rest = (choices[group] ?? []).filter((x) => x !== id);
  return { ...choices, [group]: on ? [...rest, id] : rest };
}

/** n189: the ticked charts with the types each allows and the one chosen (the option's default when none). */
export function chartTypes(opts: AppOptions | undefined, choices: AppChoices): { id: string; label: string; types: AppChartType[]; type: AppChartType }[] {
  return (opts?.charts ?? [])
    .filter((o) => choices.charts.includes(o.id))
    .map((o) => {
      const types = o.types ?? ["bar", "table"];
      const want = choices.chart_types?.[o.id];
      return { id: o.id, label: o.label, types, type: want && types.includes(want) ? want : o.type ?? types[0] };
    });
}

export function setChartType(choices: AppChoices, id: string, type: AppChartType): AppChoices {
  return { ...choices, chart_types: { ...(choices.chart_types ?? {}), [id]: type } };
}

/** n189: the pages the ticks make, in the chosen order (the overview first unless moved; then the list pages). */
export function pagesInOrder(opts: AppOptions | undefined, choices: AppChoices): { id: string; label: string }[] {
  const label = new Map((opts?.pages ?? []).map((p) => [p.id, p.label]));
  const ids = [...(choices.kpis.length || choices.charts.length ? ["overview"] : []), ...choices.tables];
  const order = (choices.page_order ?? []).filter((i) => ids.includes(i));
  return [...order, ...ids.filter((i) => !order.includes(i))].map((id) => ({ id, label: label.get(id) ?? id }));
}

/** n189: moves a page up (-1) or down (+1); the whole order is stored, so a later tick lands at the end. */
export function movePage(opts: AppOptions | undefined, choices: AppChoices, id: string, by: -1 | 1): AppChoices {
  const ids = pagesInOrder(opts, choices).map((p) => p.id);
  const i = ids.indexOf(id);
  const j = i + by;
  if (i < 0 || j < 0 || j >= ids.length) return choices;
  [ids[i], ids[j]] = [ids[j], ids[i]];
  return { ...choices, page_order: ids };
}

export function setAccent(choices: AppChoices, accent: string): AppChoices {
  return { ...choices, accent };
}

/** n189: what the dry run says about the look and the layout, in plain lines. */
export function designLines(d: AppDesign | undefined): string[] {
  if (!d) return [];
  return [
    `Accent: ${d.accent} (${d.accent_colours.light} in light, ${d.accent_colours.dark} in dark)`,
    `Pages, in this order: ${d.page_order.join(", ")}`,
    ...d.charts.map((c) => `${c.label}: ${CHART_TYPE_WORDS[c.type].toLowerCase()} chart`),
    ...(d.filters.length
      ? d.filters.map((f) => `Filter ${f.label} (${f.kind === "dates" ? "a date range" : "a value list"}): applies to ${f.reaches.length ? f.reaches.join(", ") : "nothing ticked"}`)
      : ["No filters"]),
    d.last_refresh ? `Last refresh: the latest ${d.last_refresh}` : "Last refresh: when the page read the data (the plan has no load-time column)",
    d.look,
  ];
}

/** n189: a data: URL for EDIT-WITH-AI.md, to open or save from the card. */
export function editHref(edit: { markdown: string } | undefined): string | undefined {
  return edit?.markdown ? `data:text/markdown;charset=utf-8,${encodeURIComponent(edit.markdown)}` : undefined;
}

export function nothingTicked(c: AppChoices): boolean {
  return !c.kpis.length && !c.tables.length && !c.charts.length;
}

/** The output choices with the App's ticks stored on it. */
export function withAppChoices(choices: OutputChoice[], app: AppChoices): OutputChoice[] {
  return choices.map((c) => (c.type === "rayfin_app" ? { ...c, app } : c));
}

export function preflightWords(p: AppPreflight | undefined): string | undefined {
  if (!p) return undefined;
  if (p.status === "on") return `Fabric App items are on. ${p.note ?? ""}`.trim();
  if (p.status === "off") return "Fabric App items are off for your organisation.";
  return `Could not check whether Fabric App items are on (${p.reason ?? "no permission to read tenant settings"}). ${p.note ?? ""}`.trim();
}

/** The connector and its API in plain lines: read-only, no mutation types, and every link. */
export function apiLines(api: AppApi | undefined): string[] {
  if (!api) return [];
  const access = api.read_only && !api.mutations.length
    ? "read-only: queries only, no mutations"
    : `allows ${api.mutations.join(", ")}`;
  return [
    `Connector ${api.connector} (${api.connector_type}), operations ${api.operations.join(", ")}: ${access}`,
    `${api.types.length} type(s), ${api.links.length} link(s)`,
    ...api.links.map((l) => `${l.from} → ${l.to} (${l.rule})`),
  ];
}

/** A data: URL for the package's zip (the engine sends it base64), to download from the card. */
export function packageHref(pkg: { zip_base64: string } | undefined): string | undefined {
  return pkg?.zip_base64 ? `data:application/zip;base64,${pkg.zip_base64}` : undefined;
}
