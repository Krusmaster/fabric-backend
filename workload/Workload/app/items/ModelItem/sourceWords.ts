/**
 * n201: the sources the Krusgraph Model reads and the words around them. A lakehouse, a warehouse, a SQL database or a
 * mirrored database (Azure SQL, SQL Server, Snowflake, SAP via SAP Datasphere, open mirroring...): the review and the
 * check read its SQL analytics endpoint, read-only, as before. Everything but a lakehouse is read-only, so the silver
 * notebook, the gold views and the pipeline's check are written to a lakehouse the person picks (Target lakehouse),
 * by default the first lakehouse of the workspace, and the dry run says which (fabric_backend/mirroring.py).
 *
 * The SAP pack: when the tables are SAP's, the engine marks the pack's keys and links "from the SAP pack" with the pack's
 * public sources (answer.sap); each is accepted or rejected as any other item. Nothing here invents a key or a link.
 */

/** The item types the Model reads, as Fabric's REST API names them; the engine's mirroring.SOURCE_TYPES. */
export const SOURCE_TYPES = ["Lakehouse", "Warehouse", "SQLDatabase", "MirroredDatabase"];

/** What the source picker (datahub.openDialog) is asked for. The workload client's FabricItemTypes list names a SQL
 * database "SQLDbNative" and lists no "MirroredDatabase"; the dialog's name for a mirrored database is not documented
 * (Unverified), so the REST name and the client's two candidates are passed. The engine answers the item's real type
 * (review answer source_kind), which replaces what the picker said. */
export const PICKER_TYPES = ["Lakehouse", "Warehouse", "SQLDbNative", "SQLDatabase", "MirroredDatabase", "MountedRelationalDatabase", "mounted-warehouse"];

const SAME: Record<string, string> = {
  sqldbnative: "SQLDatabase",
  mountedrelationaldatabase: "MirroredDatabase",
  "mounted-warehouse": "MirroredDatabase",
  "data-warehouse": "Warehouse",
  "lake-warehouse": "Lakehouse",
  lakehouse: "Lakehouse",
  warehouse: "Warehouse",
  sqldatabase: "SQLDatabase",
  mirroreddatabase: "MirroredDatabase",
};

/** n215: the picker's item type as the REST API names it, or undefined when it is not a name. The host's datahub item
 * carries its type in fabricItemType (a string) and in itemType, which the workload client types as `any` and which
 * can be Fabric's numeric enum: a number stored as the source's type made isReadOnly true and sourceLabel(...)
 * .toLowerCase() throw during render, and the editor went white after a lakehouse was picked. Case is ignored. */
export function restType(type?: unknown): string | undefined {
  if (typeof type !== "string" || !type.trim()) return undefined;
  const t = type.trim();
  return SAME[t.toLowerCase()] ?? t;
}

const LABELS: Record<string, string> = {
  Lakehouse: "Lakehouse",
  Warehouse: "Warehouse",
  SQLDatabase: "SQL database",
  MirroredDatabase: "Mirrored database",
};

export function sourceLabel(type?: unknown): string {
  const t = restType(type);
  return (t && LABELS[t]) ?? t ?? "Source";
}

/** Spark cannot write into it: everything but a lakehouse. An unknown type (an item saved before n201) is a lakehouse. */
export function isReadOnly(type?: unknown): boolean {
  const t = restType(type);
  return !!t && t !== "Lakehouse" && t !== "TODO";
}

export function sourceButton(source?: { itemType?: unknown; displayName: string }): string {
  return source ? `${sourceLabel(source.itemType)}: ${source.displayName}` : "Choose a source";
}

export interface TargetChoice {
  itemId: string;
  displayName: string;
}

export function targetButton(target?: TargetChoice): string {
  return target ? `Target lakehouse: ${target.displayName}` : "Target lakehouse: the first of this workspace (default)";
}

export function targetLine(source: { itemType?: unknown; displayName: string }, target?: TargetChoice): string {
  const what = sourceLabel(source.itemType).toLowerCase();
  return (
    `A ${what} is read-only: Krusgraph reads ${source.displayName} and writes the silver tables, the gold views and the ` +
    `pipeline's check to ${target ? `the lakehouse ${target.displayName}` : "the first lakehouse of this workspace, unless you choose one"}. ` +
    "The dry run says which."
  );
}

