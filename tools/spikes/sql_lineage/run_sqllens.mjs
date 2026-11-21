// SQL-lineage spike, sqllens side (throwaway; see README.md and docs/spikes/SQL-LINEAGE-SPIKE.md).
// sqllens is a separate open-source project (npm sqllens 1.11.0, MIT); this file only calls its public API.
//
// For every corpus statement: the equality join pairs between base-table columns and the base-table origins of
// each output column. Reads schema.json (written by run_sqlglot.py), writes results/sqllens.json
// (or results/sqllens-raw.json with --raw: no workaround glue, see below).
//
// Out of the box sqllens gives: parse + lower to an IR per dialect, the scope tree (sources per scope, CTEs,
// subqueries, correlated scopes), SelectExpr.joinConditions / where / joins (USING lists), originsOfExpr (any
// expression -> base-table columns, through CTEs and subqueries), lineage per output column, and dbt templating
// (minijinja engine + DbtTemplateProvider). Core extraction written here (both modes): picking the equality
// conjuncts out of ON/WHERE/HAVING and normalising names (origins keep the as-written quoting, `ID` / [ID]).
// Workaround glue (off with --raw): a CallbackSchema matching any lakehouse/schema prefix to the flat demo schema;
// turning USING lists into pairs; and, for T-SQL CREATE VIEW / INSERT / MERGE, which 1.11.0 lowers as "unparsed",
// re-analysing the SELECT found in the CST (the documented escape hatch), or for MERGE a SELECT built from the
// target, the USING source and the ON condition.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SqlSession, Schema, CallbackSchema, DbtTemplateProvider, originsOfExpr } from "sqllens";
import { minijinja } from "sqllens/minijinja";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const RAW = process.argv.includes("--raw");
const VERSION = JSON.parse(fs.readFileSync(path.join(HERE, "node_modules", "sqllens", "package.json"), "utf8")).version;
const DIALECT = { tsql: "tsql", spark: "databricks" };

const flat = JSON.parse(fs.readFileSync(path.join(HERE, "schema.json"), "utf8"));
const byUpper = new Map(Object.entries(flat).map(([t, cols]) =>
  [t.toUpperCase(), Object.entries(cols).map(([name, type]) => ({ name, type }))]));
const schema = RAW ? new Schema(flat) : new CallbackSchema({ resolve: (parts) => byUpper.get(parts.at(-1).toUpperCase()) });

function load() { // the corpus header as spike_corpus.py reads it; only the dialect is needed here
  const dir = path.join(HERE, "corpus");
  return fs.readdirSync(dir).filter((f) => f.endsWith(".sql")).sort().map((f) => {
    const sql = fs.readFileSync(path.join(dir, f), "utf8");
    return { id: f.replace(/\.sql$/, ""), dialect: /^-- dialect:\s*(\w+)/m.exec(sql)[1], sql };
  });
}

