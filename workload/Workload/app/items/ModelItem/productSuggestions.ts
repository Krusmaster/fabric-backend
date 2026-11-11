/**
 * n222: the founder's live test of 11 November 2026: "it must go faster, and I want suggestions on which data products to
 * create". Pure functions, no React (productSuggestions.test.ts).
 *
 * The suggestions are the engine's (workload_api.suggest_products: domain_draft's proposal, deterministic, no AI). The
 * editor shows them after the review, the person ticks the ones to build (outputs.json's `products`), and the dry run
 * shows each ticked one as a data product. The weekend's suggestion engine (W2) extends the engine function; this file
 * only words and keeps what the engine returned.
 */
import { ChosenProductAnswer, OperationState, SuggestedProduct, SuggestedProducts } from "./engineClient";
import { ModelDefinition } from "./ModelItemDefinition";

export const PREPARING = "Preparing the dry run of each output…";

/** The dry run's busy line: the engine's own words while it prepares the outputs side by side, else PREPARING. */
export function preparingLine(state?: OperationState): string {
  const words = state?.progress?.words;
  return typeof words === "string" && words.trim() ? words : PREPARING;
}

export type Ticked = { id: string; name: string };

export function ticked(d: ModelDefinition): Ticked[] {
  return d.outputs.products ?? [];
}

/** What the dry run sends: the ticked suggestions, nothing when none is ticked. */
export function chosenProducts(d: ModelDefinition): Ticked[] {
  return ticked(d).map((t) => ({ id: t.id, name: t.name }));
}

export function isTicked(list: Ticked[], id: string): boolean {
  return list.some((t) => t.id === id);
}

/** The list with one suggestion ticked or unticked, in the engine's order of the suggestions. */
export function toggle(list: Ticked[], s: SuggestedProduct, on: boolean, all: SuggestedProduct[]): Ticked[] {
  const ids = new Set(list.map((t) => t.id));
  if (on) ids.add(s.id);
  else ids.delete(s.id);
  const known = all.filter((x) => ids.has(x.id)).map((x) => ({ id: x.id, name: x.name }));
  const kept = list.filter((t) => ids.has(t.id) && !all.some((x) => x.id === t.id));   // ticked earlier, not suggested now
  return [...known, ...kept];
}

/** "provides its key to customers through order_items.product_id → products (R1)" and the other way round. */
export function interfaceLines(s: { interface?: SuggestedProduct["interface"] }): string[] {
  const f = s.interface ?? { provides: [], consumes: [] };
  const rule = (r: string) => (r ? ` (${r})` : "");
  return [
    ...f.provides.map((i) => `Provides to ${i.product}: ${i.link}${rule(i.rule)}`),
    ...f.consumes.map((i) => `Uses ${i.product}: ${i.link}${rule(i.rule)}`),
  ];
}

/** The panel's first line. */
export function panelLine(s: SuggestedProducts | null | undefined): string {
  if (!s) return "";
  if (!s.products.length) return "No data product to suggest: no two tables with a key are linked. Add keys or links in the review.";
  const n = s.products.length;
  return `${n} suggested data product${n === 1 ? "" : "s"}, from the keys and links you reviewed` +
    (s.checked ? " and what the rows hold." : "; check them against the rows to weigh each link by its rows.");
}

/** Ticked earlier but no longer suggested by this review: said, so it can be unticked. */
export function stale(list: Ticked[], s: SuggestedProducts | null | undefined): Ticked[] {
  if (!s) return [];
  return list.filter((t) => !s.products.some((p) => p.id === t.id));
}

/** The dry run's line for one ticked data product. */
export function chosenLine(p: ChosenProductAnswer): string {
  if (p.gone) return `${p.name}: ${p.words}`;
  return `${p.name}: ${(p.tables ?? []).join(", ")}. ${p.words}`;
}
