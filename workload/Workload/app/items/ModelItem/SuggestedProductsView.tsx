/** n222: the "Suggested data products" panel after the review, and the ticked ones on the dry run (productSuggestions.ts). */
import React from "react";
import { Body1, Caption1, Checkbox, Subtitle2 } from "@fluentui/react-components";
import { ChosenProductAnswer, SuggestedProducts } from "./engineClient";
import { Ticked, chosenLine, interfaceLines, isTicked, panelLine, stale, toggle } from "./productSuggestions";

export function SuggestedProductsPanel(props: {
  suggested?: SuggestedProducts | null;
  ticked: Ticked[];
  onTicked: (list: Ticked[]) => void;
  disabled?: boolean;
}) {
  const s = props.suggested;
  if (!s) return null;
  const old = stale(props.ticked, s);
  return (
    <section className="krusgraph-suggested" aria-label="Suggested data products">
      <Subtitle2>Suggested data products</Subtitle2>
      <Body1>{panelLine(s)}</Body1>
      <ul className="krusgraph-list">
        {s.products.map((p) => (
          <li key={p.id} data-product={p.id}>
            <Checkbox checked={isTicked(props.ticked, p.id)} disabled={props.disabled}
              label={`${p.name}: ${p.tables.length} table${p.tables.length === 1 ? "" : "s"}`}
              onChange={(_, d) => props.onTicked(toggle(props.ticked, p, !!d.checked, s.products))} />
            <Body1>Tables: {p.tables.join(", ")}</Body1>
            <Caption1>Grouped by: {p.rule} Named so because {p.name_reason}.</Caption1>
            {interfaceLines(p).length > 0 ? (
              <ul className="krusgraph-list" aria-label={`Interface of ${p.name}`}>
                {interfaceLines(p).map((l) => <li key={l}><Caption1>{l}</Caption1></li>)}
              </ul>
            ) : <Caption1>Interface: no link to another suggested data product.</Caption1>}
            <details>
              <summary>Evidence ({p.evidence.length})</summary>
              <ul className="krusgraph-list">
                {p.evidence.map((e) => <li key={e}><Caption1>{e}</Caption1></li>)}
              </ul>
            </details>
          </li>
        ))}
      </ul>
      {s.unassigned.length > 0 && (
        <Caption1>Not in a suggestion: {s.unassigned.map((u) => `${u.table} (${u.reason})`).join("; ")}.</Caption1>
      )}
      {old.length > 0 && (
        <Caption1>Ticked earlier, not suggested by this review: {old.map((t) => t.name).join(", ")}; the dry run says so.</Caption1>
      )}
      <Caption1>{s.note} From {s.from}.</Caption1>
    </section>
  );
}

export function ChosenProductsView(props: { products?: ChosenProductAnswer[] }) {
  if (!props.products?.length) return null;
  return (
    <section className="krusgraph-suggested" aria-label="Data products (dry run)">
      <Subtitle2>Data products (dry run)</Subtitle2>
      <ul className="krusgraph-list">
        {props.products.map((p) => (
          <li key={p.id} data-product={p.id}>
            <Body1>{chosenLine(p)}</Body1>
            {interfaceLines(p).map((l) => <Caption1 key={l} block>{l}</Caption1>)}
            {(p.items ?? []).length > 0 && <Caption1 block>Items: {(p.items ?? []).map((i) => i.name).join(", ")}</Caption1>}
          </li>
        ))}
      </ul>
    </section>
  );
}
