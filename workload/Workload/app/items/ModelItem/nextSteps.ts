/**
 * W13: next steps with other Fabric workloads, once Krusgraph has proven the keys and links on the rows.
 *
 * The founder, 16 November 2026, on Fabric's Data Science workload page: after Krusgraph has proven the keys, links and
 * amounts, the item should suggest what to do next with the other workloads, built on the proven model. Pure functions,
 * no React and no AI: every suggestion is a rule over what the review's check counted (review.json: each key's rows and
 * distinct values, each link's rows with a value and orphans) and what this item already built (outputs.json).
 *
 * Each suggestion says in one line why it fits, and does one of three things, never more than Krusgraph can:
 *   build    ticks outputs the editor already builds (buildWords.KINDS) and opens Choose what to build, so the dry run
 *            comes first, as for any output
 *   starter  hands over a file made here from the proven model (a Data Science notebook, .ipynb), for the person to
 *            import and run; Krusgraph creates nothing for it
 *   ask      a sentence to ask Krusgraph in Claude, where the tool exists (the drift monitor)
 * and anything else is marked "guide only", with a link to Microsoft's page.
 */
import type { CreatedItem, ReviewFile, ReviewItem } from "./ModelItemDefinition";
import type { OutputKind } from "./engineClient";

/** Fabric's workloads, as Fabric names them (the Workload hub). */
export type Workload =
  | "Data Science" | "Data Engineering" | "Data Factory" | "Power BI" | "Real-Time Intelligence" | "Fabric IQ" | "Data agent" | "Apps";

export type How =
  | { kind: "build"; outputs: OutputKind[]; label: string }
  /** WB10 (#64): `name` and `cells` let the card create the notebook in the workspace (a dry run, then Create) */
  | { kind: "starter"; label: string; filename: string; mime: string; content: string; code: string; name: string; cells: string[] }
  | { kind: "ask"; label: string; text: string }
  | { kind: "guide"; label: string; url: string };

export interface NextStep {
  id: string;
  workload: Workload;
  title: string;
  /** one line: why it fits what was proven */
  why: string;
  how: How;
  /** what Krusgraph does: builds it (after a dry run), hands over a starter, a request for Claude, or guide only */
  status: "builds" | "starter" | "in Claude" | "guide only";
  /** a second, short line: what it does not do */
  note?: string;
}

/** A link proven on the rows whose source has more rows than its target: summing over it repeats the target's rows. */
export interface Grain {
  child: string;
  parent: string;
  childColumns: string[];
  parentColumns: string[];
  childKey: string[];
  /** every column of the child that is a key or a link (never summed: summing ids means nothing) */
  childIds: string[];
  childRows: number;
  parentRows: number;
  /** childRows / parentRows, rounded to one decimal */
  ratio: number;
  /** the child's key holds the link's columns (order_items keyed on order_id + line_no): lines of a header */
  lines: boolean;
}

export interface Proof {
  keysPassed: number;
  keysChecked: number;
  linksPassed: number;
  linksChecked: number;
  /** rows counted in the tables whose key was checked */
  rows: number;
  tables: number;
  orphans: number;
  duplicates: number;
  checkedAt?: string;
  grains: Grain[];
}

const num = (x: unknown): number => (typeof x === "number" && Number.isFinite(x) ? x : 0);
const passed = (it: ReviewItem) => it.check?.status === "passed";
const checked = (it: ReviewItem) => it.check?.status === "passed" || it.check?.status === "failed";

