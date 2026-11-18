/**
 * CA1: "Publish to OneLake catalog", a step on the Data product page. Gustav, 16 November 2026: "Kan vi ha det
 * alternativet i workloaden att vi spinner upp OneLake catalog via Krusgraph?" The OneLake catalog is in every Fabric
 * tenant; Krusgraph fills and organises it for the data products it has checked.
 *
 * Prepare is a dry run: the engine (POST /workload/v1/catalog) answers a card per data product, the diff of exactly what
 * would be written as the signed-in user (descriptions, existing tags), and the handover files for what needs someone
 * else (a Fabric admin, a workspace admin, a Purview steward, a reviewer). Write sends the dry run's confirm back, so what
 * is written is what was shown, and is offered only where the engine says writing is on. Endorsement is never set.
 *
 * Phone first: one column, each change as its own block (item, field, now, after), no table to scroll sideways.
 * The editor provides the call through CatalogContext; where nothing provides it the panel is not shown.
 */
import React, { createContext, useContext, useState } from "react";
import { Badge, Body1, Button, Caption1, Checkbox, Field, Input, Subtitle2 } from "@fluentui/react-components";
import { BookDatabase20Regular, Edit20Regular } from "@fluentui/react-icons";
import { FileActions } from "./fileOffer";
import {
  CatalogAnswer, CatalogCard, CatalogDiffRow, ENDORSE_LINE, STEP_INTRO, STEP_TITLE, approvals, canWrite, diffLine, fileMime,
  fileName, ruleCounts, shown, writeCount,
} from "./catalogWords";

export interface CatalogSource {
  /** dry_run true: what would be written; false with the confirm: write it. Rejects with the engine's error. */
  run: (opts: { dryRun: boolean; confirm?: string | null; owner?: string | null }) => Promise<CatalogAnswer>;
  /** the data product's owner as the Data product page saved it, if any */
  owner?: string | null;
}

export const CatalogContext = createContext<CatalogSource | undefined>(undefined);

function Card(props: { card: CatalogCard }) {
  const c = props.card;
  return (
    <li className="kg-catalog-card" data-product={c.slug}>
      <Subtitle2 as="h4">{c.name}</Subtitle2>
      <Body1>{c.description}</Body1>
      <Caption1>Owner: {c.owner} · Proposed domain: {c.domain.proposed} · Tags: {c.tags.join(", ")}</Caption1>
      <Caption1>{c.evidence.line} · {ruleCounts(c)}</Caption1>
      <details>
        <summary>Glossary terms ({c.glossary.length}) and quality rules ({c.quality_rules.length})</summary>
        <ul className="kg-catalog-plain">
          {c.glossary.map((t) => <li key={t.term}><strong>{t.term}</strong>: {t.definition}</li>)}
        </ul>
        <ul className="kg-catalog-plain">
          {c.quality_rules.map((r) => <li key={r.id}>{r.says}: <em>{r.status}</em></li>)}
        </ul>
      </details>
    </li>
  );
}

function Change(props: { row: CatalogDiffRow }) {
  const r = props.row;
  return (
    <li className="kg-catalog-change" data-action={r.action} aria-label={diffLine(r)}>
      <div className="kg-catalog-change-head">
        <strong>{r.item}</strong>
        <Badge appearance="tint" color={r.action === "write" ? "brand" : "subtle"}>
          {r.action === "write" ? `Writes ${r.field}` : `Keeps ${r.field}`}
        </Badge>
      </div>
      {r.action === "write" ? (
        <dl className="kg-catalog-before-after">
          <dt>Now</dt><dd>{shown(r.before)}</dd>
          <dt>After</dt><dd>{shown(r.after)}</dd>
        </dl>
      ) : (
        <Caption1>{r.why}.{r.after ? <> Suggested: {shown(r.after)}</> : null}</Caption1>
      )}
    </li>
  );
}

