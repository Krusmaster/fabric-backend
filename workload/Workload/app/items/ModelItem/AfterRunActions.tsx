/**
 * W2: the two buttons a created card may need after the pipeline's run (afterRun.ts): "Select tables now" on the data
 * agent, at most MAX_SELECT_TRIES times, and "Refresh now" on the semantic model when its refresh failed or did not run.
 * Each sends one engine step; neither loops.
 */
import React from "react";
import { Button, Caption1 } from "@fluentui/react-components";
import { ArrowClockwise20Regular, TableSimple20Regular } from "@fluentui/react-icons";
import type { BuildCard, PipelineRun } from "./engineClient";
import { refreshOffer, selectTablesOffer } from "./afterRun";

export interface AfterRunProps {
  card: BuildCard;
  run?: PipelineRun;
  selectTries?: number;
  onSelectTables?: (card: BuildCard) => void;
  onRefreshModel?: (card: BuildCard) => void;
  busy?: boolean;
}

export function AfterRunActions(props: AfterRunProps) {
  const c = props.card;
  if (c.output === "data_agent" && props.onSelectTables) {
    const o = selectTablesOffer(c, props.selectTries ?? 0, props.run);
    if (!o.offer && !o.line) return null;
    return (
      <div className="kg-after-run" data-w2="select-tables">
        {o.offer && (
          <Button appearance="secondary" icon={<TableSimple20Regular />} disabled={props.busy} onClick={() => props.onSelectTables?.(c)}>
            {o.label}
          </Button>
        )}
        {o.line && <Caption1>{o.line}</Caption1>}
      </div>
    );
  }
  if (c.output === "semantic_model" && props.onRefreshModel) {
    const o = refreshOffer(c, props.run);
    if (!o.offer) return null;
    return (
      <div className="kg-after-run" data-w2="refresh-model">
        <Button appearance="secondary" icon={<ArrowClockwise20Regular />} disabled={props.busy} onClick={() => props.onRefreshModel?.(c)}>
          {o.label}
        </Button>
      </div>
    );
  }
  return null;
}
