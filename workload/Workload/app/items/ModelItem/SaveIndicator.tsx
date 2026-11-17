/**
 * W14: one line at the top of every view that says whether the item is saved: Saving…, Saved 14:05 UTC, or Not saved with
 * Save again. A mark that is not only a colour, a live region (role="status") so a screen reader hears the change, and
 * one more line when changes were recovered from this browser or merged with another session's save (autosave.ts).
 */
import React from "react";
import { AutosaveState, indicatorWords } from "./autosave";

export interface SaveIndicatorProps {
  state: AutosaveState;
  at?: string;
  tries?: number;
  /** a recovered draft or a merge with another session's save, in words (autosave.recoveredWords, conflictWords) */
  note?: string;
  onSaveAgain?: () => void;
  onDismissNote?: () => void;
}

export function SaveIndicator(props: SaveIndicatorProps) {
  const w = indicatorWords(props.state, props.at, props.tries);
  return (
    <div className="kg-autosave" data-autosave={props.state}>
      <p className={`kg-autosave-line kg-autosave-${w.tone}`} role="status" aria-live="polite">
        <span className="kg-autosave-mark" aria-hidden="true">{w.mark}</span> <span>{w.words}</span>
        {props.state === "failed" && props.onSaveAgain ? (
          <button type="button" className="kg-autosave-again" onClick={props.onSaveAgain}>Save again</button>
        ) : null}
      </p>
      {props.note ? (
        <p className="kg-autosave-note" role="alert">
          <span>{props.note}</span>
          {props.onDismissNote ? (
            <button type="button" className="kg-autosave-again" onClick={props.onDismissNote} aria-label="Dismiss this note">OK</button>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}
