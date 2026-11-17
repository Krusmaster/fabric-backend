/**
 * W13: "Next with other Fabric workloads" (nextSteps.ts), under the result of a Create and on the Data product page.
 * One card per suggestion: the workload, the title, one line of why, what Krusgraph does for it (a status word, never
 * colour alone) and one button. Cards wrap to one column on a phone (ModelItem.scss, .kg-next).
 */
import React, { useState } from "react";
import { Badge, Body1, Button, Caption1, Subtitle2 } from "@fluentui/react-components";
import { ArrowDownload20Regular, Copy20Regular, Open20Regular, Play20Regular } from "@fluentui/react-icons";
import { NextInput, NextStep, grainLine, nextSteps, proofLine, proofOf } from "./nextSteps";
import type { OutputKind } from "./engineClient";

const STATUS_COLOR: Record<NextStep["status"], "brand" | "informative" | "success" | "subtle"> = {
  builds: "brand", starter: "success", "in Claude": "informative", "guide only": "subtle",
};
const STATUS_WORD: Record<NextStep["status"], string> = {
  builds: "Krusgraph builds it", starter: "Starter to download", "in Claude": "Krusgraph in Claude", "guide only": "Guide only",
};

function href(content: string, mime: string): string {
  return `data:${mime};charset=utf-8,${encodeURIComponent(content)}`;
}

function StepCard(props: { step: NextStep; onBuild: (outputs: OutputKind[]) => void }) {
  const { step } = props;
  const [copied, setCopied] = useState(false);
  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);   // the frame may not allow the clipboard: the text is shown below to copy by hand
    }
  };
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
            <Button as="a" appearance="secondary" icon={<ArrowDownload20Regular />} href={href(how.content, how.mime)} download={how.filename}
              aria-label={`${how.label}: ${how.filename}`}>
              {how.label}
            </Button>
            <Button appearance="subtle" icon={<Copy20Regular />} onClick={(): void => void copy(how.code)}>
              {copied ? "Copied" : "Copy the code"}
            </Button>
          </>
        )}
        {how.kind === "ask" && (
          <Button appearance="secondary" icon={<Copy20Regular />} onClick={(): void => void copy(how.text)}>
            {copied ? "Copied" : how.label}
          </Button>
        )}
        {how.kind === "guide" && (
          <Button as="a" appearance="subtle" icon={<Open20Regular />} href={how.url} target="_blank" rel="noopener noreferrer">
            {how.label}
          </Button>
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