const bare = (s) => s.replace(/^[`["]|[`\]"]$/g, "").toUpperCase();
const norm = (o) => `${bare(o.table.at(-1))}.${bare(o.column)}`;
const pair = (a, b) => [a, b].sort().join(" = ");
function* allScopes(scope) { yield scope; for (const c of scope.children ?? []) yield* allScopes(c); }
function* conjuncts(e) { // through AND only, like run_sqlglot.is_join_predicate
  if (!e) return;
  if (e.kind === "binary" && e.op.toLowerCase() === "and") { yield* conjuncts(e.left); yield* conjuncts(e.right); }
  else yield e;
}

function analyseText(text, dialect, glue) {
  const templated = text.includes("{{") && !RAW;
  if (templated) glue.add("minijinja_option");
  const s = SqlSession.create(text, dialect, { schema, ...(templated ? { templating: minijinja(), provider: new DbtTemplateProvider() } : {}) });
  const scopes = [...allScopes(s.scopes.root)];
  const pairs = new Set();
  const one = (expr, sc) => { const o = originsOfExpr(expr, sc, schema); return o.length === 1 ? norm(o[0]) : null; };
  for (const sc of scopes) {
    const b = sc.body;
    if (b?.kind !== "select") continue;
    for (const p of [...(b.joinConditions ?? []), b.where, b.having].flatMap((x) => [...conjuncts(x)])) {
      if (!(p.kind === "binary" && p.op === "=" && p.left.kind === "column" && p.right.kind === "column")) continue;
      const [l, r] = [one(p.left, sc), one(p.right, sc)];
      if (l && r && l.split(".")[0] !== r.split(".")[0]) pairs.add(pair(l, r));
    }
    for (const j of RAW ? [] : b.joins ?? []) { // glue: USING (c1, c2) -> pairs with the first earlier source having c
      if (!j.using || j.source.kind !== "table") continue;
      glue.add("using_pairs");
      const name = (src) => src.relation.parts ?? src.relation.key;
      const earlier = b.from.slice(0, b.from.indexOf(j.source)).filter((f) => f.kind === "table");
      for (const col of j.using) {
        const left = earlier.find((f) => schema.columnsFor(name(f), dialect)?.some((c) => bare(c.name) === bare(col)));
        if (left) pairs.add(pair(`${bare(name(left).at(-1))}.${bare(col)}`, `${bare(name(j.source).at(-1))}.${bare(col)}`));
      }
    }
  }
  const lineage = {};
  for (const c of s.lineage().all) lineage[bare(c.output)] = [...new Set(c.origins.map(norm))].sort();
  return { s, pairs, lineage, unsupported: [...new Set(scopes.flatMap((sc) => sc.body?.unsupported ?? []))] };
}

function findCtx(node, name) { // depth-first search of the antlr CST by context class name
  if (node?.constructor?.name === name) return node;
  for (const c of node?.children ?? []) { const hit = findCtx(c, name); if (hit) return hit; }
  return null;
}
const slice = (text, ctx) => text.slice(ctx.start.start, ctx.stop.stop + 1);

function analyse(item) {
  const glue = new Set(RAW ? [] : ["prefix_schema"]);
  const out = { parse_ok: false, error: null, glue: [], joins: [], lineage: {}, statement: null };
  const dialect = DIALECT[item.dialect];
  try {
    let r = analyseText(item.sql, dialect, glue);
    out.statement = r.s.scopes.statement;
    const syntax = r.s.syntaxDiagnostics;
    out.parse_ok = syntax.length === 0;
    if (syntax.length) out.error = `syntax: ${syntax.length} error(s), first: ${syntax[0].message.slice(0, 120)}`;
    if (r.unsupported.length) out.unsupported = r.unsupported;
    if (!RAW && r.unsupported.includes("unparsed")) { // glue: re-analyse the SELECT inside a T-SQL DDL/DML statement
      const merge = findCtx(r.s.cst, "Merge_statementContext");
      let inner = null;
      if (merge) {
        const alias = merge.children.find((c) => c.constructor.name === "As_table_aliasContext");
        inner = `SELECT 1 FROM ${slice(item.sql, findCtx(merge, "Ddl_objectContext"))} ${alias ? slice(item.sql, alias) : ""}`
          + ` JOIN ${slice(item.sql, findCtx(merge, "Table_sourcesContext"))} ON ${slice(item.sql, findCtx(merge, "Search_conditionContext"))}`;
        glue.add("merge_as_select");
      } else {
        const sel = findCtx(r.s.cst, "Select_statementContext");
        if (sel) { inner = slice(item.sql, sel); glue.add("cst_select_reparse"); }
      }
      if (inner) r = analyseText(inner, dialect, glue);
    }
    out.joins = [...r.pairs].sort();
    out.lineage = /^\s*(--.*\n\s*)*merge\b/i.test(item.sql) ? {} : r.lineage;
  } catch (e) {
    out.error = `exception: ${String(e.message).slice(0, 160)}`;
  }
  out.glue = [...glue];
  return out;
}

const results = Object.fromEntries(load().map((it) => [it.id, analyse(it)]));
const name = RAW ? "sqllens-raw.json" : "sqllens.json";
fs.mkdirSync(path.join(HERE, "results"), { recursive: true });
fs.writeFileSync(path.join(HERE, "results", name), JSON.stringify({ tool: "sqllens", version: VERSION, results }, null, 1) + "\n");
console.log(`wrote results/${name}: ${Object.values(results).filter((r) => r.parse_ok).length}/${Object.keys(results).length} parsed`);