/** What the review's check proved, counted from review.json alone. */
export function proofOf(review: ReviewFile | undefined): Proof {
  const items = (review?.items ?? []).filter((it) => it.review !== "rejected");
  const keys = items.filter((it) => it.type === "key");
  const links = items.filter((it) => it.type === "relationship");
  const keyOf = new Map(keys.map((k) => [k.table ?? "", k]));
  let rows = 0, tables = 0, duplicates = 0, orphans = 0;
  let checkedAt: string | undefined;
  for (const k of keys.filter(checked)) {
    const r = k.check?.result ?? {};
    rows += num(r.rows);
    tables += 1;
    duplicates += Math.max(0, num(r.rows) - num(r.nulls) - num(r.distinct));
  }
  for (const l of links.filter(checked)) orphans += num(l.check?.result?.orphans);
  for (const it of items.filter(checked)) {
    const at = it.check?.checked_at;
    if (at && (!checkedAt || at > checkedAt)) checkedAt = at;
  }
  const grains: Grain[] = [];
  for (const l of links.filter(passed)) {
    const parentKey = keyOf.get(l.target ?? "");
    const childKey = keyOf.get(l.source ?? "");
    const parentRows = num(parentKey?.check?.result?.rows);
    const childRows = num(childKey?.check?.result?.rows) || num(l.check?.result?.rows_with_value);
    if (!parentKey || !passed(parentKey) || parentRows <= 0 || childRows <= parentRows) continue;
    const childCols = childKey?.columns ?? [];
    const childIds = [...new Set([...childCols, ...links.filter((x) => x.source === l.source).flatMap((x) => x.columns)])];
    grains.push({
      childIds,
      child: l.source ?? "", parent: l.target ?? "", childColumns: l.columns, parentColumns: l.target_columns?.length ? l.target_columns : parentKey.columns,
      childKey: childCols, childRows, parentRows, ratio: Math.round((childRows / parentRows) * 10) / 10,
      lines: childCols.length > l.columns.length && l.columns.every((c) => childCols.includes(c)),
    });
  }
  // header and lines first (the classic doubled total), then the link that repeats its target most
  grains.sort((a, b) => Number(b.lines) - Number(a.lines) || b.ratio - a.ratio || a.child.localeCompare(b.child));
  return {
    keysPassed: keys.filter(passed).length, keysChecked: keys.filter(checked).length,
    linksPassed: links.filter(passed).length, linksChecked: links.filter(checked).length,
    rows, tables, orphans, duplicates, checkedAt, grains,
  };
}

const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;

/** The proof in one sentence (Thinker's words): what was counted and what held. */
export function proofLine(p: Proof): string {
  if (!p.keysChecked && !p.linksChecked) return "";
  const parts = [`${p.keysPassed} of ${plural(p.keysChecked, "key")} unique`, `${p.linksPassed} of ${plural(p.linksChecked, "link")} holding`];
  const when = p.checkedAt ? ` (checked ${p.checkedAt.replace("T", " ").replace("Z", " UTC")})` : "";
  return `Proven on the rows${when}: ${parts.join(", ")}, ${plural(p.rows, "row")} counted in ${plural(p.tables, "table")}, ` +
    `${plural(p.orphans, "orphan")}, ${plural(p.duplicates, "duplicate key")}.`;
}

/** The doubled total the proven grain prevents, in one sentence; empty when no link repeats its target. */
export function grainLine(g: Grain | undefined): string {
  if (!g) return "";
  return `${plural(g.childRows, `${g.child} row`)} over ${plural(g.parentRows, `${g.parent} row`)}: an amount on ${g.parent} summed over ` +
    `${g.child} would count each ${g.parent} row ${g.ratio}× on average. Sum ${g.child} per ${g.parent} row first.`;
}

// ------------------------------------------------------------------ the Data Science starter -------------------------

const py = (s: string) => JSON.stringify(s);
const ident = (s: string) => s.replace(/[^A-Za-z0-9_]+/g, "_").replace(/^(\d)/, "_$1").toLowerCase();

