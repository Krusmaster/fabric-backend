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
import React, { useEffect, useState } from "react";
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
import { lastCreateOf, readLastCreate, withCard, withRunEnd } from "./createWords";
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
  OpenLink, afterCreate, choicesFor, createEach, createLabel, failedCard, mergeCreated, newNameFor, runUpdate, schemaToUse, toRequests,
} from "./buildWords";
import { Busy, EmptyView, ErrorBar, OutputsView, PreviewView, ResultView, ReviewView } from "./ModelItemViews";
import { MapData } from "./cardMap";
import { Choice, acceptAll } from "./modelWords";
import { withAppChoices } from "./appWords";
import {
  MAX_WAIT_MS, POLL_MS, agentAfterRun, jobsBlocked, pipelineItem, recordRun, recordSchedule, runFinished, scheduleIds, stillRunning,
} from "./jobsWords";
import { AppChoices } from "./engineClient";

const VIEWS: ModelView[] = ["empty", "review", "outputs", "preview", "result"];

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
  });

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
    d = exactSchema(d, a.schema_used);
    announceSchema(a.schema_used);
    setDef({ ...d, review: a.review, item: { ...d.item, view: "review" } });
    setDirty(true);
    setView?.("review");
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
        setIsLoading(false);
        if (loaded.source) void listSchemas(loaded.source.workspaceId, loaded.source.itemId, loaded.source.displayName, loaded.source.schema);
        if (loaded.source && loaded.review) {
          await plan({ ...loaded, item: { ...loaded.item, view: "review" } }); // re-plan with the saved decisions
          setDirty(false);
        }
      } catch (e) {
        setError({ error: e instanceof DefinitionError ? e.message : `The item could not be opened: ${e?.message ?? e}`, kind: "definition" });
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

  async function chooseLakehouse() {
    const picked = await callDatahubOpen(workloadClient, ["Lakehouse"], "Choose the lakehouse Krusgraph should read", false);
    if (!picked) return;
    const source = {
      version: 1,
      platform: "fabric" as const,
      workspaceId: picked.workspaceId,
      itemId: picked.id,
      itemType: picked.type,
      displayName: picked.displayName,
      schema,
    };
    setDef((d) => ({ ...d, source, review: d.source?.itemId === picked.id ? d.review : undefined }));
    setChoices((c) => choicesFor(c.filter((x) => x.enabled), picked.displayName,
      { displayName: def.source?.displayName ?? itemMeta?.displayName, created: def.outputs.created }));
    setDirty(true);
    await listSchemas(picked.workspaceId, picked.id, picked.displayName);
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

  /** n179: one request per output in the engine's order, each card with its own progress and result. A closed
   * connection costs one card ("no answer yet"), never the others; the created ids are saved after each output, so a
   * re-run skips what is built and retries only the rest. Then the data product and the flow, from the created ids. */
  async function create() {
    setError(undefined);
    setBusy(undefined);
    const src = sourceRequest(def);
    const outputs = toRequests(choices);
    const productReq = product.on ? { name: product.name.trim() } : null;
    const base = { dry_run: false, order: outputs.map((o) => o.kind), left_out_by_review: [] as engine.LeftOut[], refused: 0, note: "" };
    setResult({ ...base, outputs: [] } as engine.ManyAnswer);
    go("result");
    let d = def;
    const run = await createEach(
      outputs,
      def.outputs.created,
      async (o, created) => {
        const a = await engine.buildOne(workloadClient, src, o, outputs, def.review, created, undefined,
          { schedule_ids: scheduleIds(def.outputs.pipeline_jobs) });
        if ((a.created ?? []).length) {               // kept at once: a later lost answer cannot lose these ids
          d = { ...d, outputs: { ...d.outputs, outputs: choices, created: mergeCreated(d.outputs.created, a.created) } };
          setDef(d);
          await callUpdateItemDefinition(workloadClient, itemMeta.id, toParts(d) as never, false);
        }
        return a;
      },
      (cards) => setResult((r) => ({ ...(r ?? base), outputs: cards, refused: cards.filter((c) => c.refusal || c.answer?.error).length } as engine.ManyAnswer)),
      preview
    );
    // n184 (addition 2): the finish is kept at once, so the banner shows and reopening the item shows it again
    d = { ...d, outputs: { ...d.outputs, last_create: lastCreateOf(run.cards, itemMeta?.displayName ?? "", new Date().toISOString()) } };
    setDef(d);
    let a: engine.ManyAnswer = {
      ...base, outputs: run.cards, created: run.cards.flatMap((c) => c.created ?? []),
      refused: run.cards.filter((c) => c.refusal || c.answer?.error).length,
    } as engine.ManyAnswer;
    if (run.cards.some((c) => c.created?.length)) {
      try {
        const f = await engine.finish(workloadClient, src, outputs, def.review, productReq, run.created);
        a = { ...a, product: f.product, flow: f.flow, row_check: f.row_check };
      } catch {
        /* the cards stand on their own; the product and the flow come with the next Create */
      }
    }
    setResult(a);
    d = { ...d, item: { ...d.item, view: "result" as const }, outputs: afterCreate(d.outputs, choices, a, new Date().toISOString()) };
    d = withJobRecords(d, run.cards);                            // n185: run and schedule ids, for a later cleanup
    setDef(d);
    await save(d);
    await followRun(d, run.cards, src, outputs);
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

  /** n185: the run Create started, read every POLL_MS for at most MAX_WAIT_MS (no other card waits for it). When it
   * ends, its card, the finish and outputs.json say so; the data agent Krusgraph made is sent again with the run's end,
   * so it reads the silver tables and, if Publish was ticked and the run succeeded, is published. */
  async function followRun(d0: ModelDefinition, cards: engine.BuildCard[], src: engine.SourceRequest, outputs: engine.OutputRequest[]) {
    const card = cards.find((c) => c.output === "pipeline");
    const pipe = pipelineItem(card);
    let run = card?.jobs?.run;
    if (!card || !pipe || !run?.run_id || runFinished(run)) return;
    const until = Date.now() + MAX_WAIT_MS;
    while (!runFinished(run) && Date.now() < until) {
      await new Promise((r) => setTimeout(r, POLL_MS));
      try {
        run = await engine.pipelineRun(workloadClient, { workspace: pipe.workspace, pipeline_id: pipe.id, pipeline_name: pipe.name,
          run_id: run!.run_id as string, started: run!.started });
      } catch {
        continue;                                               // one lost read is not the run's end; the bound still holds
      }
      replaceCard({ ...card, jobs: { ...card.jobs!, run } });
    }
    if (!runFinished(run)) run = stillRunning(run!);
    replaceCard({ ...card, jobs: { ...card.jobs!, run } });
    const at = new Date().toISOString();
    let d = { ...d0, outputs: { ...d0.outputs, pipeline_jobs: recordRun(d0.outputs.pipeline_jobs, pipe, run!, at),
      last_create: withRunEnd(readLastCreate(d0.outputs.last_create), run!.status) } };
    const agentOut = outputs.find((o) => o.kind === "data_agent");
    if (agentOut && agentAfterRun(cards, run!)) {
      try {
        const a = await engine.buildOne(workloadClient, src, agentOut, outputs, d.review, d.outputs.created, undefined,
          { schedule_ids: scheduleIds(d.outputs.pipeline_jobs), after_run: { status: run!.status } });
        const agentCard = a.outputs.find((c) => c.output === "data_agent");
        if (agentCard) {
          replaceCard({ ...agentCard, status: "done" });
          d = { ...d, outputs: { ...d.outputs, created: mergeCreated(d.outputs.created, agentCard.created ?? []),
            last_create: withRunEnd(readLastCreate(d.outputs.last_create), run!.status, !!agentCard.agent?.published) } };
        }
      } catch {
        /* the agent stays as Create left it; its card says so */
      }
    }
    setDef(d);
    await save(d);
  }

  function replaceCard(card: engine.BuildCard) {
    setResult((r) => (r ? { ...r, outputs: r.outputs.map((x) => (x.output === card.output ? card : x)) } : r));
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

  /** n180: keep the item built from another plan as it is; the output gets a free name and the outputs view opens. */
  function newNameForCard(card: engine.BuildCard) {
    const taken = [...def.outputs.created.map((c) => c.name), ...choices.map((c) => c.name)];
    const name = newNameFor(card, taken);
    setChoices((cs) => cs.map((c) => (c.type === card.output ? { ...c, name } : c)));
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
    if (view === "preview") actions.push({ key: "create", icon: Play24Regular, label: "Create", onClick: create, disabled: !!busy });
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
      component: wrap(preview ? <PreviewView answer={preview} onCreate={create} mascotsOn={mascotsOn} createLabel={createLabel(preview)}
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
            busy={updating}
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
