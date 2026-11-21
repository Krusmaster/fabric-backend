/**
 * ED3: "Open in Fabric" and "Run now" side by side for an item Krusgraph created (openInFabric.tsx, runNow.ts).
 * Run now is shown only for notebooks and pipelines, starts nothing on its own, and shows the run's state as a word
 * (never colour alone), Fabric's message once when it failed, and, when it succeeded and the run wrote a table, that
 * table's row count and first 10 rows, read once and kept only on this page.
 */
import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { Badge, Button, Caption1 } from "@fluentui/react-components";
import { Play20Regular } from "@fluentui/react-icons";
import { FabricItemRef, OpenInFabric } from "./openInFabric";
import { IDLE, RUN_ONLY_WHEN, RunAnswer, RunView, nextView, pollDelay, previewCells, runStatus, runnable } from "./runNow";

export interface RunRequest {
  workspace: string;
  item_id: string;
  item_type: string;
  name: string;
  run_id?: string;
  preview?: { lakehouse: string; table: string; schema?: string };
}
export interface RunSource {
  run: (body: RunRequest) => Promise<RunAnswer>;
}
export const RunContext = createContext<RunSource | undefined>(undefined);

const BADGE: Record<string, "informative" | "success" | "danger" | "warning" | "subtle"> = {
  starting: "informative", queued: "informative", running: "informative", succeeded: "success", failed: "danger",
  unknown: "warning", refused: "warning",
};

export function RunNow(props: { item: FabricItemRef; preview?: RunRequest["preview"] }) {
  const source = useContext(RunContext);
  const [view, setView] = useState<RunView>(IDLE);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; if (timer.current) clearTimeout(timer.current); }, []);
  if (!source || !runnable(props.item.type)) return null;
  const body = (runId?: string): RunRequest => ({
    workspace: props.item.workspaceId, item_id: props.item.id, item_type: props.item.type, name: props.item.displayName ?? props.item.id,
    ...(runId ? { run_id: runId } : {}), ...(props.preview ? { preview: props.preview } : {}),
  });
  const step = async (prev: RunView, runId?: string) => {
    let next: RunView;
    try {
      next = nextView(prev, await source.run(body(runId)));
    } catch (e) {
      const err = e as { answer?: { error?: string; kind?: string; hint?: string }; message?: string };
      next = nextView(prev, { error: err.answer?.error ?? err.message ?? "The engine could not answer.", kind: err.answer?.kind, hint: err.answer?.hint });
    }
    if (!alive.current) return;
    setView(next);
    const wait = pollDelay(next);
    if (wait !== undefined) timer.current = setTimeout(() => void step(next, next.runId), wait);
  };
  const start = () => {
    const v: RunView = { state: "starting", polls: 0 };
    setView(v);
    void step(v);
  };
  const busy = ["starting", "queued", "running"].includes(view.state);
  const st = runStatus(view);
  const cells = view.preview && !view.preview.missing ? previewCells(view.preview) : undefined;
  return (
    <>
      <Button appearance="secondary" icon={<Play20Regular />} onClick={start} disabled={busy}
        aria-label={`Run now: ${props.item.displayName ?? "the item"}`}>
        {view.state === "succeeded" || view.state === "failed" ? "Run again" : "Run now"}
      </Button>
      <div className="kg-run" role="status" aria-live="polite">
        {st.word && <Badge appearance="tint" color={BADGE[view.state] ?? "subtle"}>{st.word}</Badge>}
        {st.line && <Caption1 className="kg-run-line">{st.line}</Caption1>}
        {cells && cells.columns.length > 0 && (
          <div className="kg-run-preview">
            <table aria-label={`First rows of ${view.preview!.table}`}>
              <thead><tr>{cells.columns.map((c) => <th key={c} scope="col">{c}</th>)}</tr></thead>
              <tbody>{cells.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody>
            </table>
            {view.preview?.personal_data?.notice && <Caption1>{view.preview.personal_data.notice}</Caption1>}
          </div>
        )}
      </div>
    </>
  );
}

/** Open in Fabric (primary) and, for a notebook or pipeline, Run now, with the one line that says when it runs. */
export function CreatedActions(props: { item: FabricItemRef; preview?: RunRequest["preview"]; children?: React.ReactNode }) {
  const run = runnable(props.item.type);
  return (
    <>
      <div className="kg-next-actions kg-created-actions">
        <OpenInFabric item={props.item} />
        <RunNow item={props.item} preview={props.preview} />
        {props.children}
      </div>
      {run && <Caption1 className="kg-run-when">{RUN_ONLY_WHEN}</Caption1>}
    </>
  );
}