/** The notebook's cells (Python, PySpark): a feature table one row per parent, the grain proven, and an Experiment. */
export function featureCells(g: Grain, source: { name: string; schema: string; checkedAt?: string }): string[] {
  const t = (name: string) => py(source.schema ? `\`${source.schema}\`.\`${name}\`` : `\`${name}\``);
  const table = ident(`${g.parent}_features`);
  const experiment = ident(`${g.parent}_experiment`);
  const skip = [...new Set([...g.childColumns, ...g.childKey, ...(g.childIds ?? [])])];
  const rename = g.childColumns.map((c, i) => `${py(c)}: ${py(g.parentColumns[i] ?? c)}`).join(", ");
  return [
    `# Krusgraph starter: a feature table at the grain of ${g.parent} (one row per ${g.parent}), for Data Science.\n` +
      `# Made by rules from the keys and links Krusgraph proved on ${source.name}${source.schema ? ` / ${source.schema}` : ""}` +
      `${source.checkedAt ? ` (checked ${source.checkedAt})` : ""}:\n` +
      `#   ${g.parent}: key ${g.parentColumns.join(" + ")}, unique in all ${g.parentRows} rows\n` +
      `#   ${g.child}.${g.childColumns.join(" + ")} -> ${g.parent}: holds for all ${g.childRows} rows, 0 orphans\n` +
      `#   ${g.childRows} ${g.child} rows over ${g.parentRows} ${g.parent} rows: a ${g.parent} amount summed over ${g.child} counts each ${g.parent} ${g.ratio}x.\n` +
      `# Attach the notebook to the lakehouse ${source.name} and run the cells in order. Nothing is written until cell 3.`,
    `from pyspark.sql import functions as F\nfrom pyspark.sql.types import NumericType\n\n` +
      `parent = spark.read.table(${t(g.parent)})\nchild = spark.read.table(${t(g.child)})\n` +
      `key = ${py(g.parentColumns.join(","))}.split(",")\n\n` +
      `# 1. ${g.child} summed per ${g.parent} first: every numeric column of ${g.child} except its keys and links (ids are not summed)\n` +
      `skip = set(${py(skip.join(","))}.split(","))\n` +
      `numeric = [f.name for f in child.schema.fields if isinstance(f.dataType, NumericType) and f.name not in skip]\n` +
      `per_parent = (child.groupBy(*${py(g.childColumns.join(","))}.split(","))\n` +
      `    .agg(F.count(F.lit(1)).alias(${py(`${ident(g.child)}_rows`)}), *[F.sum(c).alias(f"${ident(g.child)}_{c}_sum") for c in numeric])\n` +
      `    .withColumnsRenamed({${rename}}))\n\n` +
      `# 2. joined once, on the proven key: one row per ${g.parent}\n` +
      `features = parent.join(per_parent, on=key, how="left").fillna(0, subset=[${py(`${ident(g.child)}_rows`)}])\n` +
      `display(features.limit(10))`,
    `# 3. the grain, checked before anything is written: one row per ${g.parent}, so no total is doubled\n` +
      `n_parent, n_features = parent.count(), features.count()\n` +
      `assert n_features == n_parent, f"{n_features} feature rows for {n_parent} ${g.parent} rows: the grain is not one row per ${g.parent}"\n` +
      `assert features.select(*key).distinct().count() == n_features, "the key repeats in the feature table"\n` +
      `features.write.mode("overwrite").format("delta").saveAsTable(${py(table)})\n` +
      `print(f"${table}: {n_features} rows, one per ${g.parent}")`,
    `# 4. optional: an ML Experiment for the runs on this table. In a Fabric notebook, mlflow.set_experiment creates the\n` +
      `#    Experiment item in this workspace if it does not exist (Microsoft Learn, "Machine learning experiment").\n` +
      `import mlflow\nmlflow.set_experiment(${py(experiment)})\n` +
      `with mlflow.start_run(run_name="feature table ${table}"):\n` +
      `    mlflow.log_param("grain", ${py(g.parent)})\n    mlflow.log_param("source", ${py(`${source.name}.${source.schema}`)})\n` +
      `    mlflow.log_metric("rows", n_features)\n` +
      `# Train your model on spark.read.table(${py(table)}) inside a run like this one; Krusgraph does not train or choose a model.`,
  ];
}

/** The cells as a Jupyter notebook (nbformat 4), which Fabric imports (Workspace, Import, Notebook). */
export function toIpynb(cells: string[]): string {
  const lines = (s: string) => s.split("\n").map((l, i, a) => (i < a.length - 1 ? `${l}\n` : l));
  return JSON.stringify({
    nbformat: 4, nbformat_minor: 5,
    metadata: { language_info: { name: "python" }, kernelspec: { name: "synapse_pyspark", display_name: "Synapse PySpark", language: "Python" } },
    cells: cells.map((c, i) => ({ cell_type: "code", id: `krusgraph-${i + 1}`, metadata: {}, execution_count: null as number | null, outputs: [] as unknown[], source: lines(c) })),
  }, null, 1);
}

// ------------------------------------------------------------------ the rules ----------------------------------------