/** The target must be a lakehouse of the source's workspace: what Create builds lives there. */
export function targetProblem(sourceWorkspace: string, picked: { workspaceId: string; type?: unknown }): string | undefined {
  const t = restType(picked.type);
  if (t && t !== "Lakehouse") return "Choose a lakehouse as the target.";
  if (picked.workspaceId !== sourceWorkspace) return "Choose a lakehouse in the same workspace as the source.";
  return undefined;
}

/** What the engine sends with the review of a read-only source. */
export interface ReadOnlySource {
  kind: string;
  words: string;
  mirroring?: string;
}

export interface PackSource {
  title: string;
  url: string;
}

export interface SapItem {
  from: string;
  sources: PackSource[];
  client?: string;
  pack_table?: string;
  text?: string;
  module?: string;
}

export interface SapOffer {
  pack: string;
  label: string;
  items: Record<string, SapItem>;
  note: string;
  mirroring: string;
  licence: string;
  status: string;
  client_dropped: boolean;
  learn: Record<string, string>;
  /** WB5: the SAP fields in plain words, only from what the pack documents ({table: [{column, words}]}) */
  fields?: Record<string, { column: string; words: string }[]>;
}

/** WB5: the pack's field meanings as rows, table by table in name order, columns in the table's order. */
export function sapFieldRows(offer: SapOffer | undefined): { table: string; column: string; words: string }[] {
  const f = offer?.fields ?? {};
  return Object.keys(f).sort().flatMap((table) => (f[table] ?? []).map((r) => ({ table, column: r.column, words: r.words })));
}

/** The line under a review row that came from the SAP pack: "from the SAP pack", the client column, the sources. */
export function sapMark(offer: SapOffer | undefined, id: string): { text: string; sources: PackSource[] } | undefined {
  const it = offer?.items?.[id];
  if (!it) return undefined;
  const client = it.client ? `, with the client column ${it.client}` : "";
  const table = it.pack_table && it.text ? ` (${it.pack_table}: ${it.text})` : "";
  return { text: `${it.from}${table}${client}. Not checked against your rows until you check them.`, sources: it.sources ?? [] };
}

/** The notes above the review, in order: read-only, what mirroring delivers, the SAP pack, the licence. */
export function sourceNotes(readOnly?: ReadOnlySource, sap?: SapOffer): string[] {
  const out: string[] = [];
  if (readOnly?.words) out.push(readOnly.words);
  if (readOnly?.mirroring) out.push(readOnly.mirroring);
  else if (sap?.mirroring) out.push(sap.mirroring);
  if (sap?.note) out.push(sap.note);
  if (sap?.licence) out.push(sap.licence);
  return out;
}

/** W13: why the schemas could not be listed, in words for the person (the engine's error names the route and the
 * workspace's id: "no access to schemas: workspace '1111…', source 'demo_lh' (HTTP 403 …)"). No access: say so and what
 * to ask for, and offer another source; anything else: the engine's sentence, then how to go on. */
export function schemaProblem(error: { error: string; kind: string; hint?: string }, sourceName: string): { line: string; typeIt: boolean } {
  const name = sourceName || "this source";
  if (error.kind === "no_access") {
    return {
      line: `Your sign-in cannot open ${name}. Ask the workspace's admin for access (Viewer is enough to find keys and links, ` +
        "Contributor to create), or choose another source.",
      typeIt: false,
    };
  }
  return { line: `The schemas could not be listed: ${error.error} Type the schema as the lakehouse spells it.`, typeIt: true };
}

// ------------------------------------------------------------------ W1: the schema list of Choose a source ----------
// Gustav's test in a real tenant, 23 November 2026: a lakehouse listed "_rsc (no tables)", a Fabric system schema, as a
// choice; and the schemas Krusgraph itself writes (silver, gold, krusgraph, sap_silver, ...) sat among the real source
// schemas as if they were sources. The list now leaves system schemas out, puts the source schemas first and marks
// Krusgraph's own. Only the list changes: a schema typed or saved by name is sent to the engine as it is, and the engine
// still plans it.

/** Schemas Fabric and SQL keep for themselves (the engine's SCHEMATA_SQL leaves the same names out; any name starting
 * with "_", such as _rsc, is Fabric's). Case is ignored. */
export const SYSTEM_SCHEMAS = ["sys", "information_schema", "queryinsights", "guest"];

export function isSystemSchema(name: string): boolean {
  const n = (name ?? "").trim().toLowerCase();
  return n.startsWith("_") || SYSTEM_SCHEMAS.includes(n);
}

