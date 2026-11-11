/**
 * n198: the Data product page (productWords.ts has its words and rules; fabric_backend/product_life.py its engine).
 * Native elements and its own CSS (PRODUCT_CSS, Fluent's tokens with light and dark fallbacks), so the same component
 * renders inside Fabric and, for the browser tests, on its own (dataProductPage.test.ts writes the rendered states to
 * tests/fixtures/n198/, which tests/test_n198_browser.py opens at 375 and 1280 px, light and dark, by keyboard).
 * Colour is never the only signal: every state has its word and a mark. Every action is a button in the tab order.
 */
import React, { useState } from "react";
import { BuildCard } from "./engineClient";
import { itemTypeLabel } from "./createWords";
import { OutputsDefinition } from "./ModelItemDefinition";
import {
  KEEPS_DATA, LeftoversAnswer, OutOfDate, Person, ProductRow, RetireAnswer, STATE, StatusAnswer, healthWords, lastRunWords,
  leftoverWords, outOfDateSummary, ownerWords, resultWords, rowsOf, summary, typedNameOk,
} from "./productWords";

export const PRODUCT_CSS = `
.kg-dp{--kg-fg:var(--colorNeutralForeground1,#1f1f1f);--kg-fg2:var(--colorNeutralForeground2,#424242);
--kg-bg:var(--colorNeutralBackground1,#ffffff);--kg-bg2:var(--colorNeutralBackground2,#f5f5f5);
--kg-line:var(--colorNeutralStroke1,#c7c7c7);--kg-brand:var(--colorBrandBackground,#0f6cbd);--kg-on-brand:var(--colorNeutralForegroundOnBrand,#ffffff);
--kg-ok:#0e700e;--kg-bad:#b10e1c;--kg-warn:#8a3707;--kg-wait:#3b3a39;--kg-focus:var(--colorStrokeFocus2,#000000);
color:var(--kg-fg);background:var(--kg-bg);font-family:var(--fontFamilyBase,"Segoe UI",system-ui,sans-serif);font-size:14px;line-height:1.45;
box-sizing:border-box;max-width:960px;padding:16px;overflow-wrap:anywhere}
@media (prefers-color-scheme:dark){.kg-dp{--kg-fg:var(--colorNeutralForeground1,#f0f0f0);--kg-fg2:var(--colorNeutralForeground2,#d6d6d6);
--kg-bg:var(--colorNeutralBackground1,#1f1f1f);--kg-bg2:var(--colorNeutralBackground2,#2b2b2b);--kg-line:var(--colorNeutralStroke1,#666666);
--kg-brand:var(--colorBrandBackground,#115ea3);--kg-ok:#6ccb5f;--kg-bad:#ff99a4;--kg-warn:#fce100;--kg-wait:#d6d6d6;--kg-focus:var(--colorStrokeFocus2,#ffffff)}}
.kg-dp *{box-sizing:border-box}
.kg-dp h2{font-size:20px;margin:0 0 4px}.kg-dp h3{font-size:16px;margin:0 0 8px}
.kg-dp section{border-top:1px solid var(--kg-line);padding:12px 0;margin:0}
.kg-dp p{margin:4px 0}.kg-dp .kg-dp-muted{color:var(--kg-fg2)}
.kg-dp ul{list-style:none;margin:8px 0;padding:0}
.kg-dp li.kg-dp-row{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline;padding:8px;border:1px solid var(--kg-line);border-radius:4px;margin:0 0 8px;background:var(--kg-bg2)}
.kg-dp .kg-dp-state{font-weight:600}
.kg-dp .kg-dp-mark{display:inline-block;min-width:1.4em;text-align:center;border-radius:3px;margin-right:4px;font-weight:700}
.kg-dp .tone-ok{color:var(--kg-ok)}.kg-dp .tone-bad{color:var(--kg-bad)}.kg-dp .tone-warn{color:var(--kg-warn)}
.kg-dp .tone-wait,.kg-dp .tone-off{color:var(--kg-wait)}
.kg-dp .kg-dp-name{font-weight:600}.kg-dp .kg-dp-why{flex-basis:100%;color:var(--kg-fg2)}
.kg-dp .kg-dp-actions{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.kg-dp button{font:inherit;min-height:32px;padding:4px 12px;border-radius:4px;border:1px solid var(--kg-line);background:var(--kg-bg);color:var(--kg-fg);cursor:pointer}
.kg-dp button.kg-dp-primary{background:var(--kg-brand);border-color:var(--kg-brand);color:var(--kg-on-brand)}
.kg-dp button.kg-dp-danger{border-color:var(--kg-bad);color:var(--kg-bad);background:var(--kg-bg)}
.kg-dp button:disabled{opacity:.55;cursor:not-allowed}
.kg-dp button:focus-visible,.kg-dp input:focus-visible,.kg-dp select:focus-visible{outline:2px solid var(--kg-focus);outline-offset:2px}
.kg-dp label{display:inline-flex;gap:6px;align-items:center}
.kg-dp input[type=text]{font:inherit;min-height:32px;padding:4px 8px;border:1px solid var(--kg-line);border-radius:4px;background:var(--kg-bg);color:var(--kg-fg);width:100%;max-width:360px}
.kg-dp .kg-dp-field{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}
.kg-dp .kg-dp-field>label{display:block;flex-basis:100%;font-weight:600}
.kg-dp .kg-dp-note{border-left:4px solid var(--kg-warn);padding:4px 8px;background:var(--kg-bg2);margin:8px 0}
.kg-dp .kg-dp-sr{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.kg-dp .kg-dp-facts{display:grid;grid-template-columns:minmax(0,1fr);gap:2px}
@media (min-width:640px){.kg-dp .kg-dp-facts{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}}
`;