export interface NextInput {
  review?: ReviewFile;
  created: Pick<CreatedItem, "type" | "output" | "name">[];
  source?: { displayName: string; schema: string; itemType?: string };
}

const BUILT_TYPE: Partial<Record<OutputKind, string>> = {
  silver_notebook: "Notebook", gold_views: "Notebook", pipeline: "DataPipeline", semantic_model: "SemanticModel", report: "Report",
  graphql: "GraphQLApi", ontology: "Ontology", data_agent: "DataAgent", rayfin_app: "AppBackend",
};

/** The outputs this item built (by its recorded output, else its Fabric type where one type is one output). WB10:
 * a notebook recorded without its output is told by the default name's suffix (buildWords: "<lakehouse>_silver",
 * "<lakehouse>_gold"), so a built silver notebook is never suggested again. */
export function builtKinds(created: NextInput["created"]): Set<string> {
  const out = new Set<string>();
  for (const c of created) {
    if (c.output) out.add(c.output);
    else if (c.type === "Notebook") {
      const n = (c.name ?? "").toLowerCase();
      if (n.endsWith("_silver")) out.add("silver_notebook");
      else if (n.endsWith("_gold")) out.add("gold_views");
    } else for (const [k, t] of Object.entries(BUILT_TYPE)) if (t === c.type && t !== "Notebook") out.add(k);
  }
  return out;
}

const FACTORY_WORDS: Record<string, [string, string]> = {
  silver_notebook: ["Silver notebook", "silver notebook"], gold_views: ["Gold views", "gold views"], pipeline: ["A pipeline", "a pipeline"],
};

/** WB10 (#63): the Data Factory card says what is left, and what is built: "Gold views and a pipeline; the silver
 * notebook is built". */
export function factoryTitle(left: OutputKind[], done: OutputKind[]): string {
  const say = (ks: OutputKind[], first: boolean) =>
    ks.map((k, i) => FACTORY_WORDS[k][first && i === 0 ? 0 : 1]).join(ks.length > 2 ? ", " : " and ").replace(/, ([^,]+)$/, " and $1");
  const head = say(left, true);
  if (!done.length) return head;
  return `${head}; the ${say(done, false).replace(/^a /, "")} ${done.length > 1 ? "are" : "is"} built`;
}

export const LEARN = {
  activator: "https://learn.microsoft.com/fabric/real-time-intelligence/data-activator/activator-introduction",
  experiment: "https://learn.microsoft.com/fabric/data-science/machine-learning-experiment",
};

/**
 * The next steps, in the order a person would take them, each once: what this item already built is not suggested
 * again. Nothing is suggested before the check has passed for at least one key (the steps build on proven keys).
 */
