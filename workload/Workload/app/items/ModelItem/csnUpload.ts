/**
 * WB5: a CSN file chosen in the editor. Read in the browser, checked here, kept only in the item's definition
 * (source.json) and sent with review and check (csn_upload); the engine checks it again and never logs it. The same
 * rule as a CSN in the lakehouse's Files (fabric_backend/csn_onelake.is_csn): a `definitions` object and a version
 * marker. Pure functions, so they run in unit tests (csnUpload.test.ts).
 */
export const CSN_MAX_BYTES = 5 * 1024 * 1024;

export interface CsnUpload {
  name: string;
  csn: Record<string, unknown>;
}

export type CsnRead = { ok: true; value: CsnUpload } | { ok: false; error: string };

export function isCsn(obj: unknown): string | null {
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return "The file is not a JSON object.";
  const o = obj as Record<string, unknown>;
  if (!o.definitions || typeof o.definitions !== "object" || Array.isArray(o.definitions)) {
    return "The file has no 'definitions' object, so it is not a CSN export.";
  }
  const ver = o.version as Record<string, unknown> | undefined;
  if (!(o.$version || o.csnInteropEffective || (ver && typeof ver === "object" && ver.csn))) {
    return "The file has no '$version' or 'csnInteropEffective', so it is not recognised as CSN.";
  }
  return null;
}

/** The file's text as a CSN upload, or the one sentence that says why not. */
export function readCsn(name: string, size: number, text: string): CsnRead {
  if (!/\.(json|csn)$/i.test(name)) return { ok: false, error: "Choose a .json or .csn file (a CSN export of the SAP data model)." };
  if (size > CSN_MAX_BYTES) return { ok: false, error: `The file is larger than ${CSN_MAX_BYTES / (1024 * 1024)} MB.` };
  let obj: unknown;
  try {
    obj = JSON.parse(text.replace(/^﻿/, ""));
  } catch {
    return { ok: false, error: "The file is not valid JSON." };
  }
  const why = isCsn(obj);
  if (why) return { ok: false, error: why };
  return { ok: true, value: { name: name.slice(0, 120), csn: obj as Record<string, unknown> } };
}

/** The number of entities the CSN defines, for the line under the file name. */
export function entityCount(csn: Record<string, unknown>): number {
  const defs = csn.definitions as Record<string, { kind?: string }>;
  return Object.values(defs).filter((d) => d && typeof d === "object" && d.kind === "entity").length;
}
