/**
 * n198: a fake outputs.json in every state, and the engine's answers to it, for productWords.test.ts and for the
 * rendered pages the browser test opens (dataProductPage.test.ts writes them to tests/fixtures/n198/). Synthetic shop
 * names only.
 */
import { BuildCard } from "./engineClient";
import { OutputsDefinition } from "./ModelItemDefinition";
import { LeftoversAnswer, RetireAnswer, StatusAnswer, outOfDate } from "./productWords";

export const WS = "0f0f0f0f-0000-4000-8000-000000000001";
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
export const IDS = { silver: id(2), pipe: id(3), model: id(4), report: id(5), agent: id(6), api: id(7), onto: id(8), oldReport: id(9), left: id(21), oldLeft: id(22) };
const plan = { plan_id: "plan-0123abcd", schema_fingerprint: "sha256:abcd", schema: "shop", links: 7 };
const made = (i: string, type: string, name: string, output: string) => ({ id: i, type, name, workspace: WS, output, plan });

export const OUTPUTS: OutputsDefinition = {
  version: 1,
  outputs: [],
  created: [
    made(IDS.silver, "Notebook", "silver_shop", "silver_notebook"),
    made(IDS.pipe, "DataPipeline", "demo_lh_pipeline", "pipeline"),
    made(IDS.model, "SemanticModel", "demo_lh_model", "semantic_model"),
    made(IDS.report, "Report", "demo_lh_report", "report"),
    made(IDS.api, "GraphQLApi", "demo_lh_api", "graphql"),
    made(IDS.onto, "Ontology", "demo_lh_ontology", "ontology"),
  ],
  pending: [{ output: "rayfin_app", type: "AppBackend", name: "demo_lh_app", at: "2026-11-10T09:00:00.000Z" }],
  removed: [{ id: IDS.oldReport, type: "Report", name: "demo_lh_report_2", workspace: WS, output: "report", removed_at: "2026-11-11T08:30:00+00:00", by: "Anna Berg" }],
  last_create: {
    at: "2026-11-10T09:05:00.000Z", item: "demo_model",
    outputs: [
      { output: "silver_notebook", label: "Silver notebook", name: "silver_shop", state: "created" },
      { output: "data_agent", label: "Data agent", name: "demo_lh_agent", state: "failed", reason: "Fabric answered HTTP 403: the data agent needs DataAgent.ReadWrite.All." },
    ],
  },
  pipeline_jobs: {
    runs: [{ run_id: id(30), pipeline_id: IDS.pipe, pipeline: "demo_lh_pipeline", workspace: WS, started: "2026-11-10T09:06:00Z", status: "Succeeded", at: "2026-11-10T09:12:00Z" }],
    schedules: [{ id: id(31), pipeline_id: IDS.pipe, pipeline: "demo_lh_pipeline", workspace: WS, every: "day", at: "06:00", recorded: "2026-11-10" }],
  },
  product: { name: "Shop sales", owner: "Anna Berg (anna@example.com)", owner_set: { at: "2026-11-10T10:00:00Z", by: "Anna Berg" },
    plan: { plan_id: "plan-0123abcd", schema_fingerprint: "sha256:abcd", review_version: 3 }, items: [], domains: [] },
};

export const STATUS: StatusAnswer = {
  you: "Anna Berg",
  people: [{ name: "Anna Berg", type: "User", role: "Admin", upn: "anna@example.com" }, { name: "Sales team", type: "Group", role: "Member" }],
  items: [
    { id: IDS.silver, type: "Notebook", name: "silver_shop", workspace: WS, output: "silver_notebook", state: "built", why: "" },
    { id: IDS.pipe, type: "DataPipeline", name: "demo_lh_pipeline", workspace: WS, output: "pipeline", state: "built", why: "" },
    { id: IDS.model, type: "SemanticModel", name: "demo_lh_model", workspace: WS, output: "semantic_model", state: "built", why: "" },
    { id: IDS.report, type: "Report", name: "demo_lh_report", workspace: WS, output: "report", state: "built", why: "" },
    { id: IDS.api, type: "GraphQLApi", name: "demo_lh_api", workspace: WS, output: "graphql", state: "missing",
      why: "Fabric does not list it in the workspace any more (deleted, or moved outside Krusgraph)." },
    { id: IDS.onto, type: "Ontology", name: "demo_lh_ontology", workspace: WS, output: "ontology", state: "changed_outside", why: "Renamed in Fabric to sales_ontology." },
    { id: null, type: "AppBackend", name: "demo_lh_app", output: "rayfin_app", state: "pending", why: "A Create sent it and has not seen it finish." },
  ],
};

const card = (output: string, label: string, name: string, extra: Partial<BuildCard>): BuildCard =>
  ({ output, label, type: "", name, dry_run: true, would: "create", updates_in_place: true, permissions: { needs: [], missing: [], execute: "" }, ...extra } as BuildCard);