export function CatalogView(props: {
  answer?: CatalogAnswer; busy: boolean; problem?: string; owner: string; checked: boolean; written?: boolean;
  onOwner: (v: string) => void; onPrepare: () => void; onChecked: (v: boolean) => void; onWrite: () => void;
}) {
  const a = props.answer;
  const gate = canWrite(a, props.checked);
  return (
    <section className="kg-catalog" aria-labelledby="kg-catalog-title">
      <Subtitle2 as="h3" id="kg-catalog-title"><BookDatabase20Regular aria-hidden /> {STEP_TITLE}</Subtitle2>
      <Body1>{STEP_INTRO}</Body1>
      <Field label="Owner of the data products (optional)">
        <Input value={props.owner} onChange={(_, d) => props.onOwner(d.value)} placeholder="A name or e-mail" />
      </Field>
      <div className="kg-catalog-actions">
        <Button appearance="primary" icon={<Edit20Regular />} onClick={props.onPrepare} disabled={props.busy}>
          {a ? "Prepare again" : "Prepare (nothing is written)"}
        </Button>
      </div>
      {props.problem && <Body1 role="alert">{props.problem}</Body1>}
      {a && (
        <>
          <Caption1 role="status">{a.summary}</Caption1>
          <ul className="kg-catalog-cards">{a.products.map((c) => <Card key={c.slug} card={c} />)}</ul>

          <Subtitle2 as="h4">What would be written as you ({writeCount(a)})</Subtitle2>
          <ul className="kg-catalog-diff">{a.diff.map((r, i) => <Change key={`${r.item}-${r.field}-${i}`} row={r} />)}</ul>

          <Subtitle2 as="h4">Needs someone else</Subtitle2>
          <ul className="kg-catalog-plain">
            {approvals(a).map((g) => <li key={g.who}><strong>{g.who}</strong>: {g.steps.join("; ")}</li>)}
          </ul>
          <Caption1>{ENDORSE_LINE}</Caption1>
          <div className="kg-catalog-files">
            {Object.entries(a.handover.files).map(([path, content]) => (
              <FileActions key={path} file={{ filename: fileName(path), mime: fileMime(path), text: content }} label={path}
                ariaLabel={`Download ${path}`} copyLabel={`Copy ${path}`} />
            ))}
          </div>

          {props.written && a.results ? (
            <ul className="kg-catalog-plain" role="status">
              {a.results.map((r, i) => (
                <li key={i}>{r.item}, {r.field}: {r.ok ? "written" : `not written${r.hint ? ` (${r.hint})` : ""}`}</li>
              ))}
            </ul>
          ) : (
            <div className="kg-catalog-write">
              <Checkbox checked={props.checked} onChange={(_, d) => props.onChecked(!!d.checked)}
                label="I checked the changes above" disabled={!a.confirm || writeCount(a) === 0} />
              <Button appearance="primary" onClick={props.onWrite} disabled={!gate.ok || props.busy}>
                Write {writeCount(a)} change{writeCount(a) === 1 ? "" : "s"} as me
              </Button>
              {!gate.ok && <Caption1>{gate.why}</Caption1>}
            </div>
          )}
        </>
      )}
    </section>
  );
}

/** The panel with its own state; shown only where the editor provides CatalogContext. */
export function CatalogPanel() {
  const source = useContext(CatalogContext);
  const [answer, setAnswer] = useState<CatalogAnswer>();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string>();
  const [owner, setOwner] = useState(source?.owner ?? "");
  const [checked, setChecked] = useState(false);
  const [written, setWritten] = useState(false);
  if (!source) return null;
  const go = async (dryRun: boolean) => {
    setBusy(true);
    setProblem(undefined);
    try {
      const got = await source.run({ dryRun, confirm: dryRun ? null : answer?.confirm, owner: owner.trim() || null });
      setAnswer(dryRun ? got : { ...(answer as CatalogAnswer), ...got });
      setWritten(!dryRun);
      setChecked(false);
    } catch (e) {
      const err = e as { answer?: { error?: string; hint?: string }; message?: string };
      setProblem([err.answer?.error ?? err.message ?? "The engine could not answer.", err.answer?.hint].filter(Boolean).join(" "));
    } finally {
      setBusy(false);
    }
  };
  return (
    <CatalogView answer={answer} busy={busy} problem={problem} owner={owner} checked={checked} written={written}
      onOwner={setOwner} onPrepare={() => void go(true)} onChecked={setChecked} onWrite={() => void go(false)} />
  );
}
