/**
 * The Krusgraph Model item editor (renamed and rewritten from the starter kit's HelloWorldItemEditor.tsx,
 * microsoft/fabric-extensibility-toolkit commit dacab1b, MIT, Copyright (c) Microsoft Corporation).
 *
 * Inside Fabric's frame: one ribbon whose first tab is Home, Fluent UI, and the item is only ever created through
 * Fabric's own create dialog (createItemDialogConfig in the manifest); this editor opens on an item that exists.
 * Views: empty state (choose a lakehouse) -> review -> choose outputs -> preview (dry run) -> result.
 * Re-opening an item re-plans with the saved review.json as `previous`, so decisions carry over.
 *
 * n173: in the review, Check against the rows (/workload/v1/check) writes each item's check into the review file; the
 * map (the MCP Apps cards' drawing) and the list show passed, failed and not checked; Accept all and Accept all that
 * passed the check; Thinker's questions answered inline (a key for a keyless table, the table a column points to, or
 * keep it as it is). The ribbon stays one sticky ribbon with Home first.
 *
 * n174: Choose what to build offers every output the MCP tools build (buildWords.KINDS); Preview is one dry run per
 * output (/workload/v1/build with outputs [{kind, name}]), with the data flow drawn and the data product; Create builds
 * them in order and keeps the created ids and the product in outputs.json. Re-opened, the item shows its product and
 * offers Update where the output's tool updates in place, a new name where it does not (a report).
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { NotificationType } from "@ms-fabric/workload-client";
import {
  ArrowClockwise24Regular,
  ArrowLeft24Regular,
  ArrowRight24Regular,
  BoxMultiple24Regular,
  CheckmarkStarburst24Regular,
  Database24Regular,
  Play24Regular,
} from "@fluentui/react-icons";
import { PageProps, ContextProps } from "../../App";
import { callGetItem, callGetItemDefinition, callUpdateItemDefinition } from "../../controller/ItemCRUDController";
import { callDatahubOpen } from "../../controller/DataHubController";
import { callNotificationOpen } from "../../controller/NotificationController";
import { navigateToItem } from "../../controller/NavigationController";
import { ItemEditor, Ribbon, RibbonAction, createSaveAction } from "../../components/ItemEditor";
import * as engine from "./engineClient";
import { lastCreateOf, readLastCreate, withCard } from "./createWords";
import { rememberWorkloadOf } from "../../controller/ConfigurationController";
import {
  DefinitionError,
  ModelDefinition,
  ModelView,
  OutputChoice,
  ReviewStatus,
  decide,
  emptyDefinition,
  fromParts,
  toParts,
} from "./ModelItemDefinition";
import {
  OpenLink, afterCreate, choicesFor, createEach, createLabel, failedCard, mergeCreated, pendingCard, requestFor, runUpdate, schemaToUse,
  toRequests,
} from "./buildWords";
import {
  CreateRunRecord, Known, heldCard, knownOf, markEarlier, namesWithOneSuffix, newCreateId, readRun, settlePending, startRun, stoppedCard,
  inOrder, waitsForRun, withOperation, withPending, withProgress,
} from "./createRun";
import { PREPARING, Ticked, chosenProducts, ticked } from "./productSuggestions";
import { SuggestedProductsPanel } from "./SuggestedProductsView";
import { Busy, EmptyView, ErrorBar, OutputsView, PreviewView, ResultView, ReviewView } from "./ModelItemViews";
import { MapData } from "./cardMap";
import { Choice, acceptAll, totalsOf } from "./modelWords";
import { notCheckedLine } from "./ed1Words";
import { Blocker, freshestReview, staleLine, toFinish } from "./ed2Create";
import { readAppRecord, rememberApp, withAppChoices } from "./appWords";
import {
  MAX_WAIT_MS, POLL_MS, agentAfterRun, jobsBlocked, pipelineItem, recordRun, recordSchedule, runFinished, scheduleIds, stillRunning,
} from "./jobsWords";
import { AppChoices } from "./engineClient";
import { PICKER_TYPES, ReadOnlySource, SapOffer, restType, targetProblem } from "./sourceWords";
import { BuildIn, buildWorkspace, crossWorkspace, keptTarget, lakehouseProblem, productWorkspace, targetRequest } from "./buildPlace";
import { autoAdopt } from "./ed3Product";
import { DataProductPage, preloadParts } from "./lazyParts";   // n223: the Data product page loads when first shown
import { OntoWait } from "./OntoWait";
import { FlowSteps } from "./FlowSteps";
import { flowSteps } from "./stepWords";
import { AnalysisContext, AnalysisSource, NextStepsPanel, StarterAnswer, StarterContext, StarterSource } from "./NextStepsView";
import type { AnalysisAnswer } from "./analysisPlan";
import { Wait, WaitSignal, checkLabel, newWait, reviewLabel, withSignal } from "./waitWords";
import { accessLine } from "./accessWords";
import { DrawioContext, DrawioFile, DrawioSource } from "./drawioDownload";
import { VerifyAnswer, VerifyContext, VerifySource } from "./verifyBuilt";
import { CatalogContext, CatalogPanel, CatalogSource } from "./CatalogPanel";
import { FileContext, FileLink, FileSource, OneLakeContext, OneLakeSaveSource } from "./fileOffer";
import { STORAGE_SCOPE, saveEnabled } from "./onelakeSave";
import type { CatalogAnswer } from "./catalogWords";
import {
  LeftoversAnswer, OutOfDate, ProductRow, RetireAnswer, StatusAnswer, createdAtOf, healthFor, outOfDate, planOf, rowsOf, withAdopted, withOwner,
  withPlan, withRemoved,
} from "./productWords";
import { SAVE_WAITS_MS, SaveStatus, saveWithRetry } from "./saveState";
// W14: autosave (autosave.ts, SaveIndicator.tsx)
import {
  AUTOSAVE_DELAY_MS, AUTOSAVE_WAITS_MS, AutosaveState, Decisions, Recovery, browserStore, clearDraft, conflictWords, decisionsOf, newSession,
  readDraft, recover, recoveredWords, resolve, revisionOf, stamp, writeDraft,
} from "./autosave";
import { SaveIndicator } from "./SaveIndicator";
import { CreatedItem, ItemCache, RemovedItem, ReviewFile } from "./ModelItemDefinition";

const VIEWS: ModelView[] = ["empty", "review", "outputs", "preview", "result", "product"];
const EMPTY_RESULT = { dry_run: false, order: [], left_out_by_review: [], refused: 0, note: "", outputs: [] } as unknown as engine.ManyAnswer;
const NOTHING_KNOWN: Known = { answers: {}, running: {}, progress: {} };
/** n197: what a reopened item says, in one line, when Fabric or the engine is too busy to answer */
export const BUSY_LINE = "Fabric is busy, try again in a few minutes.";

/** n197: an answer that means "busy" (throttled capacity, no answer, a network that did not get through). */
export function isBusy(e: unknown): boolean {
  const kind = e instanceof engine.EngineCallError ? e.answer.kind : "";
  const text = e instanceof engine.EngineCallError ? `${e.answer.error} ${e.status}` : String((e as Error)?.message ?? e);
  return ["throttled", "rate_limited", "no_answer", "fabric_unavailable", "timeout"].includes(kind) || /429|throttl|busy|capacity|fetch|timeout|503/i.test(text);
}

/** n223: run fn when the browser is idle (or soon), after the first paint. */
function idle(fn: () => void): void {
  const w = typeof window === "undefined" ? undefined : (window as unknown as { requestIdleCallback?: (f: () => void, o?: object) => void });
  if (w?.requestIdleCallback) w.requestIdleCallback(fn, { timeout: 3000 });
  else setTimeout(fn, 1500);
}

/** n223: the schema list kept in the item for this source, if any (shown at once, then read again). */
export function cachedSchemas(d: ModelDefinition, itemId = d.source?.itemId): engine.SchemasAnswer | undefined {
  const c = d.item.cache?.schemas;
  return c && itemId && c.source === itemId && Array.isArray(c.list?.schemas) ? c.list : undefined;
}

