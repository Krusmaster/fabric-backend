/**
 * W3: the happy mascot line at a milestone (cheer.ts), one per milestone per Create, only with "Mascots: on". The editor
 * provides CheerContext (the toggle, this Create's id, what outputs.json says was cheered, and where to record a new
 * cheer); without it (a test, a page outside the editor) the line is drawn with the mascots on and nothing recorded.
 */
import React, { createContext, useContext, useEffect, useId } from "react";
import { MASCOT_CSS } from "./cardMap.generated";
import { CheerBook, CheeredRecord, Milestone } from "./cheer";
import { MascotSays } from "./mascotFigure";

export interface CheerSource {
  on: boolean;
  /** this Create's id (outputs.json create_run.id), or "item" when the item has none */
  create: string;
  /** outputs.json `cheered` as read */
  before?: CheeredRecord;
  book: CheerBook;
  /** records the milestone in outputs.json, so it does not cheer again in this Create */
  record?: (m: Milestone) => void;
}

export const CheerContext = createContext<CheerSource | undefined>(undefined);

/** Whether the milestone's line is drawn here: the mascots on, and this component (its place and its own React id, so the
 * same card drawn twice cheers once) the first to claim it in this Create. */
export function useCheer(m: Milestone, place: string, text: string | undefined): boolean {
  const src = useContext(CheerContext);
  const here = `${place}#${useId()}`;
  const shown = !!text && (src ? src.on && src.book.claim(m, src.create, here, src.before) : true);
  const record = src?.record;
  useEffect(() => {
    if (shown && record) record(m);
  }, [shown, record, m]);
  return shown;
}

/** Onto, celebrating, with one line. Nothing when the mascots are off or the milestone has cheered already. */
export function CheerLine(props: { milestone: Milestone; place: string; text?: string }) {
  const shown = useCheer(props.milestone, props.place, props.text);
  if (!shown) return null;
  return (
    <ul className="krusgraph-mascots krusgraph-cheer" data-w3-cheer={props.milestone}>
      <style>{MASCOT_CSS}</style>
      <MascotSays kind="onto" text={props.text} pose="celebrate" glad />
    </ul>
  );
}
