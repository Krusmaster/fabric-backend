/**
 * The Krusgraph Model's item definition: what Fabric stores for the item (docs/WORKLOAD-FEASIBILITY.md section 3).
 *
 * Four text parts, each JSON with its own version so an older definition restored from Git can be read and migrated:
 *   review.json   the review file the engine wrote (fabric_backend/review.py): plan, each key and relationship with its
 *                 rule, review status and check status. Names, types, rules, decisions and counts only: never a row
 *                 value, a token or a secret. Its own format and version come from the engine.
 *   source.json   which lakehouse and schema the model reads
 *   outputs.json  what to build (phase 1: an API for GraphQL) and the ids of what was created
 *   item.json     the definition format version and the editor's last view
 *
 * Pure functions, no React and no Fabric client, so they run in unit tests (ModelItemDefinition.test.ts).
 */

export const DEFINITION_VERSION = 1;
export const ITEM_FORMAT = "krusgraph-model";
export const PARTS = {
  review: "review.json",
  source: "source.json",
  outputs: "outputs.json",
  item: "item.json",
} as const;

export type ModelView = "empty" | "review" | "outputs" | "preview" | "result";
export type ReviewStatus = "proposed" | "accepted" | "rejected" | "open";

/** One key or relationship of the review file, as review.py writes it. */
export interface ReviewItem {
  id: string;
  type: "key" | "relationship";
  rule: string;
  columns: string[];
  table?: string;
  source?: string;
  target?: string;
  target_columns?: string[];
  review: ReviewStatus;
  reason?: string;
  check?: { status: string; verdict?: string };
  proposed?: { columns: string[]; rule: string };
}

/** The review file (format "krusgraph-review"); only the fields the editor reads are typed. */
export interface ReviewFile {
  format: "krusgraph-review";
  version: number;
  plan_id: string;
  source: { platform?: string; source?: string; schema?: string };
  items: ReviewItem[];
  open_questions?: { about: string; question: string }[];
  [key: string]: unknown;
}

export interface SourceDefinition {
  version: number;
  platform: "fabric";
  workspaceId: string;
  itemId: string;
  itemType: string;
  displayName: string;
  schema: string;
}

export interface CreatedItem {
  type: string;
  id: string;
  name: string;
  workspace: string;
}

export interface OutputChoice {
  type: "graphql";
  name: string;
  enabled: boolean;
  writable: false;
}

export interface OutputsDefinition {
  version: number;
  outputs: OutputChoice[];
  created: CreatedItem[];
}

export interface ItemSettings {
  version: number;
  format: typeof ITEM_FORMAT;
  view: ModelView;
}

export interface ModelDefinition {
  item: ItemSettings;
  source?: SourceDefinition;
  outputs: OutputsDefinition;
  review?: ReviewFile;
}

/** The parts as the workload client sends and receives them (ItemDefinitionPart). */
export interface DefinitionPart {
  path: string;
  payload: string;
  payloadType: string;
}

export class DefinitionError extends Error {}

export function emptyDefinition(): ModelDefinition {
  return {
    item: { version: DEFINITION_VERSION, format: ITEM_FORMAT, view: "empty" },
    outputs: { version: DEFINITION_VERSION, outputs: [], created: [] },
  };
}

/** The default API name for a source: the lakehouse name plus _api, in the characters Fabric item names allow. */
export function defaultApiName(displayName: string): string {
  const base = (displayName || "model").replace(/[^A-Za-z0-9_]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "") || "model";
  return `${base}_api`.slice(0, 123);
}

// ------------------------------------------------------------------ base64 that keeps non-ASCII names intact ------

export function encodeJson(value: unknown): string {
  const bytes = new TextEncoder().encode(JSON.stringify(value, null, 2));
  let bin = "";
  bytes.forEach((b) => (bin += String.fromCharCode(b)));
  return btoa(bin);
}

export function decodeJson<T = unknown>(payload: string): T {
  const bin = atob(payload);
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes)) as T;
}

// ------------------------------------------------------------------ save -----------------------------------------------

/** The definition as parts to save. A part is left out until it has content (no review before a source is chosen). */
export function toParts(def: ModelDefinition): DefinitionPart[] {
  const part = (path: string, value: unknown): DefinitionPart => ({ path, payload: encodeJson(value), payloadType: "InlineBase64" });
  const parts = [part(PARTS.item, { ...def.item, version: DEFINITION_VERSION, format: ITEM_FORMAT })];
  if (def.source) parts.push(part(PARTS.source, { ...def.source, version: DEFINITION_VERSION }));
  parts.push(part(PARTS.outputs, { ...def.outputs, version: DEFINITION_VERSION }));
  if (def.review) parts.push(part(PARTS.review, def.review));
  return parts;
}

