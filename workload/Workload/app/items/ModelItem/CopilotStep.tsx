/**
 * W3: the data agent card's guidance (copilotWords.ts) and its "Make it available in Copilot" step. Thinker says what
 * to do when the agent has no tables; once it has its tables and valid example queries, Onto cheers once (cheer.ts) and
 * Builder recommends publishing, then Microsoft 365 Copilot. The step is a dry run first (what Microsoft requires, what
 * would be done); Krusgraph publishes in Fabric only after the person ticks and chooses Publish as me. The editor
 * provides AgentPublishContext; where nothing provides it, the step is not offered (the guidance still is).
 */
import React, { createContext, useContext, useState } from "react";
import { Body1, Button, Caption1, Checkbox, Link, Subtitle2 } from "@fluentui/react-components";
import { BotSparkle20Regular } from "@fluentui/react-icons";
import type { BuildCard, PipelineRun } from "./engineClient";
import { MASCOT_CSS } from "./cardMap.generated";
import { selectTablesOffer } from "./afterRun";
import { agentCheer } from "./cheer";
import { CheerContext, CheerLine } from "./cheerView";
import {
  COPILOT_BUTTON, CopilotAnswer, PUBLISH_BUTTON, agentNoTablesLine, planLines, publishAdvice, publishBody, publishedLines,
  publishGate, requirementLine,
} from "./copilotWords";
import { MascotSays } from "./mascotFigure";

export interface AgentPublishSource {
  /** POST /workload/v1/agent-publish; rejects with the engine's error */
  run: (body: object) => Promise<CopilotAnswer>;
  /** the source's name, for the published description */
  source?: string;
}

export const AgentPublishContext = createContext<AgentPublishSource | undefined>(undefined);

/** A mascot's line, or the plain sentence with the mascots off. */
function Say(props: { kind: "thinker" | "builder"; text?: string; pose: string; attr: string }) {
  const cheer = useContext(CheerContext);
  if (!props.text) return null;
  if (cheer && !cheer.on) return <Body1 as="p" block data-w3={props.attr}>{props.text}</Body1>;
  return (
    <ul className="krusgraph-mascots" data-w3={props.attr}>
      <style>{MASCOT_CSS}</style>
      <MascotSays kind={props.kind} text={props.text} pose={props.pose} />
    </ul>
  );
}

export function CopilotStepView(props: {
  answer?: CopilotAnswer; busy: boolean; problem?: string; ticked: boolean;
  onPrepare: () => void; onTicked: (v: boolean) => void; onPublish: () => void;
}) {
  const a = props.answer;
  const gate = publishGate(a, props.ticked);
  return (
    <section className="kg-copilot" aria-label="Make it available in Microsoft 365 Copilot" data-w3="copilot-step">
      <div className="kg-catalog-actions">
        <Button appearance="primary" icon={<BotSparkle20Regular />} onClick={props.onPrepare} disabled={props.busy}>
          {a && !a.published ? "Check again" : COPILOT_BUTTON}
        </Button>
      </div>
      {props.problem && <Body1 role="alert">{props.problem}</Body1>}
      {a && (
        <>
          <Subtitle2 as="h4">What Microsoft requires</Subtitle2>
          {/* the engine's summary only when nothing is missing: the missing ones are the lines below, said once */}
          {a.missing === 0 && <Body1 as="p" block>{a.preflight_words}</Body1>}
          <ul className="krusgraph-list" aria-label="Microsoft 365 Copilot requirements">
            {a.requirements.map((r) => (
              <li key={r.requirement} data-status={r.status}>
                {requirementLine(r)} <Link href={r.doc} target="_blank">Microsoft's page</Link>
              </li>
            ))}
          </ul>
          <Subtitle2 as="h4">What would be done</Subtitle2>
          <ol className="krusgraph-steps" aria-label="What would be done">
            {planLines(a).map((l) => <li key={l}>{l.replace(/^\d+\. /, "")}</li>)}
          </ol>
          {a.published ? (
            <div role="status" data-w3="published">
              {publishedLines(a).map((l) => <Body1 as="p" block key={l}>{l}</Body1>)}
            </div>
          ) : (
            <div className="kg-catalog-write">
              <Checkbox checked={props.ticked} onChange={(_, d) => props.onTicked(!!d.checked)} disabled={!a.confirm || props.busy}
                label={`Publish ${a.name} in Fabric as me`} />
              <Button appearance="primary" onClick={props.onPublish} disabled={!gate.ok || props.busy}
                aria-describedby={!gate.ok ? "kg-copilot-why" : undefined}>
                {PUBLISH_BUTTON}
              </Button>
              {!gate.ok && <Caption1 id="kg-copilot-why">{gate.why}</Caption1>}
            </div>
          )}
        </>
      )}
    </section>
  );
}

/** The step with its own state: a dry run on the first click, the publish only with its confirm. */
export function CopilotStep(props: { card: BuildCard }) {
  const src = useContext(AgentPublishContext);
  const [answer, setAnswer] = useState<CopilotAnswer>();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string>();
  const [ticked, setTicked] = useState(false);
  if (!src || !publishBody(props.card, src.source, true)) return null;
  const go = async (dryRun: boolean) => {
    const body = publishBody(props.card, src.source, dryRun, answer?.confirm);
    if (!body) return;
    setBusy(true);
    setProblem(undefined);
    try {
      setAnswer(await src.run(body));
      setTicked(false);
    } catch (e) {
      const err = e as { answer?: { error?: string; hint?: string }; message?: string };
      setProblem([err.answer?.error ?? err.message ?? "The engine could not answer.", err.answer?.hint].filter(Boolean).join(" "));
    } finally {
      setBusy(false);
    }
  };
  return <CopilotStepView answer={answer} busy={busy} problem={problem} ticked={ticked} onPrepare={() => void go(true)}
    onTicked={setTicked} onPublish={() => void go(false)} />;
}

/** Under the data agent card: Thinker's line without tables; Onto's cheer, Builder's advice and the step once ready. */
export function AgentGuide(props: { card: BuildCard; selectTries?: number; run?: PipelineRun }) {
  const c = props.card;
  if (c.output !== "data_agent" || c.dry_run) return null;
  const empty = agentNoTablesLine(c, selectTablesOffer(c, props.selectTries ?? 0, props.run), props.run);
  const advice = publishAdvice(c);
  if (!empty && !advice) return null;
  return (
    <div className="kg-stack" data-w3="agent-guide">
      <Say kind="thinker" text={empty} pose="think" attr="agent-no-tables" />
      {advice && (
        <>
          <CheerLine milestone="agent_ready" place={`agent:${c.created?.[0]?.id ?? ""}`} text={agentCheer(c)} />
          <Say kind="builder" text={advice} pose="point" attr="agent-publish-advice" />
          <CopilotStep card={c} />
        </>
      )}
    </div>
  );
}
