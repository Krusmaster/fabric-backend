/**
 * The Krusgraph Model item editor (renamed and rewritten from the starter kit's HelloWorldItemEditor.tsx,
 * microsoft/fabric-extensibility-toolkit commit dacab1b, MIT, Copyright (c) Microsoft Corporation).
 *
 * Inside Fabric's frame: one ribbon whose first tab is Home, Fluent UI, and the item is only ever created through
 * Fabric's own create dialog (createItemDialogConfig in the manifest); this editor opens on an item that exists.
 * Views: empty state (choose a lakehouse) -> review -> choose outputs -> preview (dry run) -> result.
 * Re-opening an item re-plans with the saved review.json as `previous`, so decisions carry over.
 */
import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { NotificationType } from "@ms-fabric/workload-client";
import {
  ArrowClockwise24Regular,
  ArrowLeft24Regular,
  ArrowRight24Regular,
  Database24Regular,
  Open24Regular,
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
  ReviewStatus,
  decide,
  defaultApiName,
  emptyDefinition,
  fromParts,
  toParts,
} from "./ModelItemDefinition";
import { Busy, EmptyView, ErrorBar, OutputsView, PreviewView, ResultView, ReviewView } from "./ModelItemViews";

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
  const [apiName, setApiName] = useState("");
  const [answer, setAnswer] = useState<{ summary?: string; attention?: string[] }>({});
  const [preview, setPreview] = useState<engine.BuildAnswer>();
  const [result, setResult] = useState<engine.BuildAnswer>();
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

  async function plan(d: ModelDefinition) {
    const a = await runEngine("Reading the lakehouse and finding keys and relationships…", () =>
      engine.review(workloadClient, sourceRequest(d), d.review)
    );
    if (!a) return;
    setAnswer({ summary: a.summary, attention: a.attention });
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
        setApiName(loaded.outputs.outputs[0]?.name ?? defaultApiName(loaded.source?.displayName ?? got.item.displayName));
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
    setApiName(defaultApiName(picked.displayName));
    setDirty(true);
  }

  function onDecide(id: string, status: ReviewStatus) {
    setDef((d) => ({ ...d, review: decide(d.review, id, status) }));
    setDirty(true);
  }

  async function previewBuild() {
    const d = { ...def, outputs: { ...def.outputs, outputs: [{ type: "graphql" as const, name: apiName, enabled: true, writable: false as const }] } };
    setDef(d);
    const a = await runEngine("Preparing the dry run…", () => engine.build(workloadClient, sourceRequest(d), apiName, d.review, true));
    if (!a) return;
    setPreview(a);
    go("preview");
  }

  async function create() {
    const a = await runEngine("Creating the API for GraphQL…", () => engine.build(workloadClient, sourceRequest(def), apiName, def.review, false));
    if (!a) return;
    setResult(a);
    const d = { ...def, item: { ...def.item, view: "result" as const }, outputs: { ...def.outputs, created: a.created ?? [] } };
    setDef(d);
    setView?.("result");
    await save(d);
  }

  async function openCreated() {
    const c = result?.created?.[0] ?? def.outputs.created[0];
    if (c) await navigateToItem(workloadClient, { id: c.id, workspaceId: c.workspace, type: "GraphQLApi", displayName: c.name } as never);
  }

  // ---------------------------------------------------------------- ribbon (one sticky ribbon, Home first)
  const homeActions = (): RibbonAction[] => {
    const back: Partial<Record<ModelView, ModelView>> = { review: "empty", outputs: "review", preview: "outputs" };
    const actions: RibbonAction[] = [createSaveAction(() => save(), !dirty || !itemMeta)];
    actions.push({ key: "choose-source", icon: Database24Regular, label: "Choose source", onClick: () => go("empty") });
    if (view === "review") {
      actions.push({ key: "refresh", icon: ArrowClockwise24Regular, label: "Refresh plan", onClick: () => plan(def), disabled: !!busy });
      actions.push({ key: "next", icon: ArrowRight24Regular, label: "Next", onClick: () => go("outputs") });
    }
    if (view === "preview") actions.push({ key: "create", icon: Play24Regular, label: "Create", onClick: create, disabled: !!busy });
    if (view === "result") actions.push({ key: "open", icon: Open24Regular, label: "Open item", onClick: openCreated });
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
          <ReviewView source={def.source} review={def.review} summary={answer.summary} attention={answer.attention} onDecide={onDecide} />
        ) : null
      ),
    },
    { name: "outputs", component: wrap(<OutputsView name={apiName} onNameChange={setApiName} onPreview={previewBuild} />) },
    { name: "preview", component: wrap(preview ? <PreviewView answer={preview} onCreate={create} /> : null) },
    { name: "result", component: wrap(result ? <ResultView answer={result} onOpen={openCreated} /> : null) },
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
