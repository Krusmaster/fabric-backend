/**
 * W13: "Next with other Fabric workloads" (nextSteps.ts), under the result of a Create and on the Data product page.
 * One card per suggestion: the workload, the title, one line of why, what Krusgraph does for it (a status word, never
 * colour alone) and one button. Cards wrap to one column on a phone (ModelItem.scss, .kg-next).
 */
import React, { createContext, useContext, useState } from "react";
import { Badge, Body1, Button, Caption1, Subtitle2 } from "@fluentui/react-components";
import { Open20Regular, Play20Regular } from "@fluentui/react-icons";
import { CopyText, FileActions, OutLink } from "./fileOffer";
import { NextInput, NextStep, grainLine, nextSteps, proofLine, proofOf } from "./nextSteps";
import type { OutputKind } from "./engineClient";
import type { CreatedItem } from "./ModelItemDefinition";

/** WB10 (#64): the Data Science starter's Dry run, then Create (POST /workload/v1/starter): the notebook in the item's
 * workspace, attached to the source lakehouse. Never run by Krusgraph. */
export interface StarterAnswer {
  would: "create" | "exists" | "created";
  name: string;
  words: string;
  confirm: string | null;
  created?: CreatedItem;
}
export interface StarterSource {
  run: (opts: { name: string; cells: string[]; dryRun: boolean; confirm?: string | null }) => Promise<StarterAnswer>;
  onCreated?: (item: CreatedItem) => void;
}
export const StarterContext = createContext<StarterSource | undefined>(undefined);

function StarterCreate(props: { name: string; cells: string[] }) {
  const source = useContext(StarterContext);
  const [state, setState] = useState<{ busy?: boolean; answer?: StarterAnswer; problem?: string }>({});
  if (!source) return null;
  const go = async (dryRun: boolean) => {
    setState((s) => ({ ...s, busy: true, problem: undefined }));
    try {
      const answer = await source.run({ name: props.name, cells: props.cells, dryRun, confirm: dryRun ? null : state.answer?.confirm });
      if (answer.created) source.onCreated?.(answer.created);
      setState({ answer });
    } catch (e) {
      const err = e as { answer?: { error?: string; hint?: string }; message?: string };
      setState((s) => ({ ...s, busy: false, problem: [err.answer?.error ?? err.message ?? "The engine could not answer.", err.answer?.hint].filter(Boolean).join(" ") }));
    }
  };
  const a = state.answer;
  return (
    <>
      {a?.would !== "created" && (
        <Button appearance="secondary" icon={<Play20Regular />} onClick={(): void => void go(true)} disabled={state.busy}
          aria-label={`Dry run: create the notebook ${props.name}`}>
          Dry run
        </Button>
      )}
      {a?.would === "create" && a.confirm && (
        <Button appearance="primary" onClick={(): void => void go(false)} disabled={state.busy}>Create {a.name}</Button>
      )}
      {(a || state.problem) && (
        <Caption1 role="status" className="kg-next-starter-said">{state.problem ?? a?.words}</Caption1>
      )}
    </>
  );
}

const STATUS_COLOR: Record<NextStep["status"], "brand" | "informative" | "success" | "subtle"> = {
  builds: "brand", starter: "success", "in Claude": "informative", "guide only": "subtle",
};
const STATUS_WORD: Record<NextStep["status"], string> = {
  builds: "Krusgraph builds it", starter: "Starter to download", "in Claude": "Krusgraph in Claude", "guide only": "Guide only",
};

function StepCard(props: { step: NextStep; onBuild: (outputs: OutputKind[]) => void }) {
  const { step } = props;
  const how = step.how;
  return (
    <li className="kg-next-card" data-step={step.id}>
      <div className="kg-next-head">
        <Caption1 className="kg-next-workload">{step.workload}</Caption1>
        <Badge appearance="tint" color={STATUS_COLOR[step.status]}>{STATUS_WORD[step.status]}</Badge>
      </div>
      <Subtitle2 as="h3">{step.title}</Subtitle2>
      <Body1>{step.why}</Body1>
      {step.note && <Caption1>{step.note}</Caption1>}
      <div className="kg-next-actions">
        {how.kind === "build" && (
          <Button appearance="secondary" icon={<Play20Regular />} onClick={() => props.onBuild(how.outputs)}
            aria-label={`${how.label}: ${step.title}`}>
            {how.label}
          </Button>
        )}
        {how.kind === "starter" && (
          <>
            <StarterCreate name={how.name} cells={how.cells} />
            <FileActions file={{ filename: how.filename, mime: how.mime, text: how.content }} label={how.label} copy={false}
              ariaLabel={`${how.label}: ${how.filename}`} />
            <CopyText text={how.code} label="Copy the code" />
          </>
        )}
        {how.kind === "ask" && (
          <CopyText text={how.text} label={how.label} appearance="secondary" />
        )}
        {how.kind === "guide" && (
          <OutLink url={how.url} className="kg-next-guide"><Open20Regular aria-hidden /> {how.label}</OutLink>
        )}
      </div>
      {how.kind === "starter" && (
        <details className="kg-next-code">
          <summary><Caption1>Show the code</Caption1></summary>
          <pre>{how.code}</pre>
        </details>
      )}
      {how.kind === "ask" && <Caption1 className="kg-next-ask">{how.text}</Caption1>}
    </li>
  );
}

/** W13: what the check proved, as tiles a person can read at a glance: rows counted, keys unique, links holding,
 * orphans, duplicate keys; and the doubled total the proven grain prevents (Onto's sentence). */
export function ProofStrip(props: { review: NextInput["review"] }) {
  const p = proofOf(props.review);
  if (!p.keysChecked && !p.linksChecked) return null;
  const tiles: [string, string][] = [
    [p.rows.toLocaleString("en-US"), "rows counted"],
    [`${p.keysPassed} of ${p.keysChecked}`, "keys unique"],
    [`${p.linksPassed} of ${p.linksChecked}`, "links holding"],
    [p.orphans.toLocaleString("en-US"), p.orphans === 1 ? "orphan" : "orphans"],
    [p.duplicates.toLocaleString("en-US"), p.duplicates === 1 ? "duplicate key" : "duplicate keys"],
  ];
  const grain = grainLine(p.grains[0]);
  return (
    <section aria-label="What the check proved">
      <ul className="kg-proof">
        {tiles.map(([n, what]) => (
          <li key={what}><strong>{n}</strong><Caption1>{what}</Caption1></li>
        ))}
      </ul>
      {grain && <Body1 data-say="onto"><strong>Onto:</strong> {grain}</Body1>}
    </section>
  );
}

export function NextStepsPanel(props: NextInput & { onBuild: (outputs: OutputKind[]) => void }) {
  const { proof, steps, waiting } = nextSteps(props);
  const proven = proofLine(proof);
  const grain = grainLine(proof.grains[0]);
  return (
    <section className="kg-next" aria-labelledby="kg-next-title">
      <Subtitle2 as="h2" id="kg-next-title">Next, with other Fabric workloads</Subtitle2>
      {waiting ? (
        <Body1>{waiting}</Body1>
      ) : (
        <>
          <Body1 data-say="thinker"><strong>Thinker:</strong> {proven}</Body1>
          {grain && <Body1 data-say="onto"><strong>Onto:</strong> {grain}</Body1>}
          <Caption1>Suggestions by rules from what was proven; no AI. A dry run comes before anything is created.</Caption1>
          <ul className="kg-next-list">
            {steps.map((s) => <StepCard key={s.id} step={s} onBuild={props.onBuild} />)}
          </ul>
        </>
      )}
    </section>
  );
}