export function ModelItemEditor(props: PageProps) {
  const { workloadClient } = props;
  const { itemObjectId } = useParams<ContextProps>();

  const [isLoading, setIsLoading] = useState(true);
  /** n223: the step the editor waits for (OntoWait: Onto, the step, the slow line after 10 s, the offer after 30 s) */
  const [wait, setWait] = useState<Wait>();
  const busy = wait?.label;
  const stopRef = useRef<AbortController>();
  /** n223: a review read again while the saved one is shown (reopening an item): one line above the review */
  const [quiet, setQuiet] = useState<Wait>();
  /** n223: decisions made while that review is read again, applied again to its answer */
  const whileQuiet = useRef<((r: ReviewFile) => ReviewFile)[] | undefined>(undefined);
  /** n223: the item and its definition being read (the first load) */
  const [opening, setOpening] = useState<Wait>(() => newWait("Opening the model…", Date.now(),
    { kind: "item", doing: "opening", steps: [{ at: 0, text: "Asked Fabric for the item and its saved definition." }] }));
  const [error, setError] = useState<engine.EngineError>();
  const [trialLine, setTrialLine] = useState<string>("");   // n213: the trial's days left, one quiet line
  const [itemMeta, setItemMeta] = useState<{ id: string; workspaceId: string; displayName: string }>();
  const [def, setDef] = useState<ModelDefinition>(emptyDefinition());
  const [dirty, setDirty] = useState(false);
  const [schema, setSchema] = useState("dbo");
  /** n179: the lakehouse's schemas, listed after Choose lakehouse; the schema is picked, never typed */
  const [schemaList, setSchemaList] = useState<{ loading: boolean; list?: engine.SchemasAnswer; error?: engine.EngineError; wait?: Wait }>({ loading: false });
  const [choices, setChoices] = useState<OutputChoice[]>([]);
  const choicesRef = useRef(choices);
  choicesRef.current = choices;
  const [product, setProduct] = useState<{ on: boolean; name: string }>({ on: false, name: "" });
  const productRef = useRef(product);
  productRef.current = product;
  /** ED2: the review the item was opened with (review.json), to say once when the dry run used a newer one */
  const savedReview = useRef<ModelDefinition["review"]>();
  const [staleNote, setStaleNote] = useState<string>();
  const [map, setMap] = useState<MapData>();
  const [mascotsOn, setMascotsOn] = useState(true);
  const [preview, setPreview] = useState<engine.ManyAnswer>();
  const [result, setResult] = useState<engine.ManyAnswer>();
  const [updating, setUpdating] = useState(false);
  /** n197: a Create (or its follow-up) is going on: Create is not offered twice */
  const [creating, setCreating] = useState(false);
  const [suggested, setSuggested] = useState<engine.SuggestedProducts | null | undefined>(undefined);   // n222
  /** n197: one line on the result when the saved state or the engine could not be read */
  const [notice, setNotice] = useState<string>();
  /** n201: what the last review said about the source: read-only (where the build writes) and the SAP pack's items */
  const [sourceInfo, setSourceInfo] = useState<{ readOnly?: ReadOnlySource; sap?: SapOffer }>({});
  const [setView, setSetView] = useState<(v: string) => void>();
  /** n198: the Data product page's state (productWords.ts, DataProductView.tsx) */
  const [dp, setDp] = useState<{ status?: StatusAnswer; health?: string; updates?: OutOfDate[]; retire?: RetireAnswer;
    leftovers?: LeftoversAnswer; busy?: string; problem?: string; wait?: Wait; adopted?: string[] }>({});
  const view = def.item.view;

  const go = (v: ModelView) => {
    setDef((d) => ({ ...d, item: { ...d.item, view: v } }));
    setView?.(v);
    // n223: the schemas are listed when Choose source is shown, once per opening (not on every reopen)
    const s = defRef.current.source;
    if (v === "empty" && s && listedFor.current !== s.itemId) void listSchemas(s.workspaceId, s.itemId, s.displayName, s.schema, cachedSchemas(defRef.current));
  };
  /** n223: the source whose schemas were listed in this opening of the item */
  const listedFor = useRef<string>();

  const sourceRequest = (d: ModelDefinition): engine.SourceRequest => ({
    workspace: d.source.workspaceId,
    source: d.source.itemId,
    source_name: d.source.displayName,
    schema: d.source.schema,
    // n201: a read-only source's build writes to the chosen lakehouse, or the workspace's first (null). n221: the build's
    // workspace (this item's by default, buildPlace.ts) and the lakehouse there; review and check ignore it
    target: targetRequest(d.source, metaRef.current?.workspaceId, productRef.current.name.trim() || metaRef.current?.displayName),
  });

  /** n201: the source's real item type (the picker may name it otherwise) and what the review says about it. */
  const withKind = (d: ModelDefinition, a: engine.ReviewAnswer): ModelDefinition => {
    setSourceInfo({ readOnly: a.read_only, sap: a.sap });
    return a.source_kind && d.source && d.source.itemType !== a.source_kind ? { ...d, source: { ...d.source, itemType: a.source_kind } } : d;
  };

  /** n223: a wait's handle: the options the engine call reports to (what it waits on) and the Cancel it may offer. */
  function waitHandle(started: number, set: (fn: (w: Wait | undefined) => Wait | undefined) => void): { opts: engine.CallOptions; stop: AbortController } {
    const stop = new AbortController();
    const onWait = (sig: WaitSignal) => set((w) => (w && w.startedAt === started ? withSignal(w, sig, Date.now()) : w));
    return { opts: { signal: stop.signal, onWait }, stop };
  }

  const wasCancelled = (e: unknown) => e instanceof engine.EngineCallError && e.answer.kind === "cancelled";

  async function runEngine<T>(label: string, fn: (o: engine.CallOptions) => Promise<T>, how: Partial<Wait> = {}): Promise<T | undefined> {
    const started = Date.now();
    const { opts, stop } = waitHandle(started, setWait);
    stopRef.current = stop;
    setWait(newWait(label, started, how));
    setError(undefined);
    try {
      return await fn(opts);
    } catch (e) {
      if (!wasCancelled(e)) setError(e instanceof engine.EngineCallError ? e.answer : { error: String(e?.message ?? e), kind: "unexpected" });
      return undefined;
    } finally {
      if (stopRef.current === stop) stopRef.current = undefined;
      setWait((w) => (w?.startedAt === started ? undefined : w));
    }
  }

  /** n223: Cancel on a read-only step: the editor stops reading its answer; nothing in Fabric changes. */
  function cancelWait() {
    stopRef.current?.abort();
    callNotificationOpen(workloadClient, "Cancelled", "Stopped waiting. Nothing in Fabric changed.");
  }

  /** n175: the source with the schema as the lakehouse spells it, and a notification that says which name was used. */
  const exactSchema = (d: ModelDefinition, used?: engine.SchemaUsed): ModelDefinition =>
    !used || !d.source || d.source.schema === used.used ? d : { ...d, source: { ...d.source, schema: used.used } };

  function announceSchema(used?: engine.SchemaUsed) {
    if (!used) return;
    setSchema(used.used);
    callNotificationOpen(workloadClient, "Schema name", used.note);
  }

  /** SM3: `check` (Find keys and relationships, Read the lakehouse again): the check against the rows runs on its own
   * right after, as the chat's Check step does; it only reads. */
  async function plan(d: ModelDefinition, corrections: engine.Corrections = {}, check = false) {
    const a = await runEngine(reviewLabel(d.source?.schema), (o) =>
      engine.review(workloadClient, sourceRequest(d), d.review, corrections, o), { doing: "reading", cancellable: true }
    );
    if (!a) return;
    setMap(a.map);
    setSuggested(a.suggested_products);                       // n222
    d = withKind(exactSchema(d, a.schema_used), a);
    announceSchema(a.schema_used);
    const next = { ...d, review: a.review, item: withCache({ ...d.item, view: "review" }, { map: a.map }) };
    setDef(next);
    setDirty(true);
    setView?.("review");
    if (check && a.review) await checkRows(next);
  }

  /** n197: the review read again in the background on reopening an item that has outputs; the result stays in view.
   * A busy Fabric is one line, never a page without its flow. */
  async function replanQuietly(d: ModelDefinition) {
    try {
      const a = await engine.review(workloadClient, sourceRequest(d), d.review, {});
      setMap(a.map);
      setSuggested(a.suggested_products);                     // n222
      // ED2: a re-read of the saved review never replaces a check the person ran meanwhile (the fresher one stays)
      setDef((x) => ({ ...withKind(exactSchema(x, a.schema_used), a), review: freshestReview(x.review, a.review).review, item: withCache(x.item, { map: a.map }) }));
    } catch (e) {
      if (isBusy(e)) setNotice(BUSY_LINE);
    }
  }

  /** n223: reopening an item with a review: the saved review (and the map kept with it) shows at once, and the review is
   * read again behind it, as before n223 but without a page that only spins. A decision made meanwhile is applied
   * again to the new answer, so nothing chosen during the wait is lost. */
  async function replanOnOpen(d: ModelDefinition) {
    const started = Date.now();
    const { opts } = waitHandle(started, setQuiet);
    setQuiet(newWait(`${reviewLabel(d.source?.schema).replace(/…$/, "")} again; the saved review is shown meanwhile…`, started, { doing: "reading" }));
    whileQuiet.current = [];
    try {
      const a = await engine.review(workloadClient, sourceRequest(d), d.review, {}, opts);
      const again = whileQuiet.current ?? [];
      setMap(a.map);
      setSuggested(a.suggested_products);                     // n222
      announceSchema(a.schema_used);
      setDef((x) => {
        let review = a.review;
        for (const fn of again) {
          try { review = fn(review); } catch { /* an item the new review no longer has */ }
        }
        review = freshestReview(x.review, review).review!;   // ED2: never older than a check run during the wait
        return { ...withKind(exactSchema(x, a.schema_used), a), review, item: withCache(x.item, { map: a.map }) };
      });
      if (!again.length) setDirty(false);
    } catch (e) {
      if (isBusy(e)) setNotice(BUSY_LINE);
      else setError(e instanceof engine.EngineCallError ? e.answer : { error: String((e as Error)?.message ?? e), kind: "unexpected" });
    } finally {
      whileQuiet.current = undefined;
      setQuiet(undefined);
    }
  }

  /** n223: what the item keeps for an instant first paint (item.json cache): the last map and the schema list. */
  const withCache = (item: ModelDefinition["item"], patch: Partial<ItemCache>): ModelDefinition["item"] =>
    ({ ...item, cache: { ...(item.cache ?? {}), ...patch } });

  // ---------------------------------------------------------------- load
  useEffect(() => {
    (async () => {
      setIsLoading(true);
      void engine.access(workloadClient).then((a) => setTrialLine(accessLine(a)));   // n213: also starts the trial
      // n223: Fabric is slow to hand over the item: Onto says so after 10 s (OntoWait, kind "item")
      const opened = Date.now();
      setOpening(newWait("Opening the model…", opened, { kind: "item", doing: "opening",
        steps: [{ at: 0, text: "Asked Fabric for the item and its saved definition." }] }));
      try {
        // n223: the item and its definition are read at the same time (one waited for the other before)
        const [got, parts] = await Promise.all([callGetItem(workloadClient, itemObjectId), callGetItemDefinition(workloadClient, itemObjectId)]);
        rememberWorkloadOf(got.item.type);   // n176: Org.Krusgraph or Krusgraph.Modeler, for the engine scope
        const inFabric = fromParts(parts?.definition?.parts);
        // W14: the revision and decisions Fabric has are the base of the next autosave; changes this browser kept and
        // Fabric does not have (a reload or a closed tab before the save) are recovered and saved again
        base.current = { rev: revisionOf(inFabric), decisions: decisionsOf(inFabric.review) };
        const rec = recover(readDraft(browserStore(), got.item.id), inFabric);
        recovered.current = rec;
        if (rec) {
          base.current = { ...base.current, rev: rec.baseRev };
          setNote(rec.conflict ? `${recoveredWords(rec)} ${conflictWords(rec.conflict)}` : recoveredWords(rec));
        }
        const loaded = rec ? rec.def : inFabric;
        setItemMeta({ id: got.item.id, workspaceId: got.item.workspaceId, displayName: got.item.displayName });
        // n221: the item's workspace is where the outputs go by default, so every request from now on needs it
        metaRef.current = { id: got.item.id, workspaceId: got.item.workspaceId, displayName: got.item.displayName };
        setDef(loaded);
        savedReview.current = loaded.review;                    // ED2: what the item kept, to compare the dry run's with
        setSchema(loaded.source?.schema ?? "dbo");
        setChoices(choicesFor(loaded.outputs.outputs, loaded.source?.displayName ?? got.item.displayName,
          loaded.source ? { displayName: got.item.displayName, created: loaded.outputs.created } : undefined));
        setProduct({ on: !!loaded.outputs.product, name: loaded.outputs.product?.name ?? got.item.displayName });
        // n197: an item with outputs (or a Create in progress) opens on its result: the summary, the flow and the cards
        const hasResult = loaded.outputs.created.length > 0 || !!readRun(loaded.outputs.create_run);
        // n198: with the last Create finished, the item opens on its data product; a Create still going on stays on its cards
        const lastRun = readRun(loaded.outputs.create_run);
        const landing: ModelView = loaded.outputs.created.length > 0 && (!lastRun || lastRun.finished) ? "product" : "result";
        if (hasResult) {
          defRef.current = { ...loaded, item: { ...loaded.item, view: landing } };
          metaRef.current = { id: got.item.id, workspaceId: got.item.workspaceId, displayName: got.item.displayName };
          setDef(defRef.current);
        }
        if (loaded.item.cache?.map) setMap(loaded.item.cache.map);   // n223: the last map, until the review is read again
        const reviewFirst = !hasResult && !!loaded.source && !!loaded.review;
        if (reviewFirst) setDef({ ...loaded, item: { ...loaded.item, view: "review" } });
        setIsLoading(false);
        idle(preloadParts);   // n223: the map, the data flow and the Data product page, fetched while nothing else is
        // n223: the schema list only where it shows (Choose source); elsewhere the list kept in the item waits for it
        if (loaded.source && !reviewFirst && !hasResult) void listSchemas(loaded.source.workspaceId, loaded.source.itemId, loaded.source.displayName,
          loaded.source.schema, cachedSchemas(loaded));
        else if (loaded.source && cachedSchemas(loaded)) setSchemaList({ loading: false, list: cachedSchemas(loaded) });
        if (hasResult && loaded.source) {
          if (loaded.review) void replanQuietly(loaded);
          if (landing === "product") void loadProduct();
          await reopen(defRef.current, got.item.id);
          setDirty(false);
        } else if (reviewFirst) {
          await replanOnOpen({ ...loaded, item: { ...loaded.item, view: "review" } }); // re-plan with the saved decisions
        }
        if (recovered.current) setDirty(true);   // W14: the recovered changes are saved by the autosave
      } catch (e) {
        // n197: Fabric throttled or failed the read of the item's saved state: one line, not a page without its flow
        const busy = isBusy(e) || /429|throttl|busy|capacity/i.test(String(e?.message ?? e));
        setError({ error: e instanceof DefinitionError ? e.message : busy ? BUSY_LINE : `The item could not be opened: ${e?.message ?? e}. ${BUSY_LINE}`,
          kind: busy ? "fabric_busy" : "definition" });
        setIsLoading(false);
      }
    })();
  }, [itemObjectId]);

  useEffect(() => {
    if (!isLoading && setView) setView(VIEWS.includes(view) ? view : "empty");
  }, [isLoading, setView]);

  // ---------------------------------------------------------------- actions
  async function save(d: ModelDefinition = def) {
    // W14: through persist, so the save carries the next revision, waits for any save on its way and is tried again
    setDirty(false);
    const outcome = await persist(d);
    const ok = outcome === "saved" || outcome === "superseded";
    if (ok) {
      callNotificationOpen(workloadClient, "Saved", `${itemMeta.displayName} was saved.`);
    } else {
      callNotificationOpen(workloadClient, "Not saved", `${itemMeta.displayName} could not be saved.`, NotificationType.Error);
    }
  }

  /** n201: a lakehouse, a warehouse, a SQL database or a mirrored database (SAP via SAP Datasphere among them). */
  async function chooseLakehouse() {
    const picked = await callDatahubOpen(workloadClient, PICKER_TYPES,
      "Choose what Krusgraph should read: a lakehouse, a warehouse, a SQL database or a mirrored database", false);
    if (!picked) return;
    const source = {
      version: 1,
      platform: "fabric" as const,
      workspaceId: picked.workspaceId,
      itemId: picked.id,
      itemType: restType(picked.type) ?? "Lakehouse",
      displayName: picked.displayName,
      schema,
    };
    setSourceInfo({});
    setDef((d) => ({ ...d, source, review: d.source?.itemId === picked.id ? d.review : undefined }));
    setChoices((c) => choicesFor(c.filter((x) => x.enabled), picked.displayName,
      { displayName: def.source?.displayName ?? itemMeta?.displayName, created: def.outputs.created }));
    setDirty(true);
    await listSchemas(picked.workspaceId, picked.id, picked.displayName, undefined, cachedSchemas(def, picked.id));
  }

  /** n201: the lakehouse a read-only source's build writes to: one of the source's workspace. n221: one of the build's
   * workspace when the outputs are built in another workspace than the source's. */
  async function chooseTarget() {
    if (!def.source) return;
    const picked = await callDatahubOpen(workloadClient, ["Lakehouse"],
      "Choose the lakehouse the silver tables, gold views and the pipeline's check are written to", false);
    if (!picked) return;
    const ws = buildWorkspace(def.source, metaRef.current?.workspaceId);
    const problem = crossWorkspace(def.source, metaRef.current?.workspaceId)
      ? lakehouseProblem(ws, { workspaceId: picked.workspaceId, type: restType(picked.type) })
      : targetProblem(def.source.workspaceId, { workspaceId: picked.workspaceId, type: restType(picked.type) });
    if (problem) {
      callNotificationOpen(workloadClient, "Target lakehouse", problem, NotificationType.Error);
      return;
    }
    setDef((d) => (d.source ? { ...d, source: { ...d.source, target: { itemId: picked.id, displayName: picked.displayName, workspaceId: picked.workspaceId } } } : d));
    setDirty(true);
  }

  /** ED1: the report's semantic model, picked from the semantic models in the workspace (no free text) */
  async function pickReportModel() {
    const picked = await callDatahubOpen(workloadClient, ["SemanticModel"], "Choose the semantic model the report is built on", false);
    if (!picked) return;
    setChoices((cs) => cs.map((c) => (c.type === "report" ? { ...c, model: picked.displayName } : c)));
    setDirty(true);
  }

  /** n221: Build in (this item's workspace, the default, or the source's) and the lakehouse Create may make there. */
  function chooseBuildIn(patch: { buildIn?: BuildIn; createLakehouse?: string | null }) {
    setDef((d) => {
      if (!d.source) return d;
      const next = { ...d.source };
      if (patch.buildIn) next.buildIn = patch.buildIn;
      if (patch.createLakehouse === null) delete next.createLakehouse;
      else if (patch.createLakehouse !== undefined) next.createLakehouse = patch.createLakehouse;
      return { ...d, source: next };
    });
    setPreview(undefined);                                       // the last dry run was for the other place
    setDirty(true);
  }

  /** n179: the schemas of the chosen lakehouse with their table counts; the only one with tables is preselected. */
  async function listSchemas(workspaceId: string, itemId: string, displayName: string, saved?: string, cached?: engine.SchemasAnswer) {
    listedFor.current = itemId;
    // n223: a list kept in the item shows at once; the source is read again behind it
    const started = Date.now();
    const { opts } = waitHandle(started, (fn) => setSchemaList((x) => ({ ...x, wait: fn(x.wait) })));
    setSchemaList({ loading: true, list: cached, wait: newWait(`Reading the schemas of ${displayName}…`, started, { doing: "reading" }) });
    try {
      const list = await engine.schemas(workloadClient, { workspace: workspaceId, source: itemId, source_name: displayName }, opts);
      setSchemaList({ loading: false, list });
      setDef((d) => (d.source?.itemId === itemId ? { ...d, item: withCache(d.item, { schemas: { source: itemId, list } }) } : d));
      const chosen = schemaToUse(list, saved);
      if (chosen && chosen !== saved) pickSchema(chosen);
    } catch (e) {
      const answer = e instanceof engine.EngineCallError ? e.answer : { error: String(e?.message ?? e), kind: "unexpected" };
      setSchemaList(cached ? { loading: false, list: cached } : { loading: false, error: answer });
    }
  }

  function pickSchema(s: string) {
    setSchema(s);
    setDef((d) => (d.source ? { ...d, source: { ...d.source, schema: s } } : d));
    setDirty(true);
  }

  function onDecide(id: string, status: ReviewStatus) {
    setDef((d) => ({ ...d, review: decide(d.review, id, status) }));
    whileQuiet.current?.push((r) => decide(r, id, status));   // n223: kept for the review being read again
    setDirty(true);
  }

  function onAcceptAll(onlyPassed: boolean) {
    setDef((d) => (d.review ? { ...d, review: acceptAll(d.review, onlyPassed) } : d));
    whileQuiet.current?.push((r) => acceptAll(r, onlyPassed));
    setDirty(true);
  }

  // ED1: items the last check did not count that a check would count (changed since, or not part of it) are checked
  // again on their own, once per plan, when the review step is shown
  const autoChecked = React.useRef<string | undefined>(undefined);
  React.useEffect(() => {
    const r = def.review;
    if (view !== "review" || busy || !r) return;
    const key = `${r.plan_id ?? ""}`;
    if (autoChecked.current === key) return;
    const left = notCheckedLine(r.items as never, totalsOf(r).checked);
    if (!left?.again) return;
    autoChecked.current = key;
    void checkRows();
  }, [view, def.review, busy]);

  async function checkRows(from?: ModelDefinition) {
    const d0 = from ?? def;
    const a = await runEngine(checkLabel(d0.source?.schema), (o) =>
      engine.check(workloadClient, sourceRequest(d0), d0.review, o), { doing: "counting", cancellable: true }
    );
    if (!a) return;
    setMap(a.map);
    setSuggested(a.suggested_products);                       // n222: weighed by what the rows hold
    setDef((d) => ({ ...exactSchema(d, a.schema_used), review: a.review, item: withCache(d.item, { map: a.map }) }));
    announceSchema(a.schema_used);
    setDirty(true);
  }

  /** Thinker's question answered inline: a key or a link goes to the engine (a new review with it); keeping things as
   * they are is remembered in the item (item.json answers). */
  async function onChoice(c: Choice) {
    if (c.action.kind === "keep") {
      const about = c.action.about;
      setDef((d) => ({ ...d, item: { ...d.item, answers: { ...(d.item.answers ?? {}), [about]: "keep" } } }));
      setDirty(true);
      return;
    }
    if (c.action.kind === "key") {
      await plan(def, { keys: { [c.action.table]: c.action.columns } });
    } else {
      const { source, column, target, targetColumns } = c.action;
      await plan(def, { confirmed: [{ source, source_cols: [column], target, target_cols: targetColumns }] });
    }
  }

  /** n181: the App's ticks, kept in outputs.json at once (the item stores the choices) and sent with Preview and Create. */
  async function chooseApp(app: AppChoices) {
    const next = withAppChoices(choices, app);
    setChoices(next);
    const d = { ...def, outputs: { ...def.outputs, outputs: next } };
    setDef(d);
    await save(d);
  }

  /** ED2: the data product sent with the dry run and Create: its name and its owner (the one chosen on the Data product
   * page, else none: the engine then names the signed-in person, the same line everywhere). */
  function productRequest(d: ModelDefinition): { name: string; owner?: string } | null {
    const owner = d.outputs.product?.owner || undefined;
    if (product.on) return { name: product.name.trim(), ...(owner ? { owner } : {}) };
    return d.outputs.product ? { name: d.outputs.product.name, ...(owner ? { owner } : {}) } : null;
  }

  /** ED2: the one button under a dry run Create cannot start from: free names for a taken name, else leave those
   * outputs out; then the dry run again, so Create starts only from a dry run without the blocker. */
  async function fixBlocker(b: Blocker) {
    const taken = (preview?.outputs ?? []).map((c) => c.name);
    const next = choices.map((c) => {
      if (!b.outputs.includes(c.type as engine.OutputKind)) return c;
      if (b.fix === "leave_out") return { ...c, enabled: false };
      return namesWithOneSuffix([c], taken)[0];
    });
    setChoices(next);
    choicesRef.current = next;
    await previewBuild(next);
  }

  /** ED2: Clean up earlier builds: the Data product page's delete dry run of exactly those items; nothing is deleted
   * until the person confirms there. */
  async function cleanUpEarlier(ids: string[]) {
    go("product");
    await retireFromPage("delete", ids, {});
  }

  /** n174: every chosen output, one dry run each (the engine calls each MCP tool with dry_run=true). */
  async function previewBuild(chosen: OutputChoice[] = choicesRef.current) {
    const choices = chosen;
    const d = { ...defRef.current, outputs: { ...defRef.current.outputs, outputs: choices } };
    setDef(d);
    // n222: the engine prepares the outputs side by side and says how many are prepared; the wait (n223) shows its words
    const a = await runEngine(PREPARING, (o) =>
      engine.buildMany(workloadClient, sourceRequest(d), toRequests(choices, def.outputs.created), d.review, true, productRequest(d), d.outputs.created, d.outputs.pending ?? [],
        { ...o, products: chosenProducts(d) })
    );
    if (!a) return;
    setPreview(a);
    setStaleNote(staleLine(savedReview.current, d.review));     // ED2: said once, when the saved review was older
    if (d.review) savedReview.current = d.review;
    // n209: the App's choices, pages, package and one command, kept in outputs.json so an App built later shows them
    const kept = rememberApp(choices, a.outputs, new Date().toISOString());
    if (kept !== choices) {
      setChoices(kept);
      const d2 = { ...d, outputs: { ...d.outputs, outputs: kept } };
      setDef(d2);
      await save(d2);
    }
    go("preview");
  }

  // ---------------------------------------------------------------- n197: Create in the background
  // Each step answers at once with an operation id (engineClient.call reads it until it ends); before a step is sent its
  // items are recorded as pending in outputs.json and its operation id is kept in create_run, so a reload, a closed tab
  // or a phone asleep loses nothing: reopening reads the item's operations and goes on with the same run.
  const defRef = useRef<ModelDefinition>(def);
  defRef.current = def;
  const metaRef = useRef(itemMeta);
  metaRef.current = itemMeta;
  const cardsRef = useRef<engine.BuildCard[]>([]);
  const saving = useRef<Promise<unknown>>(Promise.resolve());
  /** n225: whether the definition this editor shows is saved in Fabric (the Data product page says it) */
  const [saveStatus, setSaveStatus] = useState<SaveStatus>({ state: "loaded" });
  /** n225: the number of the newest save asked for (an older copy is not sent once a newer one is queued) */
  const saveSeq = useRef(0);

  /** setDef and a save after the previous save (two saves never race); resolves when this one has been sent.
   * n225: callUpdateItemDefinition answers undefined when Fabric refuses a save, which used to pass for saved; now a save
   * Fabric did not confirm is tried again (saveState.saveWithRetry), a copy a newer one supersedes is not sent, and the
   * outcome is shown (Saved, Saving, Not saved with Save again). */
  function persist(next: ModelDefinition, baseRev?: number, waits: number[] = SAVE_WAITS_MS): Promise<"saved" | "superseded" | "failed" | undefined> {
    defRef.current = next;
    setDef(next);
    const meta = metaRef.current;
    if (!meta) return saving.current.then((): undefined => undefined);
    const seq = ++saveSeq.current;
    const newest = () => saveSeq.current === seq;
    setSaveStatus({ state: "saving", since: new Date().toISOString() });
    const mine = saving.current
      .then(async () => {
        if (!newest()) return "superseded" as const;             // a newer copy is queued behind this one and carries it
        // W14: the next revision, stamped when this copy is sent (after any save before it has moved the base)
        const sent = stamp(next, Math.max(baseRev ?? 0, base.current.rev), session.current);
        const got = await saveWithRetry(() => callUpdateItemDefinition(workloadClient, meta.id, toParts(sent) as never, false), newest, waits);
        if (got.outcome === "saved") {
          base.current = { rev: revisionOf(sent), decisions: decisionsOf(sent.review) };
          if (defRef.current === next) clearDraft(browserStore(), meta.id);   // nothing changed since: the draft is in Fabric
        }
        if (got.outcome === "saved" && newest()) setSaveStatus({ state: "saved", at: new Date().toISOString() });
        if (got.outcome === "failed") setSaveStatus({ state: "failed", at: new Date().toISOString(), tries: got.tries });
        return got.outcome;
      })
      .catch((): "failed" => "failed");
    saving.current = mine;
    return mine;
  }

  // ---------------------------------------------------------------- W14: autosave
  /** what Fabric had at the last read or save: its revision and its review decisions (the merge base) */
  const base = useRef<{ rev: number; decisions: Decisions }>({ rev: 0, decisions: {} });
  const session = useRef(newSession());
  const recovered = useRef<Recovery>();
  const autosaving = useRef(false);
  const [note, setNote] = useState<string>();

  /** Reads Fabric's revision; when another session saved meanwhile, merges its decisions in (autosave.resolve), then
   * saves through persist. A change made while this runs is saved by the next autosave. */
  async function autosave(): Promise<void> {
    const meta = metaRef.current;
    if (!meta || autosaving.current) return;
    autosaving.current = true;
    setDirty(false);
    try {
      const local = defRef.current;
      let remote: ModelDefinition | undefined;
      try {
        remote = fromParts((await callGetItemDefinition(workloadClient, meta.id))?.definition?.parts);
      } catch {
        remote = undefined;   // the read failed: save on the base this session has (last write wins)
      }
      const r = resolve(local, base.current.decisions, base.current.rev, remote);
      if (r.conflict) setNote(conflictWords(r.conflict));
      if (defRef.current !== local) {
        // the person changed something during the read: merge again on the next autosave
        setDirty(true);
        return;
      }
      // WB3 (F6): tried once more, then one sentence; the decisions stay in defRef and the draft, so Save still saves them.
      // Only the item's definition is written here: never Create, never anything in the workspace.
      await persist(r.def, r.baseRev, AUTOSAVE_WAITS_MS);
    } finally {
      autosaving.current = false;
    }
  }

  // the draft in this browser, written at each unsaved change, so a reload or a closed tab loses nothing
  useEffect(() => {
    if (!dirty || isLoading || !itemMeta) return;
    writeDraft(browserStore(), itemMeta.id, def, base.current.rev, base.current.decisions);
  }, [def, dirty, isLoading, itemMeta]);

  // the save itself, a moment after the last change (one Create at a time saves its own steps)
  useEffect(() => {
    if (!dirty || isLoading || !itemMeta || creating) return undefined;
    const t = setTimeout(() => void autosave(), AUTOSAVE_DELAY_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [def, dirty, isLoading, itemMeta, creating]);

  // hidden or closed: save at once (the draft covers the case where the browser does not wait for it)
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  useEffect(() => {
    const flush = () => {
      if (dirtyRef.current && document.visibilityState !== "visible") void autosave();
    };
    const leave = () => { if (dirtyRef.current) void autosave(); };
    document.addEventListener("visibilitychange", flush);
    window.addEventListener("pagehide", leave);
    return () => {
      document.removeEventListener("visibilitychange", flush);
      window.removeEventListener("pagehide", leave);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const autosaveState: AutosaveState = saveStatus.state === "failed" ? "failed"
    : saveStatus.state === "saving" ? "saving" : dirty ? "pending" : "saved";

  function update(fn: (d: ModelDefinition) => ModelDefinition): Promise<unknown> {
    return persist(fn(defRef.current));
  }

  function showCards(cards: engine.BuildCard[]) {
    cardsRef.current = cards;
    setResult((r) => ({ ...(r ?? EMPTY_RESULT), outputs: cards, refused: cards.filter((c) => c.refusal || c.answer?.error).length } as engine.ManyAnswer));
  }

  function replaceCard(card: engine.BuildCard) {
    showCards(cardsRef.current.map((x) => (x.output === card.output ? card : x)));
  }

  /** One Create step: the answer the engine already has (a reopened item), the operation still running (read again,
   * never sent twice), or a new request with this output's items recorded as pending first. */
  async function sendStep(o: engine.OutputRequest, made: engine.CreatedRef[], outputs: engine.OutputRequest[], src: engine.SourceRequest,
    known: Known, extra: engine.StepExtra = {}): Promise<engine.ManyAnswer> {
    let a: engine.ManyAnswer | undefined = extra.refresh_only ? undefined : known.answers[o.kind];
    if (!a) {
      const resume = extra.refresh_only ? undefined : known.running[o.kind];
      if (!resume && !extra.refresh_only) {
        await update((d) => ({ ...d, outputs: { ...d.outputs, pending: withPending(d.outputs.pending, o, outputs, src.schema, new Date().toISOString()) } }));
      }
      const d = defRef.current;
      const runId = readRun(d.outputs.create_run)?.id;
      a = await engine.buildOne(workloadClient, src, o, outputs, d.review, made, undefined,
        { schedule_ids: scheduleIds(d.outputs.pipeline_jobs), item_id: metaRef.current?.id, ...(runId ? { create_id: runId } : {}),
          pending: d.outputs.pending ?? [], ...extra },
        {
          resume,
          onStarted: (id) => {
            if (extra.refresh_only) return;
            void update((x) => {
              const r = readRun(x.outputs.create_run);
              return r ? { ...x, outputs: { ...x.outputs, create_run: withOperation(r, o.kind, id) } } : x;
            });
          },
          onProgress: (st) => {
            const now = cardsRef.current.find((c) => c.output === o.kind);
            if (now && now.status === "running") replaceCard(withProgress(now, st));
          },
        });
    }
    const card = a.outputs[0];
    const made2 = a.created ?? card?.created ?? [];
    const at = new Date().toISOString();
    if (card) setChoices((cs) => rememberApp(cs, [card], at));   // n209: the App's package, kept with its choices
    await update((d) => {
      const x = { ...d, outputs: { ...d.outputs, outputs: rememberApp(d.outputs.outputs.length ? d.outputs.outputs : choices, card ? [card] : [], at),
        created: mergeCreated(d.outputs.created, made2), ...(card ? { pending: settlePending(d.outputs.pending, card, made2) } : {}) } };
      return card?.output === "pipeline" && card.jobs?.run?.run_id ? withJobRecords(x, [card]) : x;   // the run, kept at once
    });
    return a;
  }

  /** n179/n197: one step per output in the engine's order, each card with its own progress and result. A lost answer
   * costs one card, never the others; the created ids and the pending items are saved as each step ends. Then the data
   * product and the flow, from the created ids, and the pipeline's run followed with what waits for it. */
  // n222: the dry run page's own Create button "did nothing" in the founder's live test of 11 November 2026: Create first
  // waited for the item's save (Fabric's updateItemDefinition, after any save still on its way) before it showed anything,
  // so a click looked lost, and a second click (the toolbar's) could start a second Create. Now the click shows the
  // Create's cards and locks both buttons at once; the save goes on behind them. One Create at a time.
  const creatingRef = useRef(false);

  async function create(resumeFrom?: { run: CreateRunRecord; known: Known }) {
    if (creatingRef.current) return;
    creatingRef.current = true;
    setCreating(true);
    setError(undefined);
    setWait(undefined);
    const d0 = defRef.current;
    const src = sourceRequest(d0);
    const outputs = resumeFrom ? resumeFrom.run.outputs : toRequests(choices, def.outputs.created);
    const productReq = productRequest(d0);
    const run = resumeFrom?.run ?? startRun(newCreateId(), outputs, new Date().toISOString());
    const known: Known = resumeFrom?.known ?? { answers: {}, running: {}, progress: {} };
    const held = waitsForRun(outputs);
    showCards(inOrder(outputs).map((o) => pendingCard(o, "waiting", preview?.outputs.find((c) => c.output === o.kind))));
    go("result");
    try {
      await persist({ ...d0, item: { ...d0.item, view: "result" }, outputs: { ...d0.outputs, outputs: resumeFrom ? d0.outputs.outputs : choices,
        create_run: run } });
      const done = await createEach(
        outputs,
        defRef.current.outputs.created,
        async (o, made) => {
          if (held.includes(o.kind) && !known.answers[o.kind]) {
            return { outputs: [heldCard(pendingCard(o, "waiting", preview?.outputs.find((c) => c.output === o.kind)))], created: [] } as unknown as engine.ManyAnswer;
          }
          const ran = resumeFrom && o.kind === "pipeline" && !known.answers.pipeline ? runOf(resumeFrom.run) : undefined;
          if (ran) {
            // resumed without the engine's answer: the run this Create started is followed, never started a second time
            const a = await sendStep({ ...o, jobs: { ...(o.jobs ?? { schedule: null }), run_once: false } }, made, outputs, src, known);
            const c = a.outputs[0];
            return { ...a, outputs: [{ ...c, jobs: c?.jobs ? { ...c.jobs, run_once: true, run: ran } : c?.jobs }] } as engine.ManyAnswer;
          }
          return sendStep(o, made, outputs, src, known);
        },
        (cards) => {
          // the operation's own state while a step runs (a reopened item: waiting for capacity, still in Fabric)
          showCards(cards.map((c) => (c.status === "running" && known.progress[c.output] ? withProgress(c, known.progress[c.output]!) : c)));
        },
        preview
      );
      await finishCreate(done.cards, src, outputs, productReq);
    } finally {
      creatingRef.current = false;
      setCreating(false);
    }
    await followRun(cardsRef.current, src, outputs);           // Try again stays open on the other cards meanwhile
  }

  /** n197: the pipeline run this Create started, as outputs.json recorded it (none: not started yet). */
  function runOf(r: CreateRunRecord): engine.PipelineRun | undefined {
    const rec = (defRef.current.outputs.pipeline_jobs?.runs ?? []).filter((x) => (x.at ?? "") >= r.at).slice(-1)[0];
    return rec ? { status: rec.status as engine.PipelineRun["status"], run_id: rec.run_id, started: rec.started } : undefined;
  }

  /** The data product and the flow of the whole Create, the stored finish, the run and schedule records. */
  async function finishCreate(cards: engine.BuildCard[], src: engine.SourceRequest, outputs: engine.OutputRequest[], productReq: { name: string } | null) {
    const thisRun = cards.flatMap((c) => c.created ?? []);
    let a: engine.ManyAnswer = { ...EMPTY_RESULT, outputs: cards, created: thisRun,
      refused: cards.filter((c) => c.refusal || c.answer?.error).length } as engine.ManyAnswer;
    if (thisRun.length) {
      try {
        const f = await engine.finish(workloadClient, src, outputs, defRef.current.review, productReq, defRef.current.outputs.created);
        const product = f.product ? { ...f.product, items: markEarlier(f.product.items as engine.CreatedRef[], thisRun) } : undefined;
        a = { ...a, product: product as engine.DataProduct | undefined, flow: f.flow, row_check: f.row_check };
      } catch {
        /* the cards stand on their own; the product and the flow come with the next Create */
      }
    }
    setResult(a);
    cardsRef.current = cards;
    const at = new Date().toISOString();
    let d = defRef.current;
    d = { ...d, outputs: { ...afterCreate(d.outputs, d.outputs.outputs.length ? d.outputs.outputs : choices, a, at),
      last_create: lastCreateOf(cards, metaRef.current?.displayName ?? "", at) } };
    if (a.product && d.outputs.product) d = { ...d, outputs: { ...d.outputs, product: { ...d.outputs.product, items: markEarlier(d.outputs.product.items, thisRun) } } };
    d = withJobRecords(d, cards);                                // n185: run and schedule ids, for a later cleanup
    // n225: the plan of this Create, recorded even when the finish (the data product) did not answer, so the Data product
    // page shows it and its health is read for this plan, not an older one
    if (thisRun.length) d = { ...d, outputs: withPlan(d.outputs, d.review?.plan_id, at) };
    if (d.source && crossWorkspace(d.source, metaRef.current?.workspaceId)) {
      // n221: the lakehouse silver and gold were written to (chosen, made or the first of the workspace), kept in
      // source.json so the next Create uses it and the health table (n200) is read there
      const kept = keptTarget(cards.map((c) => c.answer?.target).find((t) => t?.id), buildWorkspace(d.source, metaRef.current?.workspaceId));
      if (kept) {
        const { createLakehouse: _made, ...rest } = d.source;
        d = { ...d, source: { ...rest, target: kept } };
      }
    }
    await persist(d);
  }

  /** n185: the schedule Create set and the run it started, into outputs.json (pipeline_jobs). */
  function withJobRecords(d: ModelDefinition, cards: engine.BuildCard[]): ModelDefinition {
    const card = cards.find((c) => c.output === "pipeline");
    const pipe = pipelineItem(card);
    if (!card || !pipe) return d;
    const at = new Date().toISOString();
    let rec = recordSchedule(d.outputs.pipeline_jobs, pipe, card, at);
    if (card.jobs?.run) rec = recordRun(rec, pipe, card.jobs.run, at);
    return { ...d, outputs: { ...d.outputs, pipeline_jobs: rec } };
  }

  /** n185/n197: the run Create started, read every POLL_MS for at most MAX_WAIT_MS (no other card waits for it). When
   * it has succeeded: the model this Create made is refreshed once, the report waiting for the run is made, and the data
   * agent is sent again (its examples checked against the filled tables; published if Publish was ticked). When it
   * failed: those steps stop, their cards say why in plain words and offer Try again. */
  async function followRun(cards: engine.BuildCard[], src: engine.SourceRequest, outputs: engine.OutputRequest[]) {
    const card = cards.find((c) => c.output === "pipeline");
    const pipe = pipelineItem(card);
    let run = card?.jobs?.run;
    const markDone = () => update((d) => {
      const r = readRun(d.outputs.create_run);
      return r ? { ...d, outputs: { ...d.outputs, create_run: { ...r, finished: true } } } : d;
    });
    if (!card || !pipe || !run?.run_id) {
      await markDone();
      return;
    }
    const until = Date.now() + MAX_WAIT_MS;
    while (!runFinished(run) && Date.now() < until) {
      await new Promise((r) => setTimeout(r, POLL_MS));
      try {
        run = await engine.pipelineRun(workloadClient, { workspace: pipe.workspace, pipeline_id: pipe.id, pipeline_name: pipe.name,
          run_id: run!.run_id as string, started: run!.started });
      } catch {
        continue;                                               // one lost read is not the run's end; the bound still holds
      }
      const now = cardsRef.current.find((c) => c.output === "pipeline") ?? card;
      replaceCard({ ...now, jobs: { ...now.jobs!, run } });
    }
    if (!runFinished(run)) {
      run = stillRunning(run!);
      const now = cardsRef.current.find((c) => c.output === "pipeline") ?? card;
      replaceCard({ ...now, jobs: { ...now.jobs!, run } });
      await update((d) => ({ ...d, outputs: { ...d.outputs, pipeline_jobs: recordRun(d.outputs.pipeline_jobs, pipe, run!, new Date().toISOString()),
        last_create: lastCreateOf(cardsRef.current, metaRef.current?.displayName ?? "", new Date().toISOString()) } }));
      return;                                                   // reopening the item follows it again (create_run not finished)
    }
    const ok = run!.status === "Succeeded";
    const why = run!.why ?? (ok ? "" : run!.status === "NotStarted" ? "it did not start" : "it failed");
    const made = () => defRef.current.outputs.created;
    // 1. the model this Create made, refreshed once
    const model = cardsRef.current.find((c) => c.output === "semantic_model");
    if (model && model.refresh?.status === "planned" && model.created?.length) {
      if (ok) {
        try {
          const a = await sendStep(outputs.find((o) => o.kind === "semantic_model")!, made(), outputs, src, NOTHING_KNOWN, { refresh_only: true });
          const r = a.outputs[0]?.refresh;
          if (r) replaceCard({ ...model, refresh: r });
        } catch (e) {
          replaceCard({ ...model, refresh: { status: "failed", reason: e instanceof engine.EngineCallError ? e.answer.error : String(e) } });
        }
      } else {
        replaceCard({ ...model, refresh: { status: "not_run", reason: `the pipeline's run did not succeed (${why})` } });
      }
    }
    // 2. what waited for the run (the report)
    for (const held of cardsRef.current.filter((c) => c.after_run === "waiting")) {
      const o = outputs.find((x) => x.kind === held.output);
      if (!o) continue;
      if (!ok) {
        replaceCard(stoppedCard(held, why));
        continue;
      }
      replaceCard({ ...pendingCard(o, "running"), after_run: undefined });
      try {
        const a = await sendStep(requestFor(o, outputs, made()), made(), outputs, src, NOTHING_KNOWN);
        replaceCard({ ...a.outputs[0], status: "done" });
      } catch (e) {
        replaceCard(failedCard(o, e, held));
      }
    }
    // 3. the data agent, with the run's end
    const agentOut = outputs.find((o) => o.kind === "data_agent");
    if (agentOut && agentAfterRun(cardsRef.current, run!)) {
      try {
        const a = await sendStep(agentOut, made(), outputs, src, NOTHING_KNOWN, { after_run: { status: run!.status } });
        const agentCard = a.outputs.find((c) => c.output === "data_agent");
        if (agentCard) replaceCard({ ...agentCard, status: "done" });
      } catch {
        /* the agent stays as Create left it; its card says so */
      }
    }
    const pipeNow = cardsRef.current.find((c) => c.output === "pipeline");
    if (pipeNow) replaceCard({ ...pipeNow, jobs: { ...pipeNow.jobs!, run } });
    const at = new Date().toISOString();
    await update((d) => {
      const r = readRun(d.outputs.create_run);
      return { ...d, outputs: { ...d.outputs, created: mergeCreated(d.outputs.created, cardsRef.current.flatMap((c) => c.created ?? [])),
        pipeline_jobs: recordRun(d.outputs.pipeline_jobs, pipe, run!, at),
        last_create: lastCreateOf(cardsRef.current, metaRef.current?.displayName ?? "", readLastCreate(d.outputs.last_create)?.at ?? at),
        ...(r ? { create_run: { ...r, finished: true } } : {}) } };
    });
  }

  /** n197 (2b): Try again on one card: its step sent again (what Fabric finished meanwhile is adopted through pending). */
  async function retryCard(card: engine.BuildCard) {
    const d = defRef.current;
    const outputs = readRun(d.outputs.create_run)?.outputs ?? toRequests(choices, def.outputs.created);
    const o = outputs.find((x) => x.kind === card.output);
    if (!o) return;
    const src = sourceRequest(d);
    setUpdating(true);
    replaceCard({ ...pendingCard(o, "running", card), after_run: undefined, after_run_words: undefined });
    let got: engine.BuildCard;
    try {
      const a = await sendStep(requestFor(o, outputs, d.outputs.created), d.outputs.created, outputs, src, NOTHING_KNOWN);
      got = { ...a.outputs[0], status: "done" };
    } catch (e) {
      got = failedCard(o, e, card);
    }
    replaceCard(got);
    const at = new Date().toISOString();
    await update((x) => ({ ...x, outputs: { ...x.outputs, last_create: lastCreateOf(cardsRef.current, metaRef.current?.displayName ?? "", at) } }));
    setUpdating(false);
    if (got.output === "pipeline" && got.jobs?.run?.run_id && !runFinished(got.jobs.run)) {
      await update((x) => withJobRecords(x, cardsRef.current));
      await followRun(cardsRef.current, src, outputs);
    }
  }

  /** ED2: Fix and finish: only the outputs not built (failed, no answer, stopped, or waiting for one that failed), in
   * the build order, through the same createEach as Create, starting from what this item built (reused, never sent
   * again); a lakehouse the dry run planned is made by the first step that needs it. */
  async function createRest() {
    const d = defRef.current;
    const all = readRun(d.outputs.create_run)?.outputs ?? toRequests(choices, d.outputs.created);
    const missing = toFinish(cardsRef.current).map((c) => all.find((o) => o.kind === c.output)).filter(Boolean) as engine.OutputRequest[];
    if (!missing.length) return;
    const src = sourceRequest(d);
    setUpdating(true);
    try {
      const done = await createEach(missing, d.outputs.created, (o, made) => sendStep(requestFor(o, all, made), made, all, src, NOTHING_KNOWN),
        (cards) => showCards(cardsRef.current.map((c) => cards.find((x) => x.output === c.output) ?? c)));
      showCards(cardsRef.current.map((c) => done.cards.find((x) => x.output === c.output) ?? c));
      const at = new Date().toISOString();
      await update((x) => ({ ...x, outputs: { ...x.outputs, last_create: lastCreateOf(cardsRef.current, metaRef.current?.displayName ?? "", at) } }));
    } finally {
      setUpdating(false);
    }
    await followRun(cardsRef.current, src, all);
  }

  /** n197: reopening an item with outputs lands on its result: the cards of its last Create (from the engine's
   * operations, else rebuilt from the created ids), the flow and the product; a Create still in progress goes on. */
  async function reopen(loaded: ModelDefinition, itemId: string) {
    const run = readRun(loaded.outputs.create_run);
    let ops: engine.OperationState[] = [];
    if (run) {
      try {
        ops = (await engine.itemOperations(workloadClient, itemId)).operations;
      } catch (e) {
        if (isBusy(e)) setNotice(BUSY_LINE);
      }
    }
    const known = run ? knownOf(run, ops) : NOTHING_KNOWN;
    if (run && !run.finished) {
      await create({ run, known });
      return;
    }
    const outputs = run?.outputs ?? toRequests(choicesFor(loaded.outputs.outputs, loaded.source?.displayName ?? "").filter((c) => c.enabled));
    const src = sourceRequest(loaded);
    try {
      const f = await engine.finish(workloadClient, src, outputs, loaded.review, loaded.outputs.product ? { name: loaded.outputs.product.name } : null,
        loaded.outputs.created);
      const cards = f.outputs.map((c) => {
        const ans = known.answers[c.output]?.outputs?.[0];
        return { ...(ans ?? c), status: "done" as const };
      });
      cardsRef.current = cards;
      const thisRun = run ? cards.flatMap((c) => c.created ?? []) : loaded.outputs.created;
      setResult({ ...f, outputs: cards, product: f.product ? { ...f.product, items: markEarlier(f.product.items as engine.CreatedRef[], thisRun) } as engine.DataProduct : undefined });
    } catch (e) {
      setNotice(isBusy(e) ? BUSY_LINE : `The last Create's cards could not be read again (${e instanceof engine.EngineCallError ? e.answer.error : String(e)}); what was built is listed below.`);
    }
  }

  /** n180: Update of an output built from another plan: the dry run first (its card shows what would change and offers
   * Update in Fabric), then the update with the dry run's confirmation. The created ids, with this plan, are saved. */
  async function updateCard(card: engine.BuildCard) {
    const outputs = toRequests(choices, def.outputs.created);
    const o = outputs.find((x) => x.kind === card.output);
    if (!o) return;
    const src = sourceRequest(def);
    setUpdating(true);
    replaceCard({ ...card, status: "running" });
    try {
      const got = await runUpdate(card, (dryRun, confirm) =>
        engine.updateOne(workloadClient, src, o, outputs, def.review, def.outputs.created, dryRun, confirm)
      );
      replaceCard(got.card);
      const last = withCard(readLastCreate(def.outputs.last_create), got.card, new Date().toISOString());   // n184
      if (got.created.length || (last && !got.card.dry_run)) {
        const d = { ...def, outputs: { ...def.outputs, outputs: choices, created: mergeCreated(def.outputs.created, got.created),
          ...(last ? { last_create: last } : {}) } };
        setDef(d);
        await save(d);
      }
    } catch (e) {
      replaceCard(failedCard(o, e, card));
    } finally {
      setUpdating(false);
    }
  }

  /** n180: keep the item built from another plan as it is; the outputs get a free name and the outputs view opens.
   * n197: one name suffix per Create: every output of it gets the same free suffix (demo_lh_model_3, demo_lh_report_3). */
  function newNameForCard(card: engine.BuildCard) {
    const taken = [...def.outputs.created.map((c) => c.name), ...choices.map((c) => c.name), ...(card.existing_items ?? []).map((c) => c.name),
      ...(def.outputs.pending ?? []).map((p) => p.name)];
    setChoices((cs) => namesWithOneSuffix(cs, taken));
    setDirty(true);
    go("outputs");
  }

  // ---------------------------------------------------------------- n198: the Data product page
  const productName = (d: ModelDefinition = defRef.current): string => {
    const n = (d.outputs.product?.name ?? metaRef.current?.displayName ?? "data product").replace(/[^A-Za-z0-9 _.-]/g, "_").trim();
    return /^[A-Za-z0-9]/.test(n) ? n.slice(0, 80) : `p ${n}`.slice(0, 80);
  };

  function productBody(action: string, extra: Record<string, unknown> = {}): Record<string, unknown> {
    const d = defRef.current;
    const o = d.outputs;
    // n221: the data product's workspace is where its items were built (this item's by default), not the source's
    return { action, workspace: productWorkspace(d.source, o.created, metaRef.current?.workspaceId), item_id: metaRef.current?.id, product: productName(d),
      plan_id: o.product?.plan?.plan_id ?? null,
      outputs: { created: o.created, removed: o.removed ?? [], pending: o.pending ?? [], pipeline_jobs: o.pipeline_jobs ?? { runs: [], schedules: [] } },
      ...extra };
  }

  const engineWords = (e: unknown) => (e instanceof engine.EngineCallError ? [e.answer.error, e.answer.hint].filter(Boolean).join(" ") : String((e as Error)?.message ?? e));

  /** n223: a step of the Data product page: its wait is Onto's line above the page (the page stays); `readOnly` steps
   * offer Cancel after 30 s. */
  const dpStop = useRef<AbortController>();
  async function productStep<T>(label: string, fn: (o: engine.CallOptions) => Promise<T>, how: Partial<Wait> = {}): Promise<T | undefined> {
    const started = Date.now();
    const { opts, stop } = waitHandle(started, (f) => setDp((x) => ({ ...x, wait: f(x.wait) })));
    dpStop.current = stop;
    setDp((x) => ({ ...x, busy: label, problem: undefined, wait: newWait(label, started, how) }));
    try {
      return await fn(opts);
    } catch (e) {
      if (!wasCancelled(e)) setDp((x) => ({ ...x, problem: isBusy(e) ? BUSY_LINE : engineWords(e) }));
      return undefined;
    } finally {
      if (dpStop.current === stop) dpStop.current = undefined;
      setDp((x) => (x.wait?.startedAt === started ? { ...x, busy: undefined, wait: undefined } : x));
    }
  }

  async function loadProduct() {
    // n210: the Model item's own workspace, where its definition is read (the source's workspace can be another one)
    // n225: the health of this data product's plan (sent, so an older plan's result is never read for it)
    const plan = planOf(defRef.current.outputs, defRef.current.review?.plan_id);
    const h = engine.health(workloadClient, { workspace: metaRef.current?.workspaceId ?? defRef.current.source?.workspaceId,
      item_id: metaRef.current?.id, product: productName(), ...(plan ? { plan_id: plan } : {}) });
    const s = await productStep("Reading the items in Fabric…", (o) => engine.product<StatusAnswer>(workloadClient, productBody("status"), undefined, o),
      { cancellable: true });
    const health = await h;
    setDp((x) => ({ ...x, ...(s ? { status: s } : {}),
      health: healthFor(health as never, planOf(defRef.current.outputs, defRef.current.review?.plan_id), createdAtOf(defRef.current.outputs)) }));
    if (s) void adoptOwnLeftovers(s);
  }

  /** ED3 (Gustav: "Built ... but this item has no id saved for it. Look for leftovers below finds it ..."): an output the
   * latest Create built whose id this item lost is looked up by Krusgraph's plan marker and added at once when the
   * marker is this data product's plan and the name is the one Create gave it; said once. Other leftovers stay below. */
  async function adoptOwnLeftovers(s: StatusAnswer) {
    const plan = planOf(defRef.current.outputs, defRef.current.review?.plan_id);
    const rows = rowsOf(defRef.current.outputs, s, plan);
    if (!rows.some((r) => r.key.startsWith("unsaved:"))) return;
    let found: LeftoversAnswer | undefined;
    try {
      found = await engine.product<LeftoversAnswer>(workloadClient, productBody("leftovers"));
    } catch {
      return;                                            // the manual Look for leftovers stays
    }
    const take = autoAdopt(rows, found);
    if (!take.length) { setDp((x) => ({ ...x, leftovers: found })); return; }
    try {
      const a = await engine.product<{ adopted: CreatedItem[]; refused: { why: string }[]; words: string }>(workloadClient,
        productBody("adopt", { items: take.map((t) => t.id) }));
      if (a.adopted.length) {
        await update((d) => ({ ...d, outputs: withAdopted(d.outputs, a.adopted) }));
        setDp((x) => ({ ...x, adopted: a.adopted.map((c) => c.name), leftovers: undefined }));
        const st = await engine.product<StatusAnswer>(workloadClient, productBody("status"));
        setDp((x) => ({ ...x, status: st }));
      }
    } catch {
      /* nothing added: the leftovers list below still offers Adopt */
    }
  }

  async function saveOwner(name: string) {
    const by = dp.status?.you ?? "";
    await update((d) => ({ ...d, outputs: withOwner(d.outputs, name, by, new Date().toISOString(), productName(d)) }));
    callNotificationOpen(workloadClient, "Owner saved", name.trim() ? `${name.trim()} owns ${productName()}.` : "The owner was cleared.");
  }

  /** Update: the rows counted again, then a dry run of every output; what is out of date gets the existing Update path. */
  async function checkUpdates() {
    const d = defRef.current;
    if (!d.source || !d.review) return;
    const outputs = readRun(d.outputs.create_run)?.outputs ?? toRequests(choices, def.outputs.created);
    const step2 = "Step 2 of 2: a dry run of every output…";
    const a = await productStep("Step 1 of 2: counting the rows…", async (o) => {
      const c = await engine.check(workloadClient, sourceRequest(d), d.review!, o);
      setMap(c.map);
      setDp((x) => (x.wait ? { ...x, busy: step2, wait: { ...x.wait, label: step2, kind: "starting", progress: undefined, words: undefined,
        doing: "building", steps: [...x.wait.steps, { at: Math.round((Date.now() - x.wait.startedAt) / 1000), text: "The rows were counted." }] } } : x));
      await update((x) => ({ ...x, review: c.review }));
      return engine.buildMany(workloadClient, sourceRequest(defRef.current), outputs, defRef.current.review!, true, null, defRef.current.outputs.created, defRef.current.outputs.pending ?? []);
    }, { doing: "counting", cancellable: true });
    if (a) setDp((x) => ({ ...x, updates: outOfDate(a.outputs) }));
  }

  /** Update from the page: the dry run first (its card gives confirm_update), then the write with that confirmation. */
  async function updateFromPage(card: engine.BuildCard) {
    const d = defRef.current;
    const outputs = readRun(d.outputs.create_run)?.outputs ?? toRequests(choices, def.outputs.created);
    const o = outputs.find((x) => x.kind === card.output);
    if (!o || !d.review) return;
    const got = await productStep(card.confirm_update ? `Updating ${card.name} in Fabric…` : `Dry run of the Update of ${card.name}…`, () =>
      runUpdate(card, (dryRun, confirm) => engine.updateOne(workloadClient, sourceRequest(d), o, outputs, d.review!, d.outputs.created, dryRun, confirm)));
    if (!got) return;
    setDp((x) => ({ ...x, updates: (x.updates ?? []).map((u) => (u.output === card.output ? outOfDate([got.card])[0] : u)) }));
    if (got.created.length) {
      await update((x) => ({ ...x, outputs: { ...x.outputs, created: mergeCreated(x.outputs.created, got.created) } }));
      void loadProduct();
    }
  }

  /** Retire and Delete from Fabric: the dry run first; the real call with its confirm (and the typed name for Delete). */
  async function retireFromPage(scope: "soft" | "delete", ids: string[] | null, opts: { leftovers?: boolean; confirm?: string; typed?: string }) {
    const real = !!opts.confirm;
    const label = real ? (scope === "soft" ? "Turning off what Krusgraph scheduled…" : "Deleting from Fabric…") : "Making the dry run…";
    const a = await productStep(label, () => engine.product<RetireAnswer>(workloadClient, productBody("retire", {
      scope, ...(ids ? { items: ids } : {}), dry_run: !real, leftovers: !!opts.leftovers, ...(real ? { confirm: opts.confirm, typed_name: opts.typed ?? "" } : {}),
    })));
    if (!a) return;
    setDp((x) => ({ ...x, retire: a }));
    if (real && a.removed?.length) {
      const removed = a.removed as RemovedItem[];
      if (!opts.leftovers) await update((d) => ({ ...d, outputs: withRemoved(d.outputs, removed) }));
      callNotificationOpen(workloadClient, "Deleted from Fabric", a.words);
    }
    if (real) {
      void loadProduct();
      if (opts.leftovers) void findLeftovers();
    }
  }

  async function findLeftovers() {
    const a = await productStep("Looking for leftovers in the workspace…", (o) => engine.product<LeftoversAnswer>(workloadClient, productBody("leftovers"), undefined, o),
      { cancellable: true });
    if (a) setDp((x) => ({ ...x, leftovers: a }));
  }

  async function adoptLeftover(id: string) {
    const a = await productStep("Adopting it into this data product…", () =>
      engine.product<{ adopted: CreatedItem[]; refused: { why: string }[]; words: string }>(workloadClient, productBody("adopt", { items: [id] })));
    if (!a) return;
    if (a.adopted.length) await update((d) => ({ ...d, outputs: withAdopted(d.outputs, a.adopted) }));
    else setDp((x) => ({ ...x, problem: a.refused.map((r) => r.why).join(" ") || a.words }));
    void findLeftovers();
    void loadProduct();
  }

  function openRow(row: ProductRow) {
    if (row.id) void openItem({ id: row.id, workspaceId: row.workspace ?? defRef.current.source?.workspaceId, type: row.type, displayName: row.name } as never);
  }

  async function openItem(item: OpenLink["item"]) {
    await navigateToItem(workloadClient, item as never);
  }

  // ---------------------------------------------------------------- ribbon (one sticky ribbon, Home first)
  const homeActions = (): RibbonAction[] => {
    const back: Partial<Record<ModelView, ModelView>> = { review: "empty", outputs: "review", preview: "outputs", result: "outputs", product: "result" };
    const actions: RibbonAction[] = [createSaveAction(() => save(), !dirty || !itemMeta)];
    actions.push({ key: "choose-source", icon: Database24Regular, label: "Choose source", onClick: () => go("empty") });
    if (view === "review") {
      actions.push({ key: "check", icon: CheckmarkStarburst24Regular, label: def.review?.items.some((it) => it.check) ? "Check against the rows again" : "Check against the rows", onClick: () => void checkRows(), disabled: !!busy || !def.review });
      actions.push({ key: "refresh", icon: ArrowClockwise24Regular, label: "Read the lakehouse again", onClick: () => plan(def, {}, true), disabled: !!busy });
      actions.push({ key: "next", icon: ArrowRight24Regular, label: "Next", onClick: () => go("outputs") });
    }
    if (view === "preview") actions.push({ key: "create", icon: Play24Regular, label: "Create", onClick: () => create(), disabled: !!busy || creating });
    if (view !== "product" && (def.outputs.created.length > 0 || (def.outputs.removed ?? []).length > 0)) {   // n198
      actions.push({ key: "data-product", icon: BoxMultiple24Regular, label: "Data product", onClick: () => { go("product"); void loadProduct(); }, disabled: creating });
    }
    if (back[view]) actions.push({ key: "back", icon: ArrowLeft24Regular, label: "Back", onClick: () => go(back[view]) });
    // W13: every action but Save shows its label (Save stays icon only: Learn, publishing requirements for items, 3.4)
    return actions.map((a) => (a.key === "save" ? a : { ...a, showLabel: true }));
  };

  // W13: where you are (FlowSteps.tsx), at the top of every view's canvas; done steps can be gone back to
  const steps = flowSteps(view, {
    review: !!def.review, preview: !!preview || def.outputs.created.length > 0,
    built: def.outputs.created.length > 0 || (def.outputs.removed ?? []).length > 0,
  });
  const goStep = (v: ModelView) => {
    if (v === "product") { go("product"); void loadProduct(); } else go(v);
  };
  /** W13: a next step's "Dry run": those outputs ticked (and only those), then Choose what to build, as for any output */
  const buildNext = (outputs: string[]) => {
    setChoices((cs) => cs.map((c) => ({ ...c, enabled: outputs.includes(c.type) })));
    go("outputs");
  };
  const nextPanel = (
    <NextStepsPanel review={def.review} created={def.outputs.created} source={def.source} onBuild={buildNext} />
  );

  const wrap = (node: React.ReactNode) => (
    <div className="kg-wrap">
      <FlowSteps steps={steps} onGo={goStep} />
      <SaveIndicator state={autosaveState} at={saveStatus.state === "saved" ? saveStatus.at : undefined}
        tries={saveStatus.state === "failed" ? saveStatus.tries : undefined} note={note}
        onSaveAgain={() => void persist({ ...defRef.current })} onDismissNote={() => setNote(undefined)} />
      <ErrorBar error={error} />
      {trialLine ? <div style={{ fontSize: 12, opacity: 0.75, margin: "4px 0" }} role="status">{trialLine}</div> : null}
      {quiet && !wait ? <Busy wait={quiet} mascotsOn={mascotsOn} skeleton={false} /> : null}
      {wait ? <Busy wait={wait} mascotsOn={mascotsOn} onCancel={cancelWait} /> : node}
    </div>
  );

  const views = [
    {
      name: "empty",
      component: wrap(
        <EmptyView
          source={def.source}
          schema={schema}
          schemas={schemaList}
          onSchemaChange={pickSchema}
          onChooseLakehouse={chooseLakehouse}
          onChooseTarget={chooseTarget}
          onReview={() => plan(def, {}, true)}
          mascotsOn={mascotsOn}
        />
      ),
    },
    {
      name: "review",
      component: wrap(
        def.source && def.review ? (
          <ReviewView
            source={def.source}
            review={def.review}
            map={map}
            answered={def.item.answers ?? {}}
            checking={!!busy}
            mascotsOn={mascotsOn}
            onToggleMascots={() => setMascotsOn((on) => !on)}
            onDecide={onDecide}
            onAcceptAll={onAcceptAll}
            onCheck={() => void checkRows()}
            onChoice={onChoice}
            readOnly={sourceInfo.readOnly}
            sap={sourceInfo.sap}
            onNext={() => go("outputs")}
          />
        ) : null
      ),
    },
    {
      name: "outputs",
      component: wrap(
        <OutputsView
          choices={choices}
          onChange={setChoices}
          created={def.outputs.created}
          product={product}
          onProduct={setProduct}
          stored={def.outputs.product}
          onOpen={openItem}
          onPreview={() => void previewBuild()}
          jobsBlocked={jobsBlocked(preview?.outputs)}
          source={def.source}
          itemWorkspaceId={itemMeta?.workspaceId}
          onBuildIn={chooseBuildIn}
          onChooseTarget={chooseTarget}
          onPickModel={() => void pickReportModel()}
          owner={def.outputs.product?.owner || preview?.product?.owner || dp.status?.you || null}
          extra={<SuggestedProductsPanel suggested={suggested} ticked={ticked(def)} disabled={!!busy || creating}
            onTicked={(list: Ticked[]) => void update((d) => ({ ...d, outputs: { ...d.outputs, products: list } }))} />}
        />
      ),
    },
    {
      name: "preview",
      component: wrap(preview ? <PreviewView answer={preview} onCreate={() => void create()} creating={creating || !!busy} mascotsOn={mascotsOn} createLabel={createLabel(preview)}
        stale={staleNote} onFixBlocker={(b) => void fixBlocker(b)}
        appChoices={choices.find((c) => c.type === "rayfin_app")?.app} onAppChoices={chooseApp}
        appRecord={readAppRecord(choices.find((c) => c.type === "rayfin_app")?.app_package, choices.find((c) => c.type === "rayfin_app")?.name)} /> : null),
    },
    // W13: next steps with other Fabric workloads, under the result once something was built
    {
    name: "result",
    component: wrap(
      result || def.outputs.created.length ? (
        <>
          <ResultView
            answer={result}
            outputs={def.outputs}
            onOpen={openItem}
            mascotsOn={mascotsOn}
            onUpdate={updateCard}
            onNewName={newNameForCard}
            onRetry={retryCard}
            onCreateRest={() => void createRest()}
            onCleanUp={(ids) => void cleanUpEarlier(ids)}
            notice={notice}
            busy={updating || creating}
          />
          {!creating && nextPanel}
        </>
      ) : null
    ),
    },
  ];

  const productPage = (
      <DataProductPage
        productName={productName(def)}
        outputs={def.outputs}
        plan={planOf(def.outputs, def.review?.plan_id)}
        saved={saveStatus}
        onSaveAgain={() => void persist({ ...defRef.current })}
        status={dp.status}
        health={dp.health}
        busy={dp.busy}
        waiting={dp.wait ? <OntoWait wait={dp.wait} mascotsOn={mascotsOn} skeleton={false} onCancel={() => dpStop.current?.abort()} /> : undefined}
        problem={dp.problem}
        updates={dp.updates}
        retire={dp.retire}
        leftovers={dp.leftovers}
        onRefresh={() => void loadProduct()}
        onOpen={openRow}
        onOwner={(n) => void saveOwner(n)}
        onCheckUpdates={() => void checkUpdates()}
        onUpdate={(c) => void updateFromPage(c)}
        onNewName={newNameForCard}
        onRetire={(s, ids, o) => void retireFromPage(s, ids, o)}
        onFindLeftovers={() => void findLeftovers()}
        onAdopt={(id) => void adoptLeftover(id)}
        adopted={dp.adopted}
        onCheckHealth={() => void loadProduct()}
        onFixAndFinish={() => { go("result"); }}
      />
  );
  views.push({ name: "product", component: wrap(<>{productPage}<CatalogPanel />{nextPanel}</>) });   // CA1


  // n228: "Download as draw.io" under the map and the data flow (drawioDownload.tsx); the engine makes the file from what is shown
  const drawioName = [def.source?.displayName, def.source?.schema].filter(Boolean).join(".");
  const drawioSource = useMemo<DrawioSource>(
    () => ({ get: (body) => engine.drawio<DrawioFile>(workloadClient, body), name: drawioName || undefined }),
    [workloadClient, drawioName]
  );

  // n229: "Verify what was built" after a Create (verifyBuilt.tsx): the engine reads back what outputs.json records, by rules
  const verifySource = useMemo<VerifySource>(
    () => ({
      run: () => {
        const d = defRef.current;
        return engine.verify<VerifyAnswer>(workloadClient, { ...sourceRequest(d), review: d.review, created: d.outputs.created, item_id: metaRef.current?.id });
      },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [workloadClient]
  );

  // CA1: "Publish to OneLake catalog" on the Data product page (CatalogPanel.tsx): a dry run first, the write with its confirm
  const catalogOwner = def.outputs.product?.owner ?? null;
  // WB10: the same people and Me as the Data product page's Owner; the names of the items built are never an owner
  const catalogPeople = dp.status?.people ?? null;
  const catalogYou = dp.status?.you ?? null;
  const catalogItems = def.outputs.created.map((c) => c.name).filter(Boolean).join("\n");
  const catalogSource = useMemo<CatalogSource>(
    () => ({
      owner: catalogOwner,
      people: catalogPeople,
      you: catalogYou,
      itemNames: catalogItems ? catalogItems.split("\n") : [],
      run: ({ dryRun, confirm, owner, include }) => {
        const d = defRef.current;
        return engine.catalog<CatalogAnswer>(workloadClient, { ...sourceRequest(d), review: d.review, outputs: { created: d.outputs.created },
          owner: owner ?? null, dry_run: dryRun, confirm: confirm ?? null, include: include ?? [] });
      },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [workloadClient, catalogOwner, catalogPeople, catalogYou, catalogItems]
  );

  // WB10 (#57): every download goes through the engine's single-use link, opened by the Fabric host in a new tab
  const fileSource = useMemo<FileSource>(
    () => ({
      offer: (f) => engine.file<FileLink>(workloadClient, { filename: f.filename, mime: f.mime,
        ...(f.base64 !== undefined ? { content_base64: f.base64 } : { content: f.text ?? "" }) }),
      open: async (url) => {
        const got = (await workloadClient.navigation.openBrowserTab({ url })) as { success?: boolean } | undefined;
        if (got && got.success === false) throw new Error("not opened");
      },
      base: (process.env.KRUSGRAPH_ENGINE_URL || "").replace(/\/$/, "") || (typeof window === "undefined" ? "" : window.location.origin),
    }),
    [workloadClient]
  );

  // WB14 (#108): "Save to lakehouse Files" beside Download, only when the hosting server's switch is on
  // (KRUSGRAPH_ONELAKE_SAVE -> the meta tag krusgraph-onelake-save) and the item targets a lakehouse: the chosen target,
  // else a lakehouse source. The Storage token is the signed-in user's, asked of the Fabric host (onelakeSave.ts).
  const saveOn = saveEnabled(typeof document === "undefined" ? undefined : document);
  const src = def.source;
  const lakehouse = src?.target
    ? { workspaceId: src.target.workspaceId ?? src.workspaceId, lakehouseId: src.target.itemId, lakehouseName: src.target.displayName }
    : src && /lakehouse/i.test(src.itemType || "") ? { workspaceId: src.workspaceId, lakehouseId: src.itemId, lakehouseName: src.displayName } : undefined;
  const saveItemName = itemMeta?.displayName ?? "";
  const oneLakeSource = useMemo<OneLakeSaveSource | undefined>(
    () => (saveOn && lakehouse && saveItemName ? {
      target: { ...lakehouse, itemName: saveItemName },
      token: async () => (await workloadClient.auth.acquireFrontendAccessToken({ scopes: [STORAGE_SCOPE] })).token,
    } : undefined),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [workloadClient, saveOn, lakehouse?.workspaceId, lakehouse?.lakehouseId, lakehouse?.lakehouseName, saveItemName]
  );

  // WB10 (#64): the Data Science starter's Dry run and Create; what Create made joins outputs.json like any output
  const starterSource = useMemo<StarterSource>(
    () => ({
      run: ({ name, cells, dryRun, confirm, stage }) =>
        engine.starter<StarterAnswer>(workloadClient, { ...sourceRequest(defRef.current), name, cells, dry_run: dryRun, confirm: confirm ?? null,
          ...(stage && stage !== "features" ? { stage } : {}) }),   // AA1: a model or predictions notebook is recorded as that stage
      open: (item) => void openItem({ id: item.id, workspaceId: item.workspace ?? defRef.current.source?.workspaceId, type: item.type, displayName: item.name } as never),
      onCreated: (item) => {
        void update((d) => ({ ...d, outputs: { ...d.outputs, created: [...d.outputs.created.filter((c) => c.id !== item.id), item] } }));
        callNotificationOpen(workloadClient, "Notebook created", `${item.name} is in your workspace. Krusgraph did not run it.`);
      },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [workloadClient]
  );

  // WB4: Recommended analyses: analysis_plan on this item's reviewed plan (read-only; the engine answers only after the check)
  const analysisSource = useMemo<AnalysisSource>(
    () => ({
      run: () => engine.analysis<AnalysisAnswer>(workloadClient, { ...sourceRequest(defRef.current), review: defRef.current.review }),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [workloadClient]
  );

  return (
    <FileContext.Provider value={fileSource}>
    <AnalysisContext.Provider value={analysisSource}>
    <OneLakeContext.Provider value={oneLakeSource}>
    <StarterContext.Provider value={starterSource}>
    <DrawioContext.Provider value={drawioSource}>
    <VerifyContext.Provider value={verifySource}>
    <CatalogContext.Provider value={catalogSource}>
    <ItemEditor
      isLoading={isLoading}
      loadingMessage="Opening the model…"
      loadingContent={<div className="krusgraph-view"><OntoWait wait={opening} mascotsOn={mascotsOn} /></div>}
      ribbon={(context) => <Ribbon homeToolbarActions={homeActions()} viewContext={context}
        logo={<img src="/assets/krusgraph-item-icon.png" alt="Krusgraph Model" width={24} height={24} />} />}
      views={views}
      viewSetter={(setter) => {
        if (!setView) setSetView(() => setter);
      }}
    />
    </CatalogContext.Provider>
    </VerifyContext.Provider>
    </DrawioContext.Provider>
    </StarterContext.Provider>
    </OneLakeContext.Provider>
    </AnalysisContext.Provider>
    </FileContext.Provider>
  );
}
