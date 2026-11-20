/**
 * WB10 (Gustav's live test in Fabric, 18 Nov 2026, issue #57): every download in the Model editor, made to work inside
 * Fabric's frame.
 *
 * Fabric's iframe sandbox is `allow-same-origin allow-scripts` unless the workload manifest asks for relaxation
 * (Microsoft Learn, "How to relax the iFrame", ms.date 12/15/2025): a `data:` link with `download`, a blob and
 * window.open do nothing there. So, in order:
 *   1. Download: the file goes to the engine (POST /workload/v1/file, fabric_backend/file_links.py), which keeps it ten
 *      minutes and answers a signed, single-use link; the editor asks the Fabric host to open that link in a new tab
 *      (workloadClient.navigation.openBrowserTab), outside the sandbox, and the browser saves the file
 *      (Content-Disposition: attachment). If the host cannot open the tab, the link is shown to open by hand.
 *   2. Copy: the text to the clipboard; where the frame does not allow it, the text is shown, selected, in a text area.
 * Where nothing provides FileContext (a test of one view, the page outside Fabric) the old `data:` link is kept.
 *
 * WB14 (#108): a third action, "Save to lakehouse Files" (onelakeSave.ts), shown only where OneLakeContext is provided:
 * the hosting server's switch is on (KRUSGRAPH_ONELAKE_SAVE) and the item targets a lakehouse. A dry run says the full
 * path first; Save never overwrites (a file already there asks Replace); without storage access it says so plainly and
 * Download keeps working.
 */
import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { Button, Caption1 } from "@fluentui/react-components";
import { ArrowDownload20Regular, Copy20Regular, FolderArrowUp20Regular } from "@fluentui/react-icons";
import { LakehouseTarget, NO_ACCESS, NO_ACCESS_ROLE, SaveIO, SaveOutcome, TIMED_OUT, dryRunWords, saveToOneLake, shownPath } from "./onelakeSave";

export interface OfferedFile {
  filename: string;
  mime: string;
  /** the file as text, or */
  text?: string;
  /** the file's bytes as base64 (a zip) */
  base64?: string;
}

export interface FileLink {
  path: string;
  expires_in: number;
  filename: string;
}

export interface FileSource {
  /** POST /workload/v1/file: the file kept briefly, a signed single-use path answered */
  offer: (file: OfferedFile) => Promise<FileLink>;
  /** the host opens the URL in a new browser tab (workloadClient.navigation.openBrowserTab) */
  open: (url: string) => Promise<void>;
  /** the engine's base URL, for an absolute link */
  base: string;
}

export const FileContext = createContext<FileSource | undefined>(undefined);

/** WB14: where "Save to lakehouse Files" writes, and how it gets its Storage token. Absent: the button is not shown. */
export interface OneLakeSaveSource extends SaveIO {
  target: LakehouseTarget;
}

export const OneLakeContext = createContext<OneLakeSaveSource | undefined>(undefined);

/** The old link, for a page without FileContext. */
export function dataHref(file: OfferedFile): string {
  return file.base64 !== undefined
    ? `data:${file.mime};base64,${file.base64}`
    : `data:${file.mime};charset=utf-8,${encodeURIComponent(file.text ?? "")}`;
}

export function absolute(path: string, base: string): string {
  return new URL(path, base || (typeof window === "undefined" ? "http://localhost" : window.location.origin)).href;
}

export const OPENED = (name: string, minutes: number) =>
  `Opened ${name} in a new tab: your browser saves it there. The link works once, for ${minutes} minutes.`;
export const NOT_OPENED = "Fabric did not open the new tab. Open the link below (it works once, for 10 minutes), or copy the text instead.";
export const NO_CLIPBOARD = "This page may not use the clipboard here: the text is selected below, so copy it with Ctrl+C (⌘C on a Mac).";

/** Copy with a fallback a person can always use: the text, shown and selected. */
export function CopyText(props: { text: string; label?: string; appearance?: "secondary" | "subtle" }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const area = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (state === "failed" && area.current) {
      area.current.focus();
      area.current.select();
    }
  }, [state]);
  const copy = async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("no clipboard");
      await navigator.clipboard.writeText(props.text);
      setState("copied");
    } catch {
      setState("failed");
    }
  };
  return (
    <>
      <Button appearance={props.appearance ?? "subtle"} icon={<Copy20Regular />} onClick={(): void => void copy()}>
        {state === "copied" ? "Copied" : props.label ?? "Copy"}
      </Button>
      {state === "failed" && (
        <span className="kg-file-fallback">
          <Caption1 role="status">{NO_CLIPBOARD}</Caption1>
          <textarea ref={area} readOnly value={props.text} rows={8} aria-label="The text to copy" className="kg-file-text" />
        </span>
      )}
    </>
  );
}

/**
 * A Download button (and, for text, Copy) for one file. `file` may be a function, for a file that is made on the click
 * (the draw.io file). `copy` false leaves Copy out (a zip, or a card that has its own Copy).
 */
