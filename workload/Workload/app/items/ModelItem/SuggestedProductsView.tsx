/** n222: the "Suggested data products" panel after the review, and the ticked ones on the dry run (productSuggestions.ts).
 * W1: each part on its own line (Fluent's Body1 and Caption1 are inline spans: side by side they ran together), and
 * the panel as wide as the output cards above it (.krusgraph-suggested in ModelItem.scss). */
import React from "react";
import { Body1, Caption1, Checkbox, Subtitle2 } from "@fluentui/react-components";
import { ChosenProductAnswer, SuggestedProducts } from "./engineClient";
import { Ticked, chosenLine, interfaceLines, isTicked, noteLine, panelLine, productParts, stale, toggle, unassignedLine } from "./productSuggestions";

export function SuggestedProductsPanel(props: {
  suggested?: SuggestedProducts | null;
  ticked: Ticked[];
  onTicked: (list: Ticked[]) => void;
  disabled?: boolean;
}) {
  const s = props.suggested;
  if (!s) return null;
  const old = stale(props.ticked, s);
  const notIn = unassignedLine(s);
  return (
    <section className="krusgraph-suggested" aria-label="Suggested data products">
      <Subtitle2 as="h3" block>Suggested data products</Subtitle2>
      <Body1 as="p" block>{panelLine(s)}</Body1>
      <ul className="krusgraph-list kg-suggested-list">
        {s.products.map((p) => {
          const part = productParts(p);
          return (
            <li key={p.id} data-product={p.id} className="kg-suggested-item">
              <Checkbox checked={isTicked(props.ticked, p.id)} disabled={props.disabled} label={part.title}
                onChange={(_, d) => props.onTicked(toggle(props.ticked, p, !!d.checked, s.products))} />
              <Body1 as="p" block>{part.tables}</Body1>
              <Caption1 as="p" block>{part.grouped}</Caption1>
              {part.named && <Caption1 as="p" block>{part.named}</Caption1>}
              {interfaceLines(p).length > 0 ? (
                <ul className="krusgraph-list" aria-label={`Interface of ${p.name}`}>
                  {interfaceLines(p).map((l) => <li key={l}><Caption1 block>{l}</Caption1></li>)}
                </ul>
              ) : <Caption1 as="p" block>Interface: no link to another suggested data product.</Caption1>}
              <details>
                <summary>Evidence ({p.evidence.length})</summary>
                <ul className="krusgraph-list">
                  {p.evidence.map((e) => <li key={e}><Caption1 block>{e}</Caption1></li>)}
                </ul>
              </details>
            </li>
          );
        })}
      </ul>
      {notIn && <Caption1 as="p" block>{notIn}</Caption1>}
      {old.length > 0 && (
        <Caption1 as="p" block>Ticked earlier, not suggested by this review: {old.map((t) => t.name).join(", ")}; the dry run says so.</Caption1>
      )}
      <Caption1 as="p" block>{noteLine(s)}</Caption1>
    </section>
  );
}

export function ChosenProductsView(props: { products?: ChosenProductAnswer[] }) {
  if (!props.products?.length) return null;
  return (
    <section className="krusgraph-suggested" aria-label="Data products (dry run)">
      <Subtitle2 as="h3" block>Data products (dry run)</Subtitle2>
      <ul className="krusgraph-list">
        {props.products.map((p) => (
          <li key={p.id} data-product={p.id}>
            <Body1 block>{chosenLine(p)}</Body1>
            {interfaceLines(p).map((l) => <Caption1 key={l} block>{l}</Caption1>)}
            {(p.items ?? []).length > 0 && <Caption1 block>Items: {(p.items ?? []).map((i) => i.name).join(", ")}</Caption1>}
          </li>
        ))}
      </ul>
    </section>
  );
}
