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
import { AppChoices, BuildCard } from "./engineClient";

export interface AppOption {
  id: string;
  label: string;
  default: boolean;
  why: string;
}

export interface AppOptions {
  kpis: AppOption[];
  tables: AppOption[];
  charts: AppOption[];
  left_out?: string[];
}

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

export const GROUPS: { key: keyof AppChoices; title: string }[] = [
  { key: "kpis", title: "Key figures" },
  { key: "tables", title: "List pages" },
  { key: "charts", title: "Charts" },
];

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

/** The ticks to show: the person's own (outputs.json), else what the dry run used (the defaults). */
export function ticked(c: BuildCard, saved?: AppChoices): AppChoices {
  if (saved) return saved;
  const ch = c.answer?.chosen as AppChoices | undefined;
  return { kpis: ch?.kpis ?? [], tables: ch?.tables ?? [], charts: ch?.charts ?? [] };
}

export function toggle(choices: AppChoices, group: keyof AppChoices, id: string, on: boolean): AppChoices {
  const rest = choices[group].filter((x) => x !== id);
  return { ...choices, [group]: on ? [...rest, id] : rest };
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
