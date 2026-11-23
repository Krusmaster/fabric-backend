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
import { Badge, Body1, Button, Caption1, Checkbox, Subtitle2 } from "@fluentui/react-components";
import { BookDatabase20Regular, Edit20Regular, Open20Regular } from "@fluentui/react-icons";
import { FileActions, FileContext } from "./fileOffer";
import { MASCOT_CSS } from "./cardMap.generated";
import { catalogCheer } from "./cheer";
import { useCheer } from "./cheerView";
import { MascotSays } from "./mascotFigure";
import { FABRIC_PORTAL, openInNewTab } from "./openInFabric";
import { ownerShown } from "./ed3Product";
import { typeWord } from "./fabricIcons";
import { TypeIcon, TypeName } from "./itemIcons";
import {
  CatalogAnswer, CatalogCard, CatalogDiffRow, DIFF_ID, ENDORSE_LINE, OwnerPerson, STEP_INTRO, STEP_TITLE, approvals, canWrite,
  catalogPlace, diffLine, fileMime, fileName, gateSummary, ownerProblem, partialLine, receiptLines, ruleCounts, seeChangesLabel, shown,
  writeCount,
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
          {r.model_item ? <span>This Krusgraph Model item</span> : typeWord(r.type ?? undefined) && <span>{typeWord(r.type ?? undefined)}</span>}
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

/** W3: the box and the Write button beside Prepare again, after a short summary and the link to the changes. */
function WriteGate(props: { a: CatalogAnswer; checked: boolean; busy: boolean; onChecked: (v: boolean) => void; onWrite: () => void }) {
  const a = props.a;
  const gate = canWrite(a, props.checked);
  const n = writeCount(a);
  return (
    <div className="kg-catalog-write" data-w3="write-gate">
      {gateSummary(a) && <Caption1 as="p" block role="status">{gateSummary(a)}</Caption1>}
      {n > 0 && (
        <a href={`#${DIFF_ID}`} className="kg-catalog-see" onClick={(e) => {
          e.preventDefault();
          document.getElementById(DIFF_ID)?.scrollIntoView?.({ behavior: "smooth", block: "start" });
        }}>{seeChangesLabel(a)}</a>
      )}
      {/* ED3: where writing is off, no checkbox to tick; the reason beside the button, in plain words */}
      {a.writable !== false && (
        <Checkbox checked={props.checked} onChange={(_, d) => props.onChecked(!!d.checked)}
          label="I checked the changes" disabled={!a.confirm || n === 0 || props.busy} />
      )}
      <div className="kg-catalog-actions">
        <Button appearance="primary" onClick={props.onWrite} disabled={!gate.ok || props.busy}
          aria-describedby={!gate.ok ? "kg-catalog-why" : undefined}>
          Write {n} change{n === 1 ? "" : "s"} as me
        </Button>
        {!gate.ok && <Caption1 id="kg-catalog-why">{gate.why}</Caption1>}
      </div>
    </div>
  );
}

/** W3: after a write: Onto's cheer once (or the same words plain), the receipt compactly, and where to look. */
function Written(props: { a: CatalogAnswer }) {
  const results = props.a.results ?? [];
  const cheer = catalogCheer(results);
  const mascot = useCheer("catalog_written", "catalog", cheer);
  const place = catalogPlace(props.a.workspace, FABRIC_PORTAL);
  const files = useContext(FileContext);
  return (
    <div className="kg-catalog-done" role="status" data-w3="written">
      {cheer && mascot ? (
        <ul className="krusgraph-mascots krusgraph-cheer" data-w3-cheer="catalog_written">
          <style>{MASCOT_CSS}</style>
          <MascotSays kind="onto" text={cheer} pose="celebrate" glad />
        </ul>
      ) : (
        <Body1 as="p" block>{cheer ?? partialLine(results)}</Body1>
      )}
      {receiptLines(results).map((l) => <Caption1 as="p" block key={l}>{l}</Caption1>)}
      {place && cheer && (
        <>
          <div className="kg-catalog-actions">
            <a href={place.url} target="_blank" rel="noopener noreferrer" className="kg-open-fabric kg-open-fabric-primary"
              data-w3="open-catalog" onClick={(e) => {
                e.preventDefault();
                void openInNewTab(place.url, files?.open);
              }}>
              <Open20Regular aria-hidden /> {place.label}
            </a>
          </div>
          <Caption1 as="p" block>{place.line}</Caption1>
        </>
      )}
    </div>
  );
}

export function CatalogView(props: {
  answer?: CatalogAnswer; busy: boolean; problem?: string; owner: string; checked: boolean; written?: boolean;
  onOwner: (v: string) => void; onPrepare: () => void; onChecked: (v: boolean) => void; onWrite: () => void;
  people?: OwnerPerson[] | null; you?: string | null; itemNames?: string[];
  include?: string[]; onInclude?: (id: string, on: boolean) => void;
}) {
  const a = props.answer;
  const bad = undefined as string | undefined;   // ED3: the owner is the data product's, checked where it is set
  return (
    <section className="kg-catalog" aria-labelledby="kg-catalog-title">
      <Subtitle2 as="h3" id="kg-catalog-title"><BookDatabase20Regular aria-hidden /> {STEP_TITLE}</Subtitle2>
      <Body1>{STEP_INTRO}</Body1>
      {/* ED3 (Gustav: the owner asked twice on one page): the data product's owner, changed in one place (Owner above) */}
      <Caption1 data-ed3="owner">{props.owner
        ? `Owner: ${props.owner}, the data product's owner (change it under Owner above). It is kept in this item; no e-mail address goes into a description.`
        : "No owner yet: set it under Owner above."}</Caption1>
      <div className="kg-catalog-actions">
        <Button appearance="primary" icon={<Edit20Regular />} onClick={props.onPrepare} disabled={props.busy || !!bad}>
          {a ? "Prepare again" : "Prepare (nothing is written)"}
        </Button>
      </div>
      {props.problem && <Body1 role="alert">{props.problem}</Body1>}
      {/* W3 (Gustav, 23 Nov 2026): the box and Write sit right under Prepare again; after a write, the cheer and receipt */}
      {a && (props.written && a.results ? <Written a={a} /> :
        <WriteGate a={a} checked={props.checked} busy={props.busy} onChecked={props.onChecked} onWrite={props.onWrite} />)}
      {a && (
        <>
          <Caption1 as="p" block>{a.summary}</Caption1>
          <ul className="kg-catalog-cards">{a.products.map((c) => <Card key={c.slug} card={c} />)}</ul>

          <Subtitle2 as="h4" id={DIFF_ID} tabIndex={-1}>What would be written as you ({writeCount(a)})</Subtitle2>
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
  // ED3: the data product's owner (else the signed-in person, by default): one owner, set in one place
  const saved = ownerShown(source?.owner, source?.you).owner;
  const owner = ownerProblem(saved, null, null, source?.itemNames) ? ownerShown(null, source?.you).owner : saved;
  const setOwner = (_: string) => {};
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
