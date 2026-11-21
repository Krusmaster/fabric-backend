/**
 * ED3 (Gustav's editor test of 21 November 2026, part 3): the Data product step decides less and asks nothing twice.
 * Pure functions (ed3Product.test.ts), deterministic, no AI:
 *
 * - the owner is filled: the one chosen, else the signed-in person by default (ED2's rule), said the same way here and
 *   in Publish to OneLake catalog, which no longer asks for an owner of its own (ownerShown);
 * - an output the latest Create built whose id this item lost is found by Krusgraph's plan marker and added when the
 *   marker is this data product's plan and the name is the one Create gave it (autoAdopt), said once (adoptedLine);
 * - a failed row says one short line and points to the result's single "Fix and finish"; Fabric's own message stays
 *   under Details (failedLine).
 */
import type { LeftoversAnswer, ProductRow } from "./productWords";

/** The owner shown and used: the saved one, else the signed-in person (by default). */
export function ownerShown(saved: string | undefined | null, you: string | undefined | null): { owner: string; byDefault: boolean } {
  const s = (saved ?? "").trim();
  if (s) return { owner: s, byDefault: false };
  return { owner: (you ?? "").trim(), byDefault: !!(you ?? "").trim() };
}

export function ownerLine(saved: string | undefined | null, you: string | undefined | null): string | undefined {
  const o = ownerShown(saved, you);
  if (!o.owner) return undefined;
  return o.byDefault ? `Owner: ${o.owner} (you, by default). Change it below.` : undefined;
}

/** The leftovers to adopt without asking: same plan, adoptable, and named as a row the latest Create built without an id. */
export function autoAdopt(rows: ProductRow[], leftovers: LeftoversAnswer | undefined): { id: string; name: string }[] {
  const want = new Set(rows.filter((r) => r.key.startsWith("unsaved:") && !r.id).map((r) => r.name.toLowerCase()));
  if (!want.size || !leftovers) return [];
  return leftovers.leftovers
    .filter((x) => x.same_plan && x.adopt_ok && x.name && want.has(x.name.toLowerCase()))
    .map((x) => ({ id: x.id, name: x.name as string }));
}

export function adoptedLine(names: string[]): string | undefined {
  if (!names.length) return undefined;
  return `Found and added: ${names.join(", ")} (Krusgraph's plan marker matched this data product's plan).`;
}

export const FAILED_LINE = "Not built. Fix and finish on the result builds what is missing, reusing what exists.";

/** A failed row's one line; the raw message is for Details. */
export function failedLine(row: ProductRow): { line: string; details?: string } {
  return { line: FAILED_LINE, details: row.why && row.why !== FAILED_LINE ? row.why : undefined };
}