export interface DataProductProps {
  productName: string;
  outputs: OutputsDefinition;
  /** the engine's states; absent until Fabric has been read */
  status?: StatusAnswer;
  /** n200's health in words (productWords.healthWords) */
  health?: string;
  /** what is running now, in words (the buttons wait) */
  busy?: string;
  /** a problem to say in one line (the engine's error and hint) */
  problem?: string;
  updates?: OutOfDate[];
  retire?: RetireAnswer;
  leftovers?: LeftoversAnswer;
  onRefresh?: () => void;
  onOpen?: (row: ProductRow) => void;
  onOwner?: (name: string) => void;
  onCheckUpdates?: () => void;
  onUpdate?: (card: BuildCard) => void;
  onNewName?: (card: BuildCard) => void;
  /** a dry run (no confirm) or the real call (confirm from that dry run, typed for Delete from Fabric) */
  onRetire?: (scope: "soft" | "delete", ids: string[] | null, opts: { leftovers?: boolean; confirm?: string; typed?: string }) => void;
  onFindLeftovers?: () => void;
  onAdopt?: (id: string) => void;
  /** the typed name and the chosen rows, for a rendering of a given moment (tests); the page keeps its own otherwise */
  initialTyped?: string;
  initialChosen?: string[];
}

export function DataProductView(props: DataProductProps) {
  const rows = rowsOf(props.outputs, props.status);
  const [chosen, setChosen] = useState<string[]>(props.initialChosen ?? []);
  const [typed, setTyped] = useState(props.initialTyped ?? "");
  const [owner, setOwner] = useState(props.outputs.product?.owner ?? "");
  const busy = !!props.busy;
  const people: Person[] = props.status?.people ?? [];
  const ids = chosen.length ? chosen : null;
  const toggle = (id: string) => setChosen((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  const r = props.retire;
  const plan = props.outputs.product?.plan?.plan_id;
  const deletable = rows.filter((x) => x.id && x.state !== "removed");
  return (
    <div className="kg-dp" aria-busy={busy}>
      <style>{PRODUCT_CSS}</style>
      <h2>Data product: {props.productName}</h2>
      <div className="kg-dp-facts">
        <p>{ownerWords(props.outputs.product)}</p>
        <p>{props.health ?? healthWords(undefined)}</p>
        <p>{lastRunWords(props.outputs)}</p>
        <p>Plan id: {plan ?? "not recorded"}</p>
      </div>
      <p className="kg-dp-muted" aria-live="polite">{props.busy ? `${props.busy}` : summary(rows)}</p>
      {props.problem && <p className="kg-dp-note" role="alert">{props.problem}</p>}
      <div className="kg-dp-actions">
        <button type="button" onClick={() => props.onRefresh?.()} disabled={busy}>Read Fabric again</button>
      </div>

      <section aria-labelledby="kg-dp-owner">
        <h3 id="kg-dp-owner">Owner</h3>
        <div className="kg-dp-field">
          <label htmlFor="kg-dp-owner-input">The person or group who answers for this data product</label>
          <input id="kg-dp-owner-input" type="text" list="kg-dp-people" value={owner} autoComplete="off"
            onChange={(e) => setOwner(e.target.value)} placeholder={people.length ? "Start typing a name" : "A name or an e-mail address"} />
          <datalist id="kg-dp-people">
            {people.map((p) => <option key={`${p.type}:${p.name}:${p.upn ?? ""}`} value={p.upn ? `${p.name} (${p.upn})` : p.name}>{`${p.name}, ${p.type === "Group" ? "group" : p.role ?? "person"}`}</option>)}
          </datalist>
          <button type="button" onClick={() => props.onOwner?.(owner)} disabled={busy || owner.trim() === (props.outputs.product?.owner ?? "")}>Save owner</button>
          {props.status?.you && <button type="button" onClick={() => { setOwner(props.status!.you!); props.onOwner?.(props.status!.you!); }} disabled={busy}>Me ({props.status.you})</button>}
        </div>
        <p className="kg-dp-muted">{people.length ? `${people.length} people and groups have a role in this workspace.` : "Kept in this item (outputs.json)."}</p>
      </section>

      <section aria-labelledby="kg-dp-items">
        <h3 id="kg-dp-items">Items</h3>
        <ul>
          {rows.map((x) => {
            const s = STATE[x.state];
            return (
              <li key={x.key} className="kg-dp-row" data-state={x.state}>
                <span className={`kg-dp-state tone-${s.tone}`}><span className="kg-dp-mark" aria-hidden="true">{s.mark}</span>{s.label}</span>
                <span>{x.typeLabel}</span>
                <span className="kg-dp-name">{x.name}</span>
                {x.why && <span className="kg-dp-why">{x.why}</span>}
                {(x.openable && x.id) || (x.id && x.state !== "removed") ? (
                  <span className="kg-dp-actions">
                    {x.openable && x.id && <button type="button" onClick={() => props.onOpen?.(x)}>Open in Fabric<span className="kg-dp-sr">: {x.name}</span></button>}
                    {x.id && x.state !== "removed" && (
                      <label><input type="checkbox" checked={chosen.includes(x.id)} onChange={() => toggle(x.id!)} disabled={busy} />Choose {x.name} for Retire</label>
                    )}
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-labelledby="kg-dp-update">
        <h3 id="kg-dp-update">Update</h3>
        <p>Counts the rows again and makes a dry run of every output: what is out of date, with Update (a dry run first, then your confirmation) or a new name. Nothing is written until you confirm.</p>
        <div className="kg-dp-actions">
          <button type="button" className="kg-dp-primary" onClick={() => props.onCheckUpdates?.()} disabled={busy}>Check against the rows again</button>
        </div>
        {props.updates && (
          <>
            <p aria-live="polite">{outOfDateSummary(props.updates)}</p>
            <ul>
              {props.updates.map((u) => (
                <li key={u.output} className="kg-dp-row" data-update={u.kind}>
                  <span className={`kg-dp-state tone-${u.kind === "up_to_date" ? "ok" : u.kind === "differs" ? "warn" : "bad"}`}>
                    <span className="kg-dp-mark" aria-hidden="true">{u.kind === "up_to_date" ? "✓" : u.kind === "differs" ? "!" : "?"}</span>
                    {u.kind === "up_to_date" ? "Up to date" : u.kind === "differs" ? "Out of date" : u.kind === "missing" ? "Not in the workspace" : "Not checked"}
                  </span>
                  <span>{u.label}</span><span className="kg-dp-name">{u.name}</span>
                  <span className="kg-dp-why">{u.words}</span>
                  {u.actions.length > 0 && (
                    <span className="kg-dp-actions">
                      {u.actions.includes("update") && <button type="button" onClick={() => props.onUpdate?.(u.card)} disabled={busy}>Update {u.name}: see the dry run</button>}
                      {u.actions.includes("confirm_update") && <button type="button" className="kg-dp-primary" onClick={() => props.onUpdate?.(u.card)} disabled={busy}>Update {u.name} in Fabric</button>}
                      {u.actions.includes("new_name") && <button type="button" onClick={() => props.onNewName?.(u.card)} disabled={busy}>Build {u.name} under a new name</button>}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section aria-labelledby="kg-dp-retire">
        <h3 id="kg-dp-retire">Retire</h3>
        <p>{chosen.length ? `${chosen.length} item(s) chosen above.` : "No item chosen above: Retire applies to the whole data product."} {KEEPS_DATA}</p>
        <div className="kg-dp-actions">
          <button type="button" onClick={() => props.onRetire?.("soft", ids, {})} disabled={busy || !deletable.length}>1. Turn off: see what stops</button>
          <button type="button" className="kg-dp-danger" onClick={() => props.onRetire?.("delete", ids, {})} disabled={busy || !deletable.length}>2. Delete from Fabric: see the dry run</button>
        </div>
        {r && <RetirePanel r={r} typed={typed} setTyped={setTyped} busy={busy} productName={props.productName} onRetire={props.onRetire} />}
      </section>

      <section aria-labelledby="kg-dp-left">
        <h3 id="kg-dp-left">Clean up leftovers</h3>
        <p>Items in this workspace that carry Krusgraph's plan marker but that no Krusgraph Model lists, such as one Fabric finished after a Create stopped waiting.</p>
        <div className="kg-dp-actions">
          <button type="button" onClick={() => props.onFindLeftovers?.()} disabled={busy}>Look for leftovers</button>
        </div>
        {props.leftovers && (
          <>
            {props.leftovers.unread_models.length > 0 && (
              <p className="kg-dp-note">Another Krusgraph Model ({props.leftovers.unread_models.join(", ")}) could not be read, so nothing below can be deleted from here.</p>
            )}
            <p aria-live="polite">{props.leftovers.leftovers.length ? `${props.leftovers.leftovers.length} leftover(s) found.` : "No leftovers: every item with Krusgraph's marker belongs to a Krusgraph Model."}</p>
            <ul>
              {props.leftovers.leftovers.map((x) => (
                <li key={x.id} className="kg-dp-row" data-leftover={x.id}>
                  <span className="kg-dp-state tone-warn"><span className="kg-dp-mark" aria-hidden="true">!</span>Leftover</span>
                  <span className="kg-dp-why">{leftoverWords(x)}</span>
                  {!x.adopt_ok && x.adopt_why && <span className="kg-dp-why">{x.adopt_why}</span>}
                  {!x.delete_ok && x.why && <span className="kg-dp-why">{x.why}</span>}
                  <span className="kg-dp-actions">
                    <button type="button" onClick={() => props.onAdopt?.(x.id)} disabled={busy || !x.adopt_ok}>Adopt {x.name} into this data product</button>
                    <button type="button" className="kg-dp-danger" onClick={() => props.onRetire?.("delete", [x.id], { leftovers: true })} disabled={busy || !x.delete_ok}>Delete {x.name}: see the dry run</button>
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}

function RetirePanel(props: { r: RetireAnswer; typed: string; setTyped: (s: string) => void; busy: boolean; productName: string;
  onRetire?: DataProductProps["onRetire"] }) {
  const { r } = props;
  const ok = typedNameOk(props.typed, props.productName);
  const ids = r.items?.map((x) => x.id) ?? null;
  return (
    <div role="region" aria-label={r.dry_run ? "Dry run" : "Result"} className="kg-dp-panel">
      <p><strong>{r.dry_run ? "Dry run: nothing has been changed yet." : "Done."}</strong> {r.words}</p>
      {r.scope === "soft" && r.steps && r.steps.length > 0 && (
        <ul>{r.steps.map((s, i) => <li key={i} className="kg-dp-row"><span className="kg-dp-name">{s.name}</span><span className="kg-dp-why">{s.words}</span>
          {s.result && <span className="kg-dp-why">{resultWords(s as { result: string; why?: string })}</span>}</li>)}</ul>
      )}
      {r.scope === "delete" && r.dry_run && r.items && r.items.length > 0 && (
        <ul aria-label="These items would be deleted">{r.items.map((x) => <li key={x.id} className="kg-dp-row"><span className="kg-dp-state tone-bad"><span className="kg-dp-mark" aria-hidden="true">✕</span>Would be deleted</span><span>{itemTypeLabel(x.type, x.output ?? undefined)}</span><span className="kg-dp-name">{x.name}</span></li>)}</ul>
      )}
      {r.results && (
        <ul aria-label="Result per item">{r.results.map((x) => <li key={x.id} className="kg-dp-row" data-result={x.result}>
          <span className={`kg-dp-state tone-${x.result === "failed" ? "bad" : "ok"}`}><span className="kg-dp-mark" aria-hidden="true">{x.result === "failed" ? "✕" : "✓"}</span>{resultWords(x)}</span>
          <span>{itemTypeLabel(x.type)}</span><span className="kg-dp-name">{x.name}</span></li>)}</ul>
      )}
      {r.refused.length > 0 && (
        <ul aria-label="Left alone">{r.refused.map((x) => <li key={x.id} className="kg-dp-row"><span className="kg-dp-state tone-off"><span className="kg-dp-mark" aria-hidden="true">–</span>Left alone</span><span className="kg-dp-name">{x.name ?? x.id}</span><span className="kg-dp-why">{x.why}</span></li>)}</ul>
      )}
      {r.dry_run && r.confirm && r.scope === "soft" && (
        <div className="kg-dp-actions">
          <button type="button" className="kg-dp-primary" disabled={props.busy} onClick={() => props.onRetire?.("soft", ids ?? (r.steps ?? []).map((s) => s.id), { confirm: r.confirm! })}>Turn these off now</button>
        </div>
      )}
      {r.dry_run && r.confirm && r.scope === "delete" && (
        <div className="kg-dp-field">
          <label htmlFor="kg-dp-typed">Type the data product's name, {props.productName}, to delete {r.items?.length ?? 0} item(s) from Fabric</label>
          <input id="kg-dp-typed" type="text" value={props.typed} autoComplete="off" onChange={(e) => props.setTyped(e.target.value)} aria-describedby="kg-dp-typed-help" />
          <span id="kg-dp-typed-help" className="kg-dp-muted">{ok ? "The name matches." : "Delete stays off until the name matches exactly."}</span>
          <button type="button" className="kg-dp-danger" disabled={props.busy || !ok}
            onClick={() => props.onRetire?.("delete", ids, { leftovers: r.leftovers, confirm: r.confirm!, typed: props.typed })}>
            Delete {r.items?.length ?? 0} item(s) from Fabric
          </button>
        </div>
      )}
      <p className="kg-dp-muted">{r.keeps}</p>
    </div>
  );
}
