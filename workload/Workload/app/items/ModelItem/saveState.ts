/**
 * n225: whether the item's definition is saved in Fabric, in words the Data product page shows.
 *
 * The founder's phone test of 12 November 2026 (package 1.0.1074): after a Create that built 8 outputs, the Data product
 * page listed 2 items and "Plan id: not recorded". The editor saves outputs.json after every Create step
 * (updateItemDefinition, one save after the other); controller/ItemCRUDController.callUpdateItemDefinition answers
 * undefined when Fabric refuses a save, and the editor took that as saved. So a refused save went unnoticed, and the copy
 * of the item Fabric kept was an older one. Now a save that is not confirmed is tried again (a newer save supersedes an
 * older one, so only the latest copy is sent), and the page says Saved, Saving or Not saved.
 *
 * Pure functions, no React, no Fabric client (saveState.test.ts).
 */
export type SaveStatus =
  /** read from Fabric when the item was opened; nothing changed since */
  | { state: "loaded" }
  | { state: "saving"; since: string }
  | { state: "saved"; at: string }
  | { state: "failed"; at: string; tries: number };

/** The waits before each new try of a save Fabric did not confirm. */
export const SAVE_WAITS_MS = [1500, 4000, 10000];

export type SaveOutcome = "saved" | "superseded" | "failed";

/**
 * Sends one save and tries again while Fabric does not confirm it. `send` answers something truthy when Fabric took it
 * (updateItemDefinition's result), undefined or false otherwise; a throw counts as not confirmed. `latest` says whether
 * this copy is still the newest: an older copy is never sent once a newer one is waiting (the newer one carries it).
 */
export async function saveWithRetry(
  send: () => Promise<unknown>,
  latest: () => boolean,
  waits: number[] = SAVE_WAITS_MS,
  sleep: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms)),
): Promise<{ outcome: SaveOutcome; tries: number }> {
  let tries = 0;
  for (let i = 0; i <= waits.length; i++) {
    if (i > 0) {
      await sleep(waits[i - 1]);
      if (!latest()) return { outcome: "superseded", tries };
    }
    tries++;
    let ok: unknown;
    try {
      ok = await send();
    } catch {
      ok = undefined;
    }
    if (ok) return { outcome: "saved", tries };
  }
  return { outcome: "failed", tries };
}

function hhmm(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toISOString().slice(0, 16).replace("T", " ") + " UTC";
}

/** One line with a mark that is not a colour: ✓ Saved, … Saving, ✕ Not saved. */
export function savedWords(s: SaveStatus | undefined): { mark: string; tone: "ok" | "wait" | "bad"; words: string } {
  if (!s || s.state === "loaded") {
    return { mark: "✓", tone: "ok", words: "Saved: this list is what this item keeps in Fabric." };
  }
  if (s.state === "saving") return { mark: "…", tone: "wait", words: "Saving this list to the item in Fabric…" };
  if (s.state === "saved") return { mark: "✓", tone: "ok", words: `Saved in this item in Fabric (${hhmm(s.at)}).` };
  return {
    mark: "✕", tone: "bad",
    words: `Not saved: Fabric did not confirm the save after ${s.tries} tries (${hhmm(s.at)}). This list is only in this browser tab ` +
      "until Save again works; closing the item loses it.",
  };
}