/** The names Krusgraph writes, from the engine's own naming:
 * - "krusgraph" and "krusgraph_*": Krusgraph's fixed schemas (the views of create_views and the pipeline's check, the
 *   health and plans tables, krusgraph_quarantine, krusgraph_analysis, krusgraph_silver). Nothing else uses the name: "written".
 * - "silver" and "gold" (the default schemas of the silver notebook and the gold views, layer_schemas.DEFAULT_SILVER and
 *   DEFAULT_GOLD) and "<name>_silver" / "<name>_gold" (the form a build names them in, such as sap_silver and sap_gold):
 *   Krusgraph writes exactly these, but so may another tool's medallion layers, so the list says only that it looks so. */
export type OwnSchema = "written" | "looks";

export function krusgraphSchema(name: string): OwnSchema | undefined {
  const n = (name ?? "").trim().toLowerCase();
  if (n === "krusgraph" || /^krusgraph_[a-z0-9_]+$/.test(n)) return "written";
  if (n === "silver" || n === "gold" || /^[a-z][a-z0-9_]*_(silver|gold)$/.test(n)) return "looks";
  return undefined;
}

export const OWN_WORDS: Record<OwnSchema, string> = {
  written: "written by Krusgraph",
  looks: "looks like Krusgraph output",
};

export interface SchemaOption {
  schema: string;
  tables: number;
  own?: OwnSchema;
  label: string;
}

function tablesWord(n: number): string {
  return n === 0 ? "no tables" : n === 1 ? "1 table" : `${n} tables`;
}

/** The radio list: system schemas left out, the source schemas first, then Krusgraph's own (each group in the engine's
 * order), each labelled "<schema> (<n> tables)" with ", written by Krusgraph" or ", looks like Krusgraph output". */
export function schemaOptions(list: { schemas: { schema: string; tables: number }[] } | undefined): SchemaOption[] {
  const shown = (list?.schemas ?? []).filter((x) => x && typeof x.schema === "string" && !isSystemSchema(x.schema));
  const option = (x: { schema: string; tables: number }): SchemaOption => {
    const own = krusgraphSchema(x.schema);
    const tables = Number(x.tables) || 0;
    return { schema: x.schema, tables, own, label: `${x.schema} (${tablesWord(tables)}${own ? `, ${OWN_WORDS[own]}` : ""})` };
  };
  const all = shown.map(option);
  return [...all.filter((o) => !o.own), ...all.filter((o) => o.own)];
}

/** True when the list was read and no schema in it (system schemas aside) holds a table. */
export function everySchemaEmpty(list: { schemas: { schema: string; tables: number }[] } | undefined): boolean {
  return !!list && schemaOptions(list).every((o) => o.tables === 0);
}

/** The one sentence for a lakehouse whose schemas are all empty (instead of "Schema 'dbo' has no tables in '<id>' ..."). */
export const EMPTY_LAKEHOUSE =
  "This lakehouse has no tables the SQL analytics endpoint can see. If you just loaded data, open the SQL analytics " +
  "endpoint and choose Refresh. Files under Files must be loaded to Tables first (right-click, Load to Tables).";

/** The docs link the engine's hint ends with ("Step by step: https://…/docs#first-time-errors"), if any. */
export function docsLink(hint?: string): string | undefined {
  const m = /https:\/\/[^\s"'<>]+/.exec(hint ?? "");
  return m ? m[0].replace(/[.,;)]+$/, "") : undefined;
}

/** The review's schema_not_found answer in editor words. Every listed schema empty: EMPTY_LAKEHOUSE and the docs link.
 * Otherwise the engine's first sentence without the workspace id, and a hint without the MCP tool's name (list_tables).
 * Any other error is returned as it is. The MCP tool's own error text is not changed (errors.py). */
export function editorError<E extends { error: string; kind: string; hint?: string }>(
  error: E | undefined,
  list?: { schemas: { schema: string; tables: number }[] }
): E | undefined {
  if (!error || error.kind !== "schema_not_found") return error;
  const link = docsLink(error.hint);
  const more = link ? ` Step by step: ${link}` : "";
  if (everySchemaEmpty(list)) return { ...error, error: EMPTY_LAKEHOUSE, hint: more.trim() || undefined };
  const named = /^Schema ('[^']*'|"[^"]*") has no tables/.exec(error.error);
  return {
    ...error,
    error: named ? `The schema ${named[1]} has no tables the SQL analytics endpoint can see.` : error.error,
    hint: "Choose a schema with tables in the list. If you just loaded data, open the SQL analytics endpoint and choose " +
      "Refresh." + more,
  };
}
