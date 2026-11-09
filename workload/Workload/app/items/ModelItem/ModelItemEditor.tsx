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
import { OpenLink, afterCreate, choicesFor, createLabel, toRequests } from "./buildWords";
import { Busy, EmptyView, ErrorBar, OutputsView, PreviewView, ResultView, ReviewView } from "./ModelItemViews";
import { MapData } from "./cardMap";
import { Choice, acceptAll } from "./modelWords";

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
  const [choices, setChoices] = useState<OutputChoice[]>([]);
  const [product, setProduct] = useState<{ on: boolean; name: string }>({ on: false, name: "" });
  const [map, setMap] = useState<MapData>();
  const [mascotsOn, setMascotsOn] = useState(true);
  const [preview, setPreview] = useState<engine.ManyAnswer>();
  const [result, setResult] = useState<engine.ManyAnswer>();
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
        const parts = await callGetItemDefinition(workloadClient, itemObjectId);
        const loaded = fromParts(parts?.definition?.parts);
        setItemMeta({ id: got.item.id, workspaceId: got.item.workspaceId, displayName: got.item.displayName });
        setDef(loaded);
        setSchema(loaded.source?.schema ?? "dbo");
        setChoices(choicesFor(loaded.outputs.outputs, loaded.source?.displayName ?? got.item.displayName));
        setProduct({ on: !!loaded.outputs.product, name: loaded.outputs.product?.name ?? got.item.displayName });
        setIsLoading(false);
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
    setChoices((c) => choicesFor(c.filter((x) => x.enabled), picked.displayName));
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

  async function create() {
    const a = await runEngine("Creating in Fabric, one output after another…", () =>
      engine.buildMany(workloadClient, sourceRequest(def), toRequests(choices), def.review, false, product.on ? { name: product.name.trim() } : null, def.outputs.created)
    );
    if (!a) return;
    setResult(a);
    const d = { ...def, item: { ...def.item, view: "result" as const }, outputs: afterCreate(def.outputs, choices, a, new Date().toISOString()) };
    setDef(d);
    setView?.("result");
    await save(d);
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
          onSchemaChange={(s) => {
            setSchema(s);
            setDef((d) => (d.source ? { ...d, source: { ...d.source, schema: s } } : d));
          }}
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
        />
      ),
    },
    {
      name: "preview",
      component: wrap(preview ? <PreviewView answer={preview} onCreate={create} mascotsOn={mascotsOn} createLabel={createLabel(preview)} /> : null),
    },
    {
      name: "result",
      component: wrap(
        result || def.outputs.created.length ? <ResultView answer={result} outputs={def.outputs} onOpen={openItem} mascotsOn={mascotsOn} /> : null
      ),
    },
  ];

  return (
    <ItemEditor
      isLoading={isLoading}
      loadingMessage="Opening the model…"
      ribbon={(context) => <Ribbon homeToolbarActions={homeActions()} viewContext={context} />}
      views={views}
      viewSetter={(setter) => {
        if (!setView) setSetView(() => setter);
      }}
    />
  );
}
