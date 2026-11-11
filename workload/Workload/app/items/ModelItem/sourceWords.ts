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
  SQLDbNative: "SQLDatabase",
  MountedRelationalDatabase: "MirroredDatabase",
  "mounted-warehouse": "MirroredDatabase",
  "data-warehouse": "Warehouse",
  "lake-warehouse": "Lakehouse",
};

/** The picker's item type as the REST API names it. */
export function restType(type?: string): string | undefined {
  return type ? (SAME[type] ?? type) : type;
}

const LABELS: Record<string, string> = {
  Lakehouse: "Lakehouse",
  Warehouse: "Warehouse",
  SQLDatabase: "SQL database",
  MirroredDatabase: "Mirrored database",
};

export function sourceLabel(type?: string): string {
  return LABELS[type ?? ""] ?? (type ? type : "Source");
}

/** Spark cannot write into it: everything but a lakehouse. An unknown type (an item saved before n201) is a lakehouse. */
export function isReadOnly(type?: string): boolean {
  return !!type && type !== "Lakehouse" && type !== "TODO";
}

export function sourceButton(source?: { itemType?: string; displayName: string }): string {
  return source ? `${sourceLabel(source.itemType)}: ${source.displayName}` : "Choose a source";
}

export interface TargetChoice {
  itemId: string;
  displayName: string;
}

export function targetButton(target?: TargetChoice): string {
  return target ? `Target lakehouse: ${target.displayName}` : "Target lakehouse: the first of this workspace (default)";
}

export function targetLine(source: { itemType?: string; displayName: string }, target?: TargetChoice): string {
  const what = sourceLabel(source.itemType).toLowerCase();
  return (
    `A ${what} is read-only: Krusgraph reads ${source.displayName} and writes the silver tables, the gold views and the ` +
    `pipeline's check to ${target ? `the lakehouse ${target.displayName}` : "the first lakehouse of this workspace, unless you choose one"}. ` +
    "The dry run says which."
  );
}

/** The target must be a lakehouse of the source's workspace: what Create builds lives there. */
export function targetProblem(sourceWorkspace: string, picked: { workspaceId: string; type?: string }): string | undefined {
  if (picked.type && picked.type !== "Lakehouse") return "Choose a lakehouse as the target.";
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