const differs = { status: "different" as const, was: { plan_id: "plan-99999999", schema: "shop", links: 6 }, now: plan,
  words: "built from a different plan (schema shop, 6 links; now shop, 7 links)" };

export const UPDATE_CARDS: BuildCard[] = [
  card("silver_notebook", "Silver notebook", "silver_shop", { already_built: true }),
  card("semantic_model", "Semantic model", "demo_lh_model", { would: "update", built_from: differs, choices: ["update", "new_name"] }),
  card("ontology", "Ontology", "demo_lh_ontology", { would: "update", built_from: differs, confirm_update: "upd-0011223344556677" }),
  card("rayfin_app", "App (Rayfin, preview)", "demo_lh_app", { updates_in_place: false, built_from: differs, choices: ["new_name"] }),
  card("graphql", "API for GraphQL", "demo_lh_api", {}),
  card("report", "Report", "demo_lh_report", { refusal: { error: "The report needs its semantic model first.", kind: "bad_input" } }),
];
export const UPDATES = outOfDate(UPDATE_CARDS);

export const DELETE_DRY_RUN: RetireAnswer = {
  scope: "delete", leftovers: false, dry_run: true, product: "Shop sales", confirm: "ret-0011223344556677",
  words: "4 item(s) would be deleted from Fabric. Type the data product's name, Shop sales, to confirm.",
  keeps: "Krusgraph never deletes a lakehouse, a warehouse, a table or a view's data. The views and tables the notebooks wrote stay in the lakehouse.",
  items: [
    { id: IDS.report, type: "Report", name: "demo_lh_report", workspace: WS, output: "report" },
    { id: IDS.model, type: "SemanticModel", name: "demo_lh_model", workspace: WS, output: "semantic_model" },
    { id: IDS.pipe, type: "DataPipeline", name: "demo_lh_pipeline", workspace: WS, output: "pipeline" },
    { id: IDS.silver, type: "Notebook", name: "silver_shop", workspace: WS, output: "silver_notebook" },
  ],
  refused: [{ id: IDS.api, name: "demo_lh_api", type: "GraphQLApi", why: "Already gone: Fabric does not list it in the workspace.", gone: true }],
};

export const DELETED: RetireAnswer = {
  ...DELETE_DRY_RUN, dry_run: false, confirm: undefined, words: "3 of 4 item(s) deleted from Fabric. The rest say why.",
  results: [
    { id: IDS.report, type: "Report", name: "demo_lh_report", result: "deleted" },
    { id: IDS.model, type: "SemanticModel", name: "demo_lh_model", result: "deleted" },
    { id: IDS.pipe, type: "DataPipeline", name: "demo_lh_pipeline", result: "already_gone" },
    { id: IDS.silver, type: "Notebook", name: "silver_shop", result: "failed", why: "Fabric refused (HTTP 403): deleting needs write permission on the item." },
  ],
  removed: [],
};

export const SOFT_DRY_RUN: RetireAnswer = {
  scope: "soft", leftovers: false, dry_run: true, product: "Shop sales", confirm: "ret-8899aabbccddeeff", refused: [],
  words: "1 schedule(s) would be removed. Nothing is deleted.", keeps: DELETE_DRY_RUN.keeps,
  steps: [
    { id: IDS.pipe, name: "demo_lh_pipeline", type: "DataPipeline", action: "remove_schedule",
      words: "Remove the schedule Krusgraph made on demo_lh_pipeline (day at 06:00); any other schedule on it stays." },
    { id: IDS.agent, name: "demo_lh_agent", type: "DataAgent", action: "manual",
      words: "demo_lh_agent is published. Microsoft documents no API to unpublish a data agent, so Krusgraph does not try." },
  ],
};

export const LEFTOVERS: LeftoversAnswer = {
  unread_models: [],
  leftovers: [
    { id: IDS.left, type: "SemanticModel", name: "demo_lh_model4", workspace: WS, plan_id: "plan-0123abcd", same_plan: true, adopt_ok: true, adopt_why: "", delete_ok: true, why: "" },
    { id: IDS.oldLeft, type: "Report", name: "old_report", workspace: WS, plan_id: "plan-99999999", same_plan: false, adopt_ok: false,
      adopt_why: "Built from another plan than this data product's; Adopt is offered only for the same plan.", delete_ok: true, why: "" },
  ],
};

export const LEFTOVERS_UNREAD: LeftoversAnswer = {
  unread_models: ["their_model"],
  leftovers: LEFTOVERS.leftovers.map((x) => ({ ...x, delete_ok: false, why: "Another Krusgraph Model (their_model) could not be read, so this item may be one of its outputs." })),
};

export const FRESH: OutputsDefinition = { version: 1, outputs: [], created: [made(IDS.silver, "Notebook", "silver_shop", "silver_notebook")] };
