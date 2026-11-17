/**
 * W13 end-to-end harness: the real Krusgraph Model editor (ModelItemEditor, as App.tsx routes it, inside the
 * EditorErrorBoundary and FluentProvider with the app's theme as index.ui.tsx wraps it) with a stand-in for the Fabric
 * host's workload client. The editor's engine calls go to engine.py on the same origin (the real /workload/v1 routes on
 * the Fabric and SQL doubles). Synthetic data only (seed.py's shop schema).
 *
 * What the stand-in does, and nothing more:
 *   itemCrud     one item ("shop_model") whose definition parts live in localStorage, so a reload is a reopen
 *   datahub      the lakehouse picker answers demo_lh at once (?picker=cancel answers nothing)
 *   auth         a token from engine.py's /e2e/token (the audience the routes accept)
 *   notification, navigation, dialog, settings, theme: recorded in window.__host for run.js to read
 * Query: ?fresh=1 clears the saved item (and W14's unsaved drafts) first; ?slowsave=<ms> makes each save take that long.
 */
import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route } from "react-router-dom";
import { FluentProvider } from "@fluentui/react-components";
import { fabricLightTheme } from "../../Workload/app/theme";
import { ModelItemEditor } from "../../Workload/app/items/ModelItem";
import { EditorErrorBoundary } from "../../Workload/app/items/ModelItem/EditorErrorBoundary";
import { DRAFT_PREFIX } from "../../Workload/app/items/ModelItem/autosave";

const WS = "11111111-2222-3333-4444-555555555555";   // tests/golden_support.py's workspace and lakehouse
const LH = "aaaaaaaa-0000-0000-0000-000000000001";
const ITEM = "33333333-3333-3333-3333-333333333333";
const KEY = "w13-e2e-parts";
const q = new URLSearchParams(location.search);
if (q.get("fresh")) {
  localStorage.removeItem(KEY);
  // W14: and the editor's unsaved drafts (autosave.ts), so a fresh run is not a recovery
  for (const k of Object.keys(localStorage)) if (k.startsWith(DRAFT_PREFIX)) localStorage.removeItem(k);
}

type Host = { notifications: unknown[]; navigations: unknown[]; saves: number; dialogs: unknown[]; tabs: unknown[] };
const host: Host = { notifications: [], navigations: [], saves: 0, dialogs: [], tabs: [] };
(window as unknown as { __host: Host }).__host = host;

const parts = () => JSON.parse(localStorage.getItem(KEY) || "[]");
const wc = {
  itemCrud: {
    getItem: async () => ({ item: { id: ITEM, workspaceId: WS, displayName: "shop_model", type: "Org.Krusgraph.Model", description: "" } }),
    getItemDefinition: async () => ({ definition: { parts: parts() } }),
    updateItemDefinition: async (p: { payload?: { definition?: { parts?: unknown[] } } }) => {
      host.saves += 1;
      const slow = Number(q.get("slowsave") || 0);   // W14: a save still on its way when the tab is closed
      if (slow) await new Promise((r) => setTimeout(r, slow));
      localStorage.setItem(KEY, JSON.stringify(p?.payload?.definition?.parts ?? []));
      return {};
    },
  },
  datahub: {
    openDialog: async () => (q.get("picker") === "cancel" ? { selectedDatahubItem: [] } : {
      selectedDatahubItem: [{ itemObjectId: LH, workspaceObjectId: WS,
        datahubItemUI: { displayName: "demo_lh", fabricItemType: "Lakehouse", description: "" } }],
    }),
    openDatahubWizardDialog: async () => ({}),
  },
  auth: {
    acquireFrontendAccessToken: async () => ({ token: (await (await fetch("/e2e/token")).json()).token }),
  },
  notification: { open: async (n: unknown) => { host.notifications.push(n); return {}; }, hide: async () => ({}) },
  navigation: {
    navigate: async (...a: unknown[]) => { host.navigations.push(a); },
    openBrowserTab: async (a: unknown) => { host.tabs.push(a); },
    onBeforeNavigateAway: async () => undefined,
    onAfterNavigateAway: async () => undefined,
  },
  dialog: { open: async (d: unknown) => { host.dialogs.push(d); return {}; }, close: async () => ({}) },
  settings: { get: async () => ({ currentLanguage: "en-US", currentLocale: "en-US", workloadHostOrigin: location.origin }), onChange: async () => undefined },
  theme: { get: async () => ({ name: "light", tokens: {} }), onChange: async () => undefined },
  action: { onAction: async () => undefined, execute: async () => ({}) },
  state: { sharedState: {} },
};

createRoot(document.getElementById("root")!).render(
  <FluentProvider theme={fabricLightTheme}>
    <MemoryRouter initialEntries={[`/ModelItem-editor/${ITEM}`]}>
      <Route path="/ModelItem-editor/:itemObjectId">
        <EditorErrorBoundary>
          <ModelItemEditor workloadClient={wc as never} />
        </EditorErrorBoundary>
      </Route>
    </MemoryRouter>
  </FluentProvider>
);
