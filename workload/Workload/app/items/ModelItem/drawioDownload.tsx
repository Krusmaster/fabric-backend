/**
 * Krusgraph (n228): "Download as draw.io" under the map and under the data flow. The founder, 12 November 2026: "can I
 * see this as a draw.io file/flow if I want?"
 *
 * The engine makes the file (fabric_backend/drawio.py, POST /workload/v1/drawio) from what the editor is already
 * showing: the review's map with the person's latest decisions, or the build's flow without each box's code. Nothing is
 * read from Fabric for it and nothing is written. The editor (ModelItemEditor.tsx) provides the call through
 * DrawioContext; where nothing provides it (a test of the map alone, an older host) the button is not shown.
 *
 * WB10: the `data:` link with `download` did nothing inside Fabric's sandboxed frame (Gustav's live test, 18 Nov 2026);
 * the file now goes through fileOffer.tsx.
 */
import React, { createContext, useContext } from "react";
import { FileActions, OfferedFile } from "./fileOffer";
import type { MapData } from "./cardMap";
import type { DataFlow } from "./engineClient";

export interface DrawioFile {
  filename: string;
  mime_type: string;
  content?: string;
  too_large?: string;
}

export type DrawioRequest =
  | { diagram: "map"; map: MapData; name?: string }
  | { diagram: "data_flow"; flow: Record<string, unknown>; name?: string };

export interface DrawioSource {
  get: (body: DrawioRequest) => Promise<DrawioFile>;
  /** What the file is named after: the source and its schema. */
  name?: string;
}

export const DrawioContext = createContext<DrawioSource | undefined>(undefined);

/** The flow as the file needs it: every box and arrow, without the code a click unfolds. */
export function flowForFile(flow: DataFlow): Record<string, unknown> {
  return {
    columns: flow.columns,
    nodes: flow.nodes.map((n) => ({ id: n.id, column: n.column, under: n.under, label: n.label, kind_label: n.kind_label, lines: n.lines, built: n.built })),
    edges: flow.edges.map((e) => ({ from: e.from, to: e.to, label: e.label, rule: e.rule, built: e.built })),
    notes: flow.notes,
    said: flow.said,
  };
}

/** A data: URL of the file's text, for a link with `download`. */
export function fileHref(file: DrawioFile): string {
  return `data:${file.mime_type};charset=utf-8,${encodeURIComponent(file.content ?? "")}`;
}

export function DrawioButton(props: { request: () => DrawioRequest; what: string }) {
  const source = useContext(DrawioContext);
  if (!source) return null;
  // WB10 (#57): the file is made on the click, then offered through the engine's single-use link (fileOffer.tsx), which
  // works inside Fabric's sandboxed frame; Copy and the text area are offered if the download cannot be opened
  const make = async (): Promise<OfferedFile> => {
    let file: DrawioFile;
    try {
      file = await source.get({ ...props.request(), name: source.name });
    } catch {
      throw new Error(`The ${props.what} could not be made into a draw.io file just now. Nothing changed; try again.`);
    }
    if (!file.content) throw new Error(file.too_large ?? "The engine answered without a file.");
    return { filename: file.filename, mime: file.mime_type, text: file.content };
  };
  return (
    <p className="krusgraph-drawio">
      <FileActions file={make} label="Download as draw.io" appearance="subtle" />
    </p>
  );
}
