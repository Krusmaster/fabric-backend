/**
 * n174: the data flow's picture, laid out left to right: bronze (the source tables) -> silver -> gold -> what is built on
 * the source, and the pipeline's steps in a row under the columns they run. The founder, 8 November 2026: "when you
 * create a data flow you want to see it visually: bronze to gold, which silvers are joined"; "click the boxes and you
 * see the code unfolded, otherwise not".
 *
 * The data is the engine's (fabric_backend/data_flow.py, in the build's answer as `flow`): every node, edge and line of
 * code comes from the dry run. This module only places it. Pure, so it runs in unit tests (dataFlow.test.ts); FlowView
 * draws it with the map's classes and colours (the same visual language as the plan map).
 */
import { DataFlow, FlowEdge, FlowNode } from "./engineClient";

export const BOX_W = 196;
export const GAP_X = 74;
export const GAP_Y = 14;
export const TOP = 40;
const LINE_H = 15;
const MAX_CHARS = 31;
const MAX_LABEL = 24;

export interface Box {
  node: FlowNode;
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  lines: string[];
}

export interface Path {
  edge: FlowEdge;
  d: string;
  dashed: boolean;
}

export interface FlowLayout {
  width: number;
  height: number;
  columns: { id: string; title: string; x: number }[];
  boxes: Box[];
  paths: Path[];
  pipelineTitle?: { x: number; y: number; text: string };
}

export function clip(s: string, n = MAX_CHARS): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

export function boxHeight(n: FlowNode): number {
  return 26 + LINE_H * Math.min(n.lines.filter(Boolean).length, 6) + (n.pills.length ? 18 : 0);
}

/** Where every node, edge and column title goes. Columns without a node are left out (no gold without schemas). */
export function layoutFlow(flow: DataFlow): FlowLayout {
  const present = flow.columns.filter((c) => flow.nodes.some((n) => n.column === c.id));
  const columns = present.map((c, i) => ({ id: c.id, title: c.title, x: i * (BOX_W + GAP_X) }));
  const xOf = (col: string) => columns.find((c) => c.id === col)?.x ?? 0;
  const boxes: Box[] = [];
  let bottom = TOP;
  for (const c of columns) {
    let y = TOP;
    for (const n of flow.nodes.filter((m) => m.column === c.id)) {
      const lines = n.lines.filter(Boolean).slice(0, 6).map((l) => clip(l));
      const b = { node: n, x: c.x, y, w: BOX_W, h: boxHeight(n), label: clip(n.label, MAX_LABEL), lines };
      boxes.push(b);
      y += b.h + GAP_Y;
    }
    bottom = Math.max(bottom, y);
  }
  let pipelineTitle: FlowLayout["pipelineTitle"];
  const steps = flow.nodes.filter((n) => n.column === "pipeline");
  if (steps.length) {
    const y = bottom + 30;
    pipelineTitle = { x: 0, y: y - 10, text: `Pipeline ${flow.pipeline?.name ?? ""}`.trim() };
    steps.forEach((n, i) => {
      const x = n.under && columns.some((c) => c.id === n.under) ? xOf(n.under) : i * (BOX_W + GAP_X);
      boxes.push({ node: n, x, y, w: BOX_W, h: boxHeight(n), label: clip(n.label, MAX_LABEL), lines: n.lines.slice(0, 6).map((l) => clip(l)) });
    });
    bottom = y + Math.max(...steps.map(boxHeight)) + GAP_Y;
  }
  const byId = new Map(boxes.map((b) => [b.node.id, b]));
  const paths: Path[] = [];
  const bronze = columns.find((c) => c.id === "bronze");
  for (const e of flow.edges) {
    const to = byId.get(e.to);
    if (!to) continue;
    const ty = to.y + to.h / 2;
    if (e.from === "bronze" && bronze) {
      // the items built on the source read the bronze tables: one line along the top, from the bronze column
      const sx = bronze.x + BOX_W / 2;
      const bend = to.x - 26;
      paths.push({ edge: e, dashed: !e.built, d: `M${sx},${TOP - 6} V${TOP - 14} H${bend} C${bend + 16},${TOP - 14} ${bend},${ty} ${to.x},${ty}` });
      continue;
    }
    const from = byId.get(e.from);
    if (!from) continue;
    const sy = from.y + from.h / 2;
    if (from.node.column === "pipeline" || to.node.column === "pipeline" || from.x === to.x) {
      const sx = from.x + from.w;
      paths.push({ edge: e, dashed: !e.built, d: `M${sx},${sy} H${to.x}` });
      continue;
    }
    const sx = from.x + from.w;
    const mid = (sx + to.x) / 2;
    paths.push({ edge: e, dashed: !e.built, d: `M${sx},${sy} C${mid},${sy} ${mid},${ty} ${to.x},${ty}` });
  }
  const width = Math.max(BOX_W, ...boxes.map((b) => b.x + b.w)) + 4;
  return { width, height: bottom + 4, columns, boxes, paths, pipelineTitle };
}

/** One box open at a time: clicking the open one closes it, another opens that one. */
export function toggleOpen(open: string | undefined, id: string): string | undefined {
  return open === id ? undefined : id;
}

/** Enter and Space toggle a box, as a button does. */
export function togglesOn(key: string): boolean {
  return key === "Enter" || key === " " || key === "Spacebar";
}

/** What a screen reader hears for a box: its label, its lines, whether this build makes it, whether it has code. */
export function boxLabel(n: FlowNode, open: boolean): string {
  const what = n.column === "pipeline" ? "Pipeline step" : n.kind_label ?? n.column.charAt(0).toUpperCase() + n.column.slice(1);
  const built = n.column === "bronze" ? "the source" : n.built ? "part of this build" : "not part of this build";
  const code = n.code ? (open ? "; code shown below" : "; press Enter to show its code") : "";
  return `${what} ${n.label}: ${n.lines.filter(Boolean).join("; ")}${n.lines.length ? "; " : ""}${built}${code}`;
}
