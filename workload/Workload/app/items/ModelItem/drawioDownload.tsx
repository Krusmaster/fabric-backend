/**
 * Krusgraph (n228): "Download as draw.io" under the map and under the data flow. The founder, 12 November 2026: "can I
 * see this as a draw.io file/flow if I want?"
 *
 * The engine makes the file (fabric_backend/drawio.py, POST /workload/v1/drawio) from what the editor is already
 * showing: the review's map with the person's latest decisions, or the build's flow without each box's code. Nothing is
 * read from Fabric for it and nothing is written. The editor (ModelItemEditor.tsx) provides the call through
 * DrawioContext; where nothing provides it (a test of the map alone, an older host) the button is not shown.
 *
 * The file is offered as a link with the `download` attribute, the way the App card offers its package: a click on
 * the button fetches the file and then clicks that link once, and the link stays for a browser that wants the click
 * to be the person's own.
 */
import React, { createContext, useContext, useEffect, useRef, useState } from "react";
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
  const [state, setState] = useState<{ busy?: boolean; file?: DrawioFile; error?: string }>({});
  const link = useRef<HTMLAnchorElement>(null);
  const clicked = useRef<string>();
  useEffect(() => {
    // one click of the link for each file fetched; the link stays for a browser that ignores it
    if (state.file?.content && link.current && clicked.current !== state.file.content) {
      clicked.current = state.file.content;
      try {
        link.current.click();
      } catch {
        /* the link is there to click */
      }
    }
  }, [state.file]);
  if (!source) return null;
  const fetchFile = async () => {
    setState({ busy: true });
    try {
      const file = await source.get({ ...props.request(), name: source.name });
      setState(file.content ? { file } : { error: file.too_large ?? "The engine answered without a file." });
    } catch {
      setState({ error: `The ${props.what} could not be made into a draw.io file just now. Nothing changed; try again.` });
    }
  };
  return (
    <p className="krusgraph-drawio">
      <button type="button" className="kg-toggle" disabled={state.busy} onClick={() => void fetchFile()}>
        {state.busy ? "Making the file…" : "Download as draw.io"}
      </button>{" "}
      {state.file?.content && (
        <a ref={link} href={fileHref(state.file)} download={state.file.filename}>
          Save {state.file.filename}
        </a>
      )}
      {state.error && <span role="status">{state.error}</span>}
    </p>
  );
}