// ------------------------------------------------------------------ load and migrate -----------------------------------

function versionOf(obj: { version?: unknown } | undefined, part: string): number {
  if (!obj) return DEFINITION_VERSION;
  const v = obj.version;
  if (v === undefined) return 1; // written before the field existed: read as version 1
  if (typeof v !== "number" || !Number.isInteger(v) || v < 1) {
    throw new DefinitionError(`${part} has an invalid version: ${JSON.stringify(v)}`);
  }
  if (v > DEFINITION_VERSION) {
    throw new DefinitionError(`${part} was saved by a newer Krusgraph (version ${v}); this editor reads version ${DEFINITION_VERSION}.`);
  }
  return v;
}

/** Version 1 is the first format, so migrating means filling defaults. Later versions add a step here per version. */
export function migrate(def: ModelDefinition): ModelDefinition {
  return {
    item: { version: DEFINITION_VERSION, format: ITEM_FORMAT, view: def.item?.view ?? (def.review ? "review" : "empty") },
    source: def.source ? { ...def.source, version: DEFINITION_VERSION, schema: def.source.schema || "dbo" } : undefined,
    outputs: {
      version: DEFINITION_VERSION,
      outputs: def.outputs?.outputs ?? [],
      created: def.outputs?.created ?? [],
    },
    review: def.review,
  };
}

/** The parts Fabric returned (getItemDefinition) as a definition. Unknown parts (.platform and others) are ignored. */
export function fromParts(parts: DefinitionPart[] | undefined): ModelDefinition {
  if (!parts || parts.length === 0) return emptyDefinition();
  const read = <T>(path: string): T | undefined => {
    const p = parts.find((x) => x.path === path);
    if (!p) return undefined;
    try {
      return decodeJson<T>(p.payload);
    } catch {
      throw new DefinitionError(`${path} is not valid JSON`);
    }
  };
  const item = read<ItemSettings>(PARTS.item);
  const source = read<SourceDefinition>(PARTS.source);
  const outputs = read<OutputsDefinition>(PARTS.outputs);
  const review = read<ReviewFile>(PARTS.review);
  versionOf(item, PARTS.item);
  versionOf(source, PARTS.source);
  versionOf(outputs, PARTS.outputs);
  if (item && item.format !== undefined && item.format !== ITEM_FORMAT) {
    throw new DefinitionError(`item.json is not a ${ITEM_FORMAT} definition`);
  }
  if (review && review.format !== "krusgraph-review") {
    throw new DefinitionError("review.json is not a Krusgraph review file");
  }
  return migrate({ item: item as ItemSettings, source, outputs: outputs as OutputsDefinition, review });
}

// ------------------------------------------------------------------ review helpers ------------------------------------

const ORDER: Record<ReviewStatus, number> = { open: 0, proposed: 1, accepted: 2, rejected: 3 };

/** List-first review: open items first, then what is still only proposed, then decided ones; keys before relationships. */
export function sortForReview(items: ReviewItem[]): ReviewItem[] {
  return [...items].sort(
    (a, b) =>
      ORDER[a.review] - ORDER[b.review] ||
      (a.type === b.type ? 0 : a.type === "key" ? -1 : 1) ||
      a.id.localeCompare(b.id)
  );
}

/** The rule pill: K for a key rule (K0-K5), R for a relationship rule (R0-R5, confirmed). */
export function rulePill(item: ReviewItem): "K" | "R" {
  return item.type === "key" ? "K" : "R";
}

export function describe(item: ReviewItem): string {
  if (item.type === "key") return `${item.table}: ${item.columns.join(" + ")}`;
  return `${item.source}.${item.columns.join("+")} → ${item.target}.${(item.target_columns ?? []).join("+")}`;
}

/** The review with one item's decision changed; the engine re-reads the decisions when the item is re-opened or built. */
export function decide(review: ReviewFile, id: string, status: ReviewStatus, reason = ""): ReviewFile {
  if (!review.items.some((it) => it.id === id)) throw new DefinitionError(`no item ${id} in the review`);
  return { ...review, items: review.items.map((it) => (it.id === id ? { ...it, review: status, reason } : it)) };
}

export function counts(review: ReviewFile | undefined): Record<ReviewStatus, number> & { keys: number; relationships: number } {
  const c = { open: 0, proposed: 0, accepted: 0, rejected: 0, keys: 0, relationships: 0 };
  for (const it of review?.items ?? []) {
    c[it.review] += 1;
    if (it.type === "key") c.keys += 1;
    else c.relationships += 1;
  }
  return c;
}
