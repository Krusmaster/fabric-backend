/**
 * n223: what the editor says while it waits, in one place (OntoWait.tsx draws it). Pure functions, no React, so the
 * lines at 0, 10 and 30 seconds are unit-tested for every kind of wait (waitWords.test.ts).
 *
 * The kind is what the code is actually waiting on, never a guess:
 *   starting  nothing known yet: the request has not been answered (the engine may be starting, the network slow)
 *   item      Fabric's own item API (the item and its saved definition, read through the Fabric host)
 *   sql       the engine said the step is running, and the step only reads the source's SQL analytics endpoint
 *             (review, check, schemas)
 *   capacity  the engine said Fabric answered 429: the capacity is throttled and the step is tried again by itself
 *   fabric    the engine said Fabric is still running one of its long-running operations for this step
 *   network   the last reads of the step's state did not get through (a phone asleep, a network change)
 *   engine    the engine is working on a step that is neither only SQL nor a known Fabric wait (a dry run, the Data
 *             product's reads): we know it is running, not what inside it is slow
 * Unknown slowness is "Still working on it": nothing is blamed without a signal for it.
 */

export type WaitKind = "starting" | "item" | "sql" | "capacity" | "fabric" | "network" | "engine";

/** after this many seconds Onto adds one honest line about what is slow */
export const SLOW_AFTER_S = 10;
/** after this many seconds Onto offers what the person can do: keep waiting, see the steps so far, cancel safely */
export const OFFER_AFTER_S = 30;

/** a step with a known number of parts: "3 of 7 tables counted" */
export interface WaitProgress {
  done: number;
  total: number;
  unit: string;
}

/** What the engine client reports while a step runs (engineClient.CallOptions.onWait). */
export interface WaitSignal {
  kind: WaitKind;
  /** the engine's own words for this moment (capacity attempt, the Fabric operation it follows) */
  words?: string;
  progress?: WaitProgress;
}

/** One wait as the editor shows it. */
export interface Wait {
  /** the step's name: "Reading the tables in shop…" */
  label: string;
  kind: WaitKind;
  /** Date.now() when the step started */
  startedAt: number;
  /** reading, counting, building: the verb of the SQL line ("I am still counting") */
  doing?: "reading" | "counting" | "building" | "opening";
  progress?: WaitProgress;
  words?: string;
  /** what has happened so far, oldest first, each with its second ("Show the steps so far") */
  steps: { at: number; text: string }[];
  /** the step only reads: stopping it changes nothing in Fabric (the editor stops waiting and forgets the answer) */
  cancellable?: boolean;
  /** the step goes on without the editor (a Create): reopening the item shows where it is */
  leaveSafe?: boolean;
}

export interface WaitLines {
  label: string;
  /** "3 of 7 tables counted" */
  progress?: string;
  /** the engine's own words, when it gave some */
  words?: string;
  /** from SLOW_AFTER_S: what is slow, or "Still working on it." */
  slow?: string;
  /** from OFFER_AFTER_S: what the person can do */
  offer?: string;
  canCancel: boolean;
  canSeeSteps: boolean;
  seconds: number;
}

export function progressWords(p?: WaitProgress): string | undefined {
  if (!p || !(p.total > 0)) return undefined;
  const done = Math.max(0, Math.min(p.done, p.total));
  return `${done} of ${p.total} ${p.unit}`;
}

/** The line Onto adds after SLOW_AFTER_S, chosen from what the code waits on. */
export function slowLine(kind: WaitKind, doing: Wait["doing"] = "reading"): string {
  switch (kind) {
    case "sql":
      return `Fabric's SQL endpoint is taking its time today; I am still ${doing === "counting" ? "counting" : "reading"}.`;
    case "capacity":
      return "Your Fabric capacity is busy; this can take a minute. I try again by myself, and nothing fails because of it.";
    case "fabric":
      return "Fabric is still finishing its part of this step; I am following its operation.";
    case "item":
      return "Fabric is taking its time to hand over this item's saved state; I am still asking.";
    case "network":
      return "The last few reads did not get through; I keep asking. Nothing is lost.";
    case "engine":
    case "starting":
    default:
      return "Still working on it.";
  }
}

/** The offer after OFFER_AFTER_S: keep waiting always; the steps when there are some; cancel only when it is safe. */
export function offerLine(w: Pick<Wait, "cancellable" | "leaveSafe">, hasSteps: boolean): string {
  const steps = hasSteps ? ", see the steps done so far" : "";
  if (w.cancellable) return `You can keep waiting${steps}, or cancel: this step only reads, so nothing in Fabric changes.`;
  if (w.leaveSafe) return `You can keep waiting${steps}, or close the item: this step goes on, and reopening the item shows where it is.`;
  return `You can keep waiting${steps ? ` or${steps.slice(1)}` : ""}.`;
}

export function waitLines(w: Wait, now: number): WaitLines {
  const seconds = Math.max(0, Math.floor((now - w.startedAt) / 1000));
  const canSeeSteps = w.steps.length > 0;
  return {
    label: w.label,
    progress: progressWords(w.progress),
    words: w.words,
    slow: seconds >= SLOW_AFTER_S ? slowLine(w.kind, w.doing) : undefined,
    offer: seconds >= OFFER_AFTER_S ? offerLine(w, canSeeSteps) : undefined,
    canCancel: !!w.cancellable && seconds >= OFFER_AFTER_S,
    canSeeSteps: canSeeSteps && seconds >= OFFER_AFTER_S,
    seconds,
  };
}

/** A wait's next state after a signal from the engine client: its kind, words and progress, and a step when they say
 * something new. */
export function withSignal(w: Wait, s: WaitSignal, now: number): Wait {
  const text = s.words || progressWords(s.progress) || KIND_STEP[s.kind];
  const last = w.steps[w.steps.length - 1]?.text;
  const steps = text && text !== last ? [...w.steps, { at: Math.max(0, Math.round((now - w.startedAt) / 1000)), text }] : w.steps;
  return { ...w, kind: s.kind, words: s.words, progress: s.progress ?? w.progress, steps };
}

/** the step a kind adds to "the steps so far" when the engine gave no words */
const KIND_STEP: Partial<Record<WaitKind, string>> = {
  sql: "The engine is reading the SQL analytics endpoint.",
  engine: "The engine is working on the step.",
  capacity: "Fabric answered 429 (capacity busy); the step waits and tries again.",
  fabric: "Fabric is running its long-running operation.",
  network: "A read of the step's state did not get through; asking again.",
};

export function newWait(label: string, now: number, extra: Partial<Omit<Wait, "label" | "startedAt">> = {}): Wait {
  return { kind: "starting", steps: [{ at: 0, text: "Sent to the Krusgraph engine." }], ...extra, label, startedAt: now };
}

/** The review's and the check's step names, with the schema: "Reading the tables in shop…". */
export function reviewLabel(schema?: string): string {
  return schema ? `Reading the tables in ${schema} and finding keys and links…` : "Reading the lakehouse and finding keys and links…";
}

export function checkLabel(schema?: string): string {
  return schema ? `Counting the rows in ${schema}: is each key unique, does each link find its table…`
    : "Counting the rows: is each key unique, does each link find its table…";
}