export function nextSteps(input: NextInput): { proof: Proof; steps: NextStep[]; built: string[]; waiting?: string } {
  const proof = proofOf(input.review);
  const built = builtKinds(input.created);
  if (!proof.keysPassed) {
    return { proof, steps: [], built: [...built], waiting: "Check against the rows first: these steps build on keys and links proven on the rows." };
  }
  const g = proof.grains[0];
  const src = input.source ?? { displayName: "the source", schema: "" };
  const lakehouse = !input.source?.itemType || input.source.itemType === "Lakehouse";
  const held = `${proof.linksPassed} of ${plural(proof.linksChecked, "link")} hold with ${plural(proof.orphans, "orphan")}`;
  const steps: NextStep[] = [];
  const has = (...kinds: OutputKind[]) => kinds.every((k) => built.has(k));

  if (g) {
    const cells = featureCells(g, { name: src.displayName, schema: src.schema, checkedAt: proof.checkedAt });
    const nbName = ident(`${src.displayName}_${g.parent}_features`).slice(0, 123);
    const nbBuilt = built.has("ds_features");
    steps.push({
      id: "ds-features", workload: "Data Science", title: `Feature table at the grain of ${g.parent}, with an Experiment`,
      why: `Your ${g.child} → ${g.parent} link is proven (${plural(g.childRows, "row")}, 0 orphans), so this notebook sums ${g.child} per ` +
        `${g.parent} row first: one row per ${g.parent} row, no total counted ${g.ratio}×.`,
      how: { kind: "starter", label: "Download notebook (.ipynb)", filename: `${ident(g.parent)}_features.ipynb`, mime: "application/x-ipynb+json",
        content: toIpynb(cells), code: cells.join("\n\n# ----\n\n"), name: nbName, cells },
      status: "starter",
      note: nbBuilt
        ? `The notebook is in your workspace: open it and run it. Krusgraph does not run it and trains no model.`
        : "Dry run, then Create puts the notebook in your workspace, attached to the lakehouse; or download it. Krusgraph never runs it and trains no model.",
    });
  }
  if (!has("semantic_model", "report")) {
    const outputs: OutputKind[] = built.has("semantic_model") ? ["report"] : ["semantic_model", "report"];
    steps.push({
      id: "pbi", workload: "Power BI", title: built.has("semantic_model") ? "A report on the semantic model" : "Semantic model and report",
      why: `${held}, so every relationship in the model is many-to-one onto a key proven unique.`,
      how: { kind: "build", outputs, label: "Dry run" }, status: "builds",
    });
  }
  if (!built.has("data_agent")) {
    steps.push({
      id: "agent", workload: "Data agent", title: "A data agent that answers in words",
      why: `Its instructions are written from the ${plural(proof.keysPassed, "key")} and ${plural(proof.linksPassed, "link")} you proved, ` +
        "with example questions to try before anyone relies on it.",
      how: { kind: "build", outputs: ["data_agent"], label: "Dry run" }, status: "builds",
      note: "Left unpublished, a draft only you see, unless you tick Publish.",
    });
  }
  const factory = ["silver_notebook", "gold_views", "pipeline"] as OutputKind[];
  if (lakehouse && factory.some((k) => !built.has(k))) {
    // WB10 (#63): only what is left is ticked in the dry run, and the title says what is built
    const outputs = factory.filter((k) => !built.has(k));
    steps.push({
      id: "factory", workload: "Data Factory", title: factoryTitle(outputs, factory.filter((k) => built.has(k))),
      why: `The keys are unique in all ${plural(proof.rows, "row")} today; the pipeline's check fails a run the day one stops being unique or a link breaks.`,
      how: { kind: "build", outputs, label: "Dry run" }, status: "builds", note: "Not run or scheduled unless you tick it.",
    });
  }
  if (!built.has("graphql")) {
    steps.push({
      id: "api", workload: "Data Engineering", title: "An API for GraphQL",
      why: `Apps can read the tables with the ${plural(proof.linksPassed, "proven link")} as relationships, one query per screen.`,
      how: { kind: "build", outputs: ["graphql"], label: "Dry run" }, status: "builds",
    });
  }
  if (!built.has("ontology") && proof.keysPassed >= 2 && proof.linksPassed >= 1) {
    steps.push({
      id: "iq", workload: "Fabric IQ", title: "An ontology (preview)",
      why: `${plural(proof.keysPassed, "table")} with a proven key become entity types, and the ${plural(proof.linksPassed, "proven link")} the relationships between them.`,
      how: { kind: "build", outputs: ["ontology"], label: "Dry run" }, status: "builds",
    });
  }
  if (lakehouse) {
    steps.push({
      id: "drift", workload: "Real-Time Intelligence", title: "A drift monitor, then an alert",
      why: "What is proven today can change: a nightly monitor reports when a key or link no longer matches the source.",
      how: { kind: "ask", label: "Copy the request for Claude",
        text: `Show a drift monitor for ${src.displayName}${src.schema ? ` (schema ${src.schema})` : ""} as a dry run: run create_drift_monitor with dry_run=true.` },
      status: "in Claude",
      note: "The monitor is a Krusgraph tool in Claude, not in this item. An Activator alert on its result is guide only.",
    });
  }
  if (!built.has("rayfin_app")) {
    steps.push({
      id: "app", workload: "Apps", title: "A Rayfin App (preview)",
      why: `Its list pages and key figures are built over a read-only connector with the ${plural(proof.linksPassed, "proven link")}.`,
      how: { kind: "build", outputs: ["rayfin_app"], label: "Dry run" }, status: "builds",
      note: "Create makes an empty App item and a package with one command; the App opens inside Fabric only.",
    });
  }
  return { proof, steps, built: [...built] };
}
