// n189: a test double of the generated src/lib/app-connectors.ts for the screenshot and accessibility checks of the App
// (Rayfin, preview) package (tests/test_n189_rayfin_design.py). It answers the query chain the pages use (select, where,
// orderBy, first, after, groupBy, aggregate, execute, executePaginated) from the shop rows in fake-data.json, and logs
// every query in window.__kgQueries. create, update and delete throw and are logged as mutations: the pages never call them.
import DATA from './fake-data.json';

const log = (window.__kgQueries = window.__kgQueries || []);
const mutations = (window.__kgMutations = window.__kgMutations || []);

function asTime(v) {
  if (v instanceof Date) return v.getTime();
  const t = Date.parse(String(v));
  return Number.isNaN(t) ? NaN : t;
}

function cmp(a, b) {
  if (b instanceof Date || (typeof a === 'string' && /^\d{4}-\d{2}-\d{2}/.test(a) && typeof b !== 'number')) {
    return asTime(a) - asTime(b);
  }
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b));
}

function fieldMatches(value, cond) {
  if (cond === null || typeof cond !== 'object' || cond instanceof Date) return cmp(value, cond) === 0;
  return Object.entries(cond).every(([op, arg]) => {
    if (value === null || value === undefined) return op === 'isNull' ? arg === true : false;
    switch (op) {
      case 'eq': return cmp(value, arg) === 0;
      case 'neq': return cmp(value, arg) !== 0;
      case 'in': return arg.some((a) => cmp(value, a) === 0);
      case 'contains': return String(value).toLowerCase().includes(String(arg).toLowerCase());
      case 'gte': return cmp(value, arg) >= 0;
      case 'gt': return cmp(value, arg) > 0;
      case 'lte': return cmp(value, arg) <= 0;
      case 'lt': return cmp(value, arg) < 0;
      case 'isNull': return arg === false;
      default: throw new Error(`fake connector: unknown filter ${op}`);
    }
  });
}

function matches(row, where) {
  if (!where) return true;
  return Object.entries(where).every(([k, v]) => {
    if (k === 'and') return v.every((w) => matches(row, w));
    if (k === 'or') return v.some((w) => matches(row, w));
    return fieldMatches(row[k], v);
  });
}

function merge(a, b) {
  if (!a || Object.keys(a).length === 0) return b;
  if (!b || Object.keys(b).length === 0) return a;
  return { and: [a, b] };
}

function plain(v) {
  return JSON.parse(JSON.stringify(v ?? null));
}

class Query {
  constructor(entity, state = {}) {
    this.entity = entity;
    this.state = { where: {}, ...state };
  }
  next(patch) { return new Query(this.entity, { ...this.state, ...patch }); }
  select(fields) { return this.next({ select: [...fields] }); }
  where(w) { return this.next({ where: merge(this.state.where, w) }); }
  orderBy(o) { return this.next({ orderBy: o }); }
  first(n) { return this.next({ first: n }); }
  after(c) { return this.next({ after: c }); }
  groupBy(fields) { return this.next({ groupBy: [...fields] }); }
  aggregate(spec) {
    const q = this.next({ aggregate: spec });
    return { execute: () => q.runAggregate() };
  }
  rows() {
    const all = DATA[this.entity];
    if (!all) throw new Error(`fake connector: no entity ${this.entity}`);
    let rows = all.filter((r) => matches(r, this.state.where));
    if (this.state.orderBy) {
      const [[k, dir]] = Object.entries(this.state.orderBy);
      rows = [...rows].sort((a, b) => (dir === 'desc' ? -1 : 1) * cmp(a[k], b[k]));
    }
    return rows;
  }
  record(kind) {
    log.push({ entity: this.entity, kind, ...plain(this.state) });
  }
  page() {
    const rows = this.rows();
    const start = this.state.after ? Number(this.state.after) : 0;
    const n = this.state.first ?? 100;
    const items = rows.slice(start, start + n).map((r) => (this.state.select ? Object.fromEntries(this.state.select.map((k) => [k, r[k]])) : { ...r }));
    return { items, hasNextPage: start + n < rows.length, endCursor: String(start + n) };
  }
  async execute() {
    this.record('rows');
    return this.page().items;
  }
  async executePaginated() {
    this.record('page');
    return this.page();
  }
  async runAggregate() {
    this.record('aggregate');
    const groups = new Map();
    for (const r of this.rows()) {
      const fields = Object.fromEntries((this.state.groupBy ?? []).map((k) => [k, r[k]]));
      const key = JSON.stringify(fields);
      if (!groups.has(key)) groups.set(key, { fields, rows: [] });
      groups.get(key).rows.push(r);
    }
    if (!this.state.groupBy && groups.size === 0) groups.set('{}', { fields: {}, rows: [] });
    return [...groups.values()].map((g) => ({
      fields: g.fields,
      aggregations: Object.fromEntries(Object.entries(this.state.aggregate).map(([name, spec]) => {
        const [[op, col]] = Object.entries(spec);
        const vals = g.rows.map((r) => r[col]).filter((v) => v !== null && v !== undefined);
        const v = op === 'count' ? vals.length : op === 'sum' ? vals.reduce((a, b) => a + Number(b), 0)
          : op === 'min' ? Math.min(...vals) : op === 'max' ? Math.max(...vals) : vals.reduce((a, b) => a + Number(b), 0) / (vals.length || 1);
        return [name, v];
      })),
    }));
  }
}

function entity(name) {
  const q = new Query(name);
  const refuse = (op) => () => {
    mutations.push({ entity: name, op });
    throw new Error(`read-only: ${op} on ${name}`);
  };
  return Object.assign(Object.create(q), {
    create: refuse('create'), update: refuse('update'), delete: refuse('delete'),
    findMany: async () => q.execute(), findFirst: async () => (await q.first(1).execute())[0] ?? null,
  });
}

const connector = new Proxy({}, { get: (_t, name) => (typeof name === 'string' ? entity(name) : undefined) });

export async function getConnectorsClient() {
  return { connectors: new Proxy({}, { get: () => connector }) };
}