export function FileActions(props: {
  file: OfferedFile | (() => Promise<OfferedFile>);
  label: string;
  copy?: boolean;
  copyLabel?: string;
  appearance?: "primary" | "secondary" | "subtle";
  ariaLabel?: string;
}) {
  const source = useContext(FileContext);
  const [state, setState] = useState<{ busy?: boolean; said?: string; link?: string; problem?: string; file?: OfferedFile }>({});
  const fixed = typeof props.file === "function" ? undefined : props.file;
  const shown = fixed ?? state.file;
  const textOf = shown?.base64 === undefined ? shown?.text : undefined;
  const download = async () => {
    setState((s) => ({ ...s, busy: true, said: undefined, problem: undefined, link: undefined }));
    let file: OfferedFile;
    try {
      file = typeof props.file === "function" ? await props.file() : props.file;
    } catch (e) {
      setState({ problem: (e as Error)?.message || "The file could not be made just now. Nothing changed; try again." });
      return;
    }
    if (!source) {
      setState({ file, link: dataHref(file) });
      return;
    }
    let url: string;
    try {
      const got = await source.offer(file);
      url = absolute(got.path, source.base);
    } catch {
      setState({ file, problem: "The Krusgraph engine could not prepare the download just now. Nothing changed; try again, or copy the text." });
      return;
    }
    try {
      await source.open(url);
      setState({ file, said: OPENED(file.filename, 10) });
    } catch {
      setState({ file, link: url, problem: NOT_OPENED });
    }
  };
  return (
    <span className="kg-file" data-file={shown?.filename ?? ""}>
      <Button appearance={props.appearance ?? "secondary"} icon={<ArrowDownload20Regular />} disabled={state.busy}
        onClick={(): void => void download()} aria-label={props.ariaLabel ?? props.label}>
        {state.busy ? "Preparing the file…" : props.label}
      </Button>
      {props.copy !== false && fixed && textOf !== undefined && <CopyText text={textOf} label={props.copyLabel} />}
      <SaveToLakehouse file={props.file} />
      {(state.said || state.problem) && <Caption1 role="status" className="kg-file-said">{state.problem ?? state.said}</Caption1>}
      {state.link && shown && (
        source
          ? <a href={state.link} target="_blank" rel="noopener noreferrer" className="kg-file-link">Open the download of {shown.filename}</a>
          : <a href={state.link} download={shown.filename} className="kg-file-link">Save {shown.filename}</a>
      )}
      {props.copy !== false && !fixed && state.file && textOf !== undefined && state.problem && (
        <CopyText text={textOf} label={props.copyLabel ?? "Copy the file's text"} />
      )}
    </span>
  );
}

export const SAVED = (where: string) => `Saved to ${where}. Download still works the same way.`;
export const EXISTS = (name: string, where: string) =>
  `A file named ${name} is already in ${where}. Nothing was written. Replace it with this one?`;

/**
 * WB14: "Save to lakehouse Files". The first click is the dry run (the full path, the size, nothing written); Save
 * writes; a file already there is replaced only after Replace.
 */
export function SaveToLakehouse(props: { file: OfferedFile | (() => Promise<OfferedFile>) }) {
  const source = useContext(OneLakeContext);
  const [state, setState] = useState<{ step: "idle" | "dry" | "busy" | "exists" | "done"; file?: OfferedFile; said?: string; problem?: string }>({ step: "idle" });
  if (!source) return null;
  const dry = async () => {
    setState({ step: "busy" });
    try {
      const file = typeof props.file === "function" ? await props.file() : props.file;
      setState({ step: "dry", file, said: dryRunWords(source.target, file) });
    } catch (e) {
      setState({ step: "idle", problem: (e as Error)?.message || "The file could not be made just now. Nothing changed; try again." });
    }
  };
  const save = async (file: OfferedFile, replace: boolean) => {
    setState({ step: "busy", file });
    const out: SaveOutcome = await saveToOneLake(source, source.target, file, { replace });
    const where = shownPath(source.target, file.filename);
    if (out.kind === "saved") setState({ step: "done", file, said: SAVED(where) });
    else if (out.kind === "exists") {
      const folder = where.slice(0, where.lastIndexOf("/") + 1);
      setState({ step: "exists", file, said: EXISTS(file.filename, folder) });
    } else if (out.kind === "no_access") setState({ step: "idle", file, problem: out.status ? `${NO_ACCESS} ${NO_ACCESS_ROLE}` : NO_ACCESS });
    else if (out.kind === "timeout") setState({ step: "idle", file, problem: TIMED_OUT });
    else setState({ step: "idle", file, problem: `OneLake did not save the file${out.status ? ` (HTTP ${out.status})` : ""}. Nothing was replaced; use Download instead, or try again.` });
  };
  const f = state.file;
  return (
    <span className="kg-file-save">
      {(state.said || state.problem) && <Caption1 block role="status" className="kg-file-said">{state.problem ?? state.said}</Caption1>}
      {(state.step === "idle" || state.step === "done") && (
        <Button appearance="subtle" icon={<FolderArrowUp20Regular />} onClick={(): void => void dry()}>Save to lakehouse Files</Button>
      )}
      {state.step === "busy" && <Button appearance="subtle" disabled icon={<FolderArrowUp20Regular />}>Saving to the lakehouse…</Button>}
      {state.step === "dry" && f && (
        <>
          <Button appearance="primary" onClick={(): void => void save(f, false)}>Save</Button>
          <Button appearance="subtle" onClick={(): void => setState({ step: "idle" })}>Cancel</Button>
        </>
      )}
      {state.step === "exists" && f && (
        <>
          <Button appearance="primary" onClick={(): void => void save(f, true)}>Replace</Button>
          <Button appearance="subtle" onClick={(): void => setState({ step: "idle", said: `${f.filename} was left as it is.` })}>Keep the file there</Button>
        </>
      )}
    </span>
  );
}

/** A link to a page outside Fabric (Microsoft Learn): opened by the host, since the frame may not open tabs itself. */
export function OutLink(props: { url: string; children: React.ReactNode; className?: string }) {
  const source = useContext(FileContext);
  return (
    <a href={props.url} target="_blank" rel="noopener noreferrer" className={props.className}
      onClick={(e) => {
        if (!source) return;
        e.preventDefault();
        void source.open(props.url).catch(() => window.open(props.url, "_blank", "noopener"));
      }}>
      {props.children}
    </a>
  );
}
