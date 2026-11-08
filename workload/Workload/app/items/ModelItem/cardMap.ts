/**
 * Krusgraph (n173): the plan as a map in the Model editor, drawn by the MCP Apps cards' own code (cardMap.generated.ts,
 * written by workload/scripts/build_card_map.py from fabric_backend/mcp_apps_pictures.py), so the editor and the cards
 * show the same picture: tables with their key columns, links with their rule pill, column pair and check state.
 *
 * The engine sends the map with every answer (/review, /check: workload_api.map_of). Between answers the person decides
 * in the editor (Accept, Reject, Accept all), so overlay() brings the map's review states up to date from the review
 * file; stateClasses() adds what the cards have no use for: a table's key check, and accepted versus proposed. Both are
 * pure and tested (cardMap.test.ts). n174 adds more outputs: a picture of another output goes next to drawPlanMap here,
 * from its own generated drawing (the cards' drawOntology, drawProducts are in the same generated module).
 */
import { ReviewFile } from "./ModelItemDefinition";
import { drawMap } from "./cardMap.generated";

export type LinkState = "passed" | "failed" | "warning" | "empty" | "stale" | "not_checked" | "not_counted";
export type ReviewState = "proposed" | "accepted" | "rejected" | "open";

export interface MapTable {
  name: string;
  key: string[];
  key_rule: string;
  columns: number;
  review?: ReviewState;
  key_check?: "passed" | "failed" | "stale" | "not_checked";
}

export interface MapLink {
  id: string;
  source: string;
  source_cols: string[];
  target: string;
  target_cols: string[];
  rule: string;
  state?: LinkState;
  review?: ReviewState;
  orphans?: number;
  rows_with_value?: number;
}

export interface MapData {
  tables: MapTable[];
  relationships: MapLink[];
  checked?: boolean;
  reviewed?: boolean;
  left_out?: string;
}

const CHECKS: Record<string, LinkState> = { passed: "passed", failed: "failed", stale: "stale" };

/** The map with each table's and link's review and check state taken from the review file (the person's latest
 * decisions and the latest check). Items the review does not have keep what the engine sent. */
export function overlay(map: MapData, review: ReviewFile | undefined): MapData {
  if (!review) return map;
  const items = new Map(review.items.map((it) => [it.id, it]));
  const tables = map.tables.map((t) => {
    const it = items.get(`key:${t.name}`);
    if (!it) return t;
    const s = it.check?.status;
    return { ...t, review: it.review, key_check: s === "passed" || s === "failed" || s === "stale" ? s : "not_checked" } as MapTable;
  });
  let checked = false;
  const relationships = map.relationships.map((r) => {
    const it = items.get(`rel:${r.id}`);
    if (!it) return r;
    const c = (it.check ?? {}) as { status?: string; result?: { orphans?: number; rows_with_value?: number } };
    const state = CHECKS[c.status ?? ""] ?? "not_checked";
    if (state !== "not_checked") checked = true;
    const out: MapLink = { ...r, review: it.review, state };
    if (state !== "not_checked") {
      out.orphans = c.result?.orphans;
      out.rows_with_value = c.result?.rows_with_value;
    } else {
      delete out.orphans;
      delete out.rows_with_value;
    }
    return out;
  });
  return { ...map, tables, relationships, checked: checked || tables.some((t) => t.key_check === "passed" || t.key_check === "failed"), reviewed: true };
}

/** The classes the editor adds on top of the cards' drawing: kg-key-<check> and kg-rv-<review> on a table,
 * kg-rv-<review> on a link (the cards already mark a link's check state and a rejection). */
export function stateClasses(map: MapData): { tables: Record<string, string[]>; links: Record<string, string[]> } {
  const tables: Record<string, string[]> = {};
  for (const t of map.tables) {
    const cls: string[] = [];
    if (t.key_check && t.key.length) cls.push(`kg-key-${t.key_check}`);
    if (t.review) cls.push(`kg-rv-${t.review}`);
    tables[t.name] = cls;
  }
  const links: Record<string, string[]> = {};
  for (const r of map.relationships) links[r.id] = [`kg-st-${r.state ?? "not_checked"}`, `kg-rv-${r.review ?? "proposed"}`];
  return { tables, links };
}

/** Draws the map into `box` with the cards' drawMap and marks the editor's states; returns the picture's description
 * (one sentence a screen reader hears), or "" when there is nothing to draw. */
export function drawPlanMap(box: HTMLElement, map: MapData | undefined): string {
  if (!map) {
    box.textContent = "";
    return "";
  }
  const desc: string = drawMap(box, map) || "";
  const cls = stateClasses(map);
  const esc = (s: string) => s.replace(/["\\]/g, "\\$&");
  for (const [name, c] of Object.entries(cls.tables)) {
    box.querySelectorAll(`[data-table="${esc(name)}"]`).forEach((n) => c.forEach((x) => n.classList.add(x)));
  }
  for (const [id, c] of Object.entries(cls.links)) {
    box.querySelectorAll(`[data-id="${esc(id)}"]`).forEach((n) => c.forEach((x) => n.classList.add(x)));
  }
  return desc;
}
