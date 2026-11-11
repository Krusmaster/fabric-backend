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
import React, { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { NotificationType } from "@ms-fabric/workload-client";
import {
  ArrowClockwise24Regular,
  ArrowLeft24Regular,
  ArrowRight24Regular,
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
  toRetry, waitsForRun, withOperation, withPending, withProgress,
} from "./createRun";
import { Busy, EmptyView, ErrorBar, OutputsView, PreviewView, ResultView, ReviewView } from "./ModelItemViews";
import { MapData } from "./cardMap";
import { Choice, acceptAll } from "./modelWords";
import { withAppChoices } from "./appWords";
import {
  MAX_WAIT_MS, POLL_MS, agentAfterRun, jobsBlocked, pipelineItem, recordRun, recordSchedule, runFinished, scheduleIds, stillRunning,
} from "./jobsWords";
import { AppChoices } from "./engineClient";
import { PICKER_TYPES, ReadOnlySource, SapOffer, isReadOnly, restType, targetProblem } from "./sourceWords";

const VIEWS: ModelView[] = ["empty", "review", "outputs", "preview", "result"];
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

export function ModelItemEditor(props: PageProps) {
  const { workloadClient } = props;
  const { itemObjectId } = useParams<ContextProps>();

  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState<string>();
  const [error, setError] = useState<engine.EngineError>();
  const [itemMeta, setItemMeta] = useState<{ id: string; workspaceId: string; displayName: string }>();
  const [def, setDef] = useState<ModelDefinition>(emptyDefinition());
  const [dirty, setDirty] = useState(false);
  const [schema, setSchema] = useState("dbo");
  /** n179: the lakehouse's schemas, listed after Choose lakehouse; the schema is picked, never typed */
  const [schemaList, setSchemaList] = useState<{ loading: boolean; list?: engine.SchemasAnswer; error?: engine.EngineError }>({ loading: false });
  const [choices, setChoices] = useState<OutputChoice[]>([]);
  const [product, setProduct] = useState<{ on: boolean; name: string }>({ on: false, name: "" });
  const [map, setMap] = useState<MapData>();
  const [mascotsOn, setMascotsOn] = useState(true);
  const [preview, setPreview] = useState<engine.ManyAnswer>();
  const [result, setResult] = useState<engine.ManyAnswer>();
  const [updating, setUpdating] = useState(false);
  /** n197: a Create (or its follow-up) is going on: Create is not offered twice */
  const [creating, setCreating] = useState(false);
  /** n197: one line on the result when the saved state or the engine could not be read */
  const [notice, setNotice] = useState<string>();
  /** n201: what the last review said about the source: read-only (where the build writes) and the SAP pack's items */
  const [sourceInfo, setSourceInfo] = useState<{ readOnly?: ReadOnlySource; sap?: SapOffer }>({});
  const [setView, setSetView] = useState<(v: string) => void>();
  const view = def.item.view;

  const go = (v: ModelView) => {
    setDef((d) => ({ ...d, item: { ...d.item, view: v } }));
    setView?.(v);
  };

  const sourceRequest = (d: ModelDefinition): engine.SourceRequest => ({
    workspace: d.source.workspaceId,
    source: d.source.itemId,
    source_name: d.source.displayName,
    schema: d.source.schema,
    // n201: a read-only source's build writes to the chosen lakehouse, or the workspace's first (null)
    ...(isReadOnly(d.source.itemType) ? { target: { lakehouse: d.source.target?.itemId ?? null } } : {}),
  });

  /** n201: the source's real item type (the picker may name it otherwise) and what the review says about it. */
  const withKind = (d: ModelDefinition, a: engine.ReviewAnswer): ModelDefinition => {
    setSourceInfo({ readOnly: a.read_only, sap: a.sap });
    return a.source_kind && d.source && d.source.itemType !== a.source_kind ? { ...d, source: { ...d.source, itemType: a.source_kind } } : d;
  };

  async function runEngine<T>(label: string, fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(label);
    setError(undefined);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof engine.EngineCallError ? e.answer : { error: String(e?.message ?? e), kind: "unexpected" });
      return undefined;
    } finally {
      setBusy(undefined);
    }
  }

  /** n175: the source with the schema as the lakehouse spells it, and a notification that says which name was used. */
  const exactSchema = (d: ModelDefinition, used?: engine.SchemaUsed): ModelDefinition =>
    !used || !d.source || d.source.schema === used.used ? d : { ...d, source: { ...d.source, schema: used.used } };

  function announceSchema(used?: engine.SchemaUsed) {
    if (!used) return;
    setSchema(used.used);
    callNotificationOpen(workloadClient, "Schema name", used.note);
  }

  async function plan(d: ModelDefinition, corrections: engine.Corrections = {}) {
    const a = await runEngine("Reading the lakehouse and finding keys and links…", () =>
      engine.review(workloadClient, sourceRequest(d), d.review, corrections)
    );
    if (!a) return;
    setMap(a.map);
    d = withKind(exactSchema(d, a.schema_used), a);
    announceSchema(a.schema_used);
    setDef({ ...d, review: a.review, item: { ...d.item, view: "review" } });
    setDirty(true);
    setView?.("review");
  }

  /** n197: the review read again in the background on reopening an item that has outputs; the result stays in view.
   * A busy Fabric is one line, never a page without its flow. */
  async function replanQuietly(d: ModelDefinition) {
    try {
      const a = await engine.review(workloadClient, sourceRequest(d), d.review, {});
      setMap(a.map);
      setDef((x) => ({ ...withKind(exactSchema(x, a.schema_used), a), review: a.review }));
    } catch (e) {
      if (isBusy(e)) setNotice(BUSY_LINE);
    }
  }

  // ---------------------------------------------------------------- load
  useEffect(() => {
    (async () => {
      setIsLoading(true);
      try {
        const got = await callGetItem(workloadClient, itemObjectId);
        rememberWorkloadOf(got.item.type);   // n176: Org.Krusgraph or Krusgraph.Modeler, for the engine scope
        const parts = await callGetItemDefinition(workloadClient, itemObjectId);
        const loaded = fromParts(parts?.definition?.parts);
        setItemMeta({ id: got.item.id, workspaceId: got.item.workspaceId, displayName: got.item.displayName });
        setDef(loaded);
        setSchema(loaded.source?.schema ?? "dbo");
        setChoices(choicesFor(loaded.outputs.outputs, loaded.source?.displayName ?? got.item.displayName,
          loaded.source ? { displayName: got.item.displayName, created: loaded.outputs.created } : undefined));
        setProduct({ on: !!loaded.outputs.product, name: loaded.outputs.product?.name ?? got.item.displayName });
        // n197: an item with outputs (or a Create in progress) opens on its result: the summary, the flow and the cards
        const hasResult = loaded.outputs.created.length > 0 || !!readRun(loaded.outputs.create_run);
        if (hasResult) {
          defRef.current = { ...loaded, item: { ...loaded.item, view: "result" } };
          metaRef.current = { id: got.item.id, workspaceId: got.item.workspaceId, displayName: got.item.displayName };
          setDef(defRef.current);
        }
        setIsLoading(false);
        if (loaded.source) void listSchemas(loaded.source.workspaceId, loaded.source.itemId, loaded.source.displayName, loaded.source.schema);
        if (hasResult && loaded.source) {
          if (loaded.review) void replanQuietly(loaded);
          await reopen(defRef.current, got.item.id);
          setDirty(false);
        } else if (loaded.source && loaded.review) {
          await plan({ ...loaded, item: { ...loaded.item, view: "review" } }); // re-plan with the saved decisions
          setDirty(false);
        }
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
    const ok = await callUpdateItemDefinition(workloadClient, itemMeta.id, toParts(d) as never, false);
    if (ok) {
      setDirty(false);
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
    await listSchemas(picked.workspaceId, picked.id, picked.displayName);
  }

  /** n201: the lakehouse a read-only source's build writes to: one of the source's workspace. */
  async function chooseTarget() {
    if (!def.source) return;
    const picked = await callDatahubOpen(workloadClient, ["Lakehouse"],
      "Choose the lakehouse the silver tables, gold views and the pipeline's check are written to", false);
    if (!picked) return;
    const problem = targetProblem(def.source.workspaceId, { workspaceId: picked.workspaceId, type: restType(picked.type) });
    if (problem) {
      callNotificationOpen(workloadClient, "Target lakehouse", problem, NotificationType.Error);
      return;
    }
    setDef((d) => (d.source ? { ...d, source: { ...d.source, target: { itemId: picked.id, displayName: picked.displayName } } } : d));
    setDirty(true);
  }

  /** n179: the schemas of the chosen lakehouse with their table counts; the only one with tables is preselected. */
  async function listSchemas(workspaceId: string, itemId: string, displayName: string, saved?: string) {
    setSchemaList({ loading: true });
    try {
      const list = await engine.schemas(workloadClient, { workspace: workspaceId, source: itemId, source_name: displayName });
      setSchemaList({ loading: false, list });
      const chosen = schemaToUse(list, saved);
      if (chosen && chosen !== saved) pickSchema(chosen);
    } catch (e) {
      setSchemaList({ loading: false, error: e instanceof engine.EngineCallError ? e.answer : { error: String(e?.message ?? e), kind: "unexpected" } });
    }
  }

  function pickSchema(s: string) {
    setSchema(s);
    setDef((d) => (d.source ? { ...d, source: { ...d.source, schema: s } } : d));
    setDirty(true);
  }

  function onDecide(id: string, status: ReviewStatus) {
    setDef((d) => ({ ...d, review: decide(d.review, id, status) }));
    setDirty(true);
  }

  function onAcceptAll(onlyPassed: boolean) {
    setDef((d) => (d.review ? { ...d, review: acceptAll(d.review, onlyPassed) } : d));
    setDirty(true);
  }

  async function checkRows() {
    const a = await runEngine("Counting the rows: is each key unique, does each link find its table…", () =>
      engine.check(workloadClient, sourceRequest(def), def.review)
    );
    if (!a) return;
    setMap(a.map);
    setDef((d) => ({ ...exactSchema(d, a.schema_used), review: a.review }));
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

  /** n174: every chosen output, one dry run each (the engine calls each MCP tool with dry_run=true). */
  async function previewBuild() {
    const d = { ...def, outputs: { ...def.outputs, outputs: choices } };
    setDef(d);
    const a = await runEngine("Preparing the dry run of each output…", () =>
      engine.buildMany(workloadClient, sourceRequest(d), toRequests(choices), d.review, true, product.on ? { name: product.name.trim() } : null, d.outputs.created)
    );
    if (!a) return;
    setPreview(a);
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

  /** setDef and a save after the previous save (two saves never race); resolves when this one has been sent. */
  function persist(next: ModelDefinition): Promise<unknown> {
    defRef.current = next;
    setDef(next);
    const meta = metaRef.current;
    if (!meta) return saving.current;
    saving.current = saving.current
      .then((): Promise<unknown> => callUpdateItemDefinition(workloadClient, meta.id, toParts(next) as never, false))
      .catch((): undefined => undefined);
    return saving.current;
  }

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
    await update((d) => {
      const x = { ...d, outputs: { ...d.outputs, outputs: d.outputs.outputs.length ? d.outputs.outputs : choices,
        created: mergeCreated(d.outputs.created, made2), ...(card ? { pending: settlePending(d.outputs.pending, card, made2) } : {}) } };
      return card?.output === "pipeline" && card.jobs?.run?.run_id ? withJobRecords(x, [card]) : x;   // the run, kept at once
    });
    return a;
  }

  /** n179/n197: one step per output in the engine's order, each card with its own progress and result. A lost answer
   * costs one card, never the others; the created ids and the pending items are saved as each step ends. Then the data
   * product and the flow, from the created ids, and the pipeline's run followed with what waits for it. */
  async function create(resumeFrom?: { run: CreateRunRecord; known: Known }) {
    setError(undefined);
    setBusy(undefined);
    const d0 = defRef.current;
    const src = sourceRequest(d0);
    const outputs = resumeFrom ? resumeFrom.run.outputs : toRequests(choices);
    const productReq = product.on ? { name: product.name.trim() } : d0.outputs.product ? { name: d0.outputs.product.name } : null;
    const run = resumeFrom?.run ?? startRun(newCreateId(), outputs, new Date().toISOString());
    const known: Known = resumeFrom?.known ?? { answers: {}, running: {}, progress: {} };
    const held = waitsForRun(outputs);
    await persist({ ...d0, item: { ...d0.item, view: "result" }, outputs: { ...d0.outputs, outputs: resumeFrom ? d0.outputs.outputs : choices,
      create_run: run } });
    showCards([]);
    go("result");
    setCreating(true);
    try {
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
    const outputs = readRun(d.outputs.create_run)?.outputs ?? toRequests(choices);
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

  /** n197 (2b): every red, unanswered or stopped card sent again, one after another. */
  async function createRest() {
    for (const c of toRetry(cardsRef.current)) {
      await retryCard(c);
    }
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
    const outputs = toRequests(choices);
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

  async function openItem(item: OpenLink["item"]) {
    await navigateToItem(workloadClient, item as never);
  }

  // ---------------------------------------------------------------- ribbon (one sticky ribbon, Home first)
  const homeActions = (): RibbonAction[] => {
    const back: Partial<Record<ModelView, ModelView>> = { review: "empty", outputs: "review", preview: "outputs", result: "outputs" };
    const actions: RibbonAction[] = [createSaveAction(() => save(), !dirty || !itemMeta)];
    actions.push({ key: "choose-source", icon: Database24Regular, label: "Choose source", onClick: () => go("empty") });
    if (view === "review") {
      actions.push({ key: "check", icon: CheckmarkStarburst24Regular, label: "Check against the rows", onClick: checkRows, disabled: !!busy || !def.review });
      actions.push({ key: "refresh", icon: ArrowClockwise24Regular, label: "Read the lakehouse again", onClick: () => plan(def), disabled: !!busy });
      actions.push({ key: "next", icon: ArrowRight24Regular, label: "Next", onClick: () => go("outputs") });
    }
    if (view === "preview") actions.push({ key: "create", icon: Play24Regular, label: "Create", onClick: () => create(), disabled: !!busy || creating });
    if (back[view]) actions.push({ key: "back", icon: ArrowLeft24Regular, label: "Back", onClick: () => go(back[view]) });
    return actions;
  };

  const wrap = (node: React.ReactNode) => (
    <>
      <ErrorBar error={error} />
      {busy ? <Busy label={busy} /> : node}
    </>
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
          onReview={() => plan(def)}
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
            onCheck={checkRows}
            onChoice={onChoice}
            readOnly={sourceInfo.readOnly}
            sap={sourceInfo.sap}
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
          onPreview={previewBuild}
          jobsBlocked={jobsBlocked(preview?.outputs)}
        />
      ),
    },
    {
      name: "preview",
      component: wrap(preview ? <PreviewView answer={preview} onCreate={() => { if (!creating) void create(); }} mascotsOn={mascotsOn} createLabel={createLabel(preview)}
        appChoices={choices.find((c) => c.type === "rayfin_app")?.app} onAppChoices={chooseApp} /> : null),
    },
    {
      name: "result",
      component: wrap(
        result || def.outputs.created.length ? <ResultView
            answer={result}
            outputs={def.outputs}
            onOpen={openItem}
            mascotsOn={mascotsOn}
            onUpdate={updateCard}
            onNewName={newNameForCard}
            onRetry={retryCard}
            onCreateRest={createRest}
            notice={notice}
            busy={updating || creating}
          /> : null
      ),
    },
  ];

  return (
    <ItemEditor
      isLoading={isLoading}
      loadingMessage="Opening the model…"
      ribbon={(context) => <Ribbon homeToolbarActions={homeActions()} viewContext={context}
        logo={<img src="/assets/krusgraph-item-icon.png" alt="Krusgraph Model" width={24} height={24} />} />}
      views={views}
      viewSetter={(setter) => {
        if (!setView) setSetView(() => setter);
      }}
    />
  );
}
