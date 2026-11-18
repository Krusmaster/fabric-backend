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
import React, { createContext, useContext, useId, useState } from "react";
import { Badge, Body1, Button, Caption1, Checkbox, Field, Input, Subtitle2 } from "@fluentui/react-components";
import { BookDatabase20Regular, Edit20Regular } from "@fluentui/react-icons";
import { FileActions } from "./fileOffer";
import { typeWord } from "./fabricIcons";
import { TypeIcon, TypeName } from "./itemIcons";
import {
  CatalogAnswer, CatalogCard, CatalogDiffRow, ENDORSE_LINE, OwnerPerson, STEP_INTRO, STEP_TITLE, approvals, canWrite, diffLine,
  fileMime, fileName, ownerProblem, personValue, ruleCounts, shown, writeCount,
} from "./catalogWords";

export interface CatalogSource {
  /** dry_run true: what would be written; false with the confirm: write it. Rejects with the engine's error.
   * WB10: `include`, the ids of items Krusgraph did not build that the person ticked. */
  run: (opts: { dryRun: boolean; confirm?: string | null; owner?: string | null; include?: string[] }) => Promise<CatalogAnswer>;
  /** the data product's owner as the Data product page saved it, if any */
  owner?: string | null;
  /** WB10: the workspace's people and groups (the Data product page's list) and the signed-in person, for the picker */
  people?: OwnerPerson[] | null;
  you?: string | null;
  /** WB10: the names of the items this Model built: never an owner */
  itemNames?: string[];
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

/** WB11: "the lakehouse demo_lh", or the name alone for a type without a word. */
function typedItem(r: CatalogDiffRow): string {
  const w = typeWord(r.type ?? undefined);
  // a type that starts with an acronym (SQL database, API for GraphQL) keeps its capitals
  return w ? `the ${/^.[A-Z]/.test(w) ? w : w[0].toLowerCase() + w.slice(1)} ${r.item}` : r.item;
}

function Change(props: { row: CatalogDiffRow; included?: boolean; onInclude?: (id: string, on: boolean) => void; busy?: boolean }) {
  const r = props.row;
  if (r.action === "optional") {
    // WB10: an item Krusgraph did not build (the source lakehouse): unticked, with one line why
    return (
      <li className="kg-catalog-change" data-action="optional" aria-label={diffLine(r)}>
        <Checkbox checked={!!props.included} disabled={props.busy || !r.item_id}
          onChange={(_, d) => r.item_id && props.onInclude?.(r.item_id, !!d.checked)}
          label={<TypeName type={r.type} text={`Also write the ${r.field} of ${typedItem(r)}`} />} />
        <Caption1>{r.why}.</Caption1>
        {r.after ? <Caption1> If ticked, the description would be: {shown(r.after)}</Caption1> : null}
      </li>
    );
  }
  return (
    <li className="kg-catalog-change" data-action={r.action} aria-label={diffLine(r)}>
      <div className="kg-catalog-change-head">
        <span className="krusgraph-item-title">
          <TypeIcon type={r.type} beside={typeWord(r.type ?? undefined)} />
          {typeWord(r.type ?? undefined) && <span>{typeWord(r.type ?? undefined)}</span>}
          <strong>{r.item}</strong>
        </span>
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
  people?: OwnerPerson[] | null; you?: string | null; itemNames?: string[];
  include?: string[]; onInclude?: (id: string, on: boolean) => void;
}) {
  const a = props.answer;
  const gate = canWrite(a, props.checked);
  const listId = `kg-catalog-people-${useId().replace(/[^A-Za-z0-9_-]/g, "")}`;
  const people = props.people ?? [];
  const bad = ownerProblem(props.owner, props.people, props.you, props.itemNames);
  return (
    <section className="kg-catalog" aria-labelledby="kg-catalog-title">
      <Subtitle2 as="h3" id="kg-catalog-title"><BookDatabase20Regular aria-hidden /> {STEP_TITLE}</Subtitle2>
      <Body1>{STEP_INTRO}</Body1>
      {/* WB10: the same picker as the Data product page's Owner; autocomplete off and a name of its own, so the browser
          never fills it with a value typed in another field (an item's name, live test of 18 Nov 2026) */}
      <Field label="Owner of the data products (optional)" validationState={bad ? "error" : "none"} validationMessage={bad || undefined}
        hint="A person or group with a role in this workspace">
        <Input value={props.owner} onChange={(_, d) => props.onOwner(d.value)} name="kg-catalog-owner" autoComplete="off"
          list={people.length ? listId : undefined} placeholder={people.length ? "Start typing a name" : "A person's or group's name or e-mail"} />
      </Field>
      {people.length > 0 && (
        <datalist id={listId}>
          {people.map((p) => <option key={`${p.type}:${p.name}:${p.upn ?? ""}`} value={personValue(p)}>{`${p.name}, ${p.type === "Group" ? "group" : p.role ?? "person"}`}</option>)}
        </datalist>
      )}
      <div className="kg-catalog-actions">
        {props.you && <Button appearance="secondary" onClick={() => props.onOwner(props.you!)} disabled={props.busy}>Me ({props.you})</Button>}
        <Button appearance="primary" icon={<Edit20Regular />} onClick={props.onPrepare} disabled={props.busy || !!bad}>
          {a ? "Prepare again" : "Prepare (nothing is written)"}
        </Button>
      </div>
      {props.problem && <Body1 role="alert">{props.problem}</Body1>}
      {a && (
        <>
          <Caption1 role="status">{a.summary}</Caption1>
          <ul className="kg-catalog-cards">{a.products.map((c) => <Card key={c.slug} card={c} />)}</ul>

          <Subtitle2 as="h4">What would be written as you ({writeCount(a)})</Subtitle2>
          <ul className="kg-catalog-diff">
            {a.diff.map((r, i) => (
              <Change key={`${r.item}-${r.field}-${i}`} row={r} busy={props.busy}
                included={!!r.item_id && (props.include ?? []).includes(r.item_id)} onInclude={props.onInclude} />
            ))}
          </ul>

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
  // WB10: never prefilled with an item's name
  const saved = source?.owner ?? "";
  const [owner, setOwner] = useState(ownerProblem(saved, null, null, source?.itemNames) ? "" : saved);
  const [checked, setChecked] = useState(false);
  const [written, setWritten] = useState(false);
  const [include, setInclude] = useState<string[]>([]);
  if (!source) return null;
  const go = async (dryRun: boolean, inc: string[] = include) => {
    setBusy(true);
    setProblem(undefined);
    try {
      const got = await source.run({ dryRun, confirm: dryRun ? null : answer?.confirm, owner: owner.trim() || null, include: inc });
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
  // WB10: ticking an item Krusgraph did not build prepares again with it, so the confirm covers exactly what is shown
  const onInclude = (id: string, on: boolean) => {
    const next = on ? [...new Set([...include, id])] : include.filter((x) => x !== id);
    setInclude(next);
    void go(true, next);
  };
  return (
    <CatalogView answer={answer} busy={busy} problem={problem} owner={owner} checked={checked} written={written}
      people={source.people} you={source.you} itemNames={source.itemNames} include={include} onInclude={onInclude}
      onOwner={setOwner} onPrepare={() => void go(true)} onChecked={setChecked} onWrite={() => void go(false)} />
  );
}
