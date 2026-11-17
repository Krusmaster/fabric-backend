// W14: autosave's pure parts: the revision, the three-way merge of decisions, the draft in this browser, the words.
import { describe, expect, it } from "vitest";
import {
  DRAFT_MAX_AGE_MS, DRAFT_PREFIX, DraftStore, clearDraft, conflictWords, decisionsOf, indicatorWords, mergeDecisions,
  readDraft, recover, recoveredWords, resolve, revisionOf, stamp, writeDraft,
} from "./autosave";
import { ModelDefinition, ReviewFile, ReviewStatus, emptyDefinition, fromParts, toParts } from "./ModelItemDefinition";

const review = (statuses: Record<string, ReviewStatus>): ReviewFile => ({
  format: "krusgraph-review", version: 3, plan_id: "p1", source: { schema: "dbo" },
  items: Object.entries(statuses).map(([id, s]) => ({ id, type: "key", rule: "K1", columns: ["id"], table: id, review: s })),
});
const def = (statuses: Record<string, ReviewStatus>, rev?: number): ModelDefinition => {
  const d = emptyDefinition();
  return { ...d, review: review(statuses), item: { ...d.item, view: "review", ...(rev ? { saved: { rev, at: "2026-11-17T10:00:00.000Z", session: "other" } } : {}) } };
};
const status = (r: ReviewFile | undefined, id: string) => r?.items.find((x) => x.id === id)?.review;

class MemStore implements DraftStore {
  m = new Map<string, string>();
  getItem(k: string) { return this.m.get(k) ?? null; }
  setItem(k: string, v: string) { this.m.set(k, v); }
  removeItem(k: string) { this.m.delete(k); }
}
class Blocked implements DraftStore {
  getItem(): string { throw new Error("SecurityError"); }
  setItem(): void { throw new Error("SecurityError"); }
  removeItem(): void { throw new Error("SecurityError"); }
}

describe("the revision in item.json", () => {
  it("an older definition without one reads as revision 0, and each save is one more", () => {
    const d = def({ a: "proposed" });
    expect(revisionOf(d)).toBe(0);
    const s = stamp(d, 0, "abc", new Date("2026-11-17T12:00:00Z"));
    expect(s.item.saved).toEqual({ rev: 1, at: "2026-11-17T12:00:00.000Z", session: "abc" });
    expect(revisionOf(stamp(s, 4, "abc"))).toBe(5);
  });

  it("survives the round trip through Fabric's parts and is dropped when malformed", () => {
    const s = stamp(def({ a: "accepted" }), 2, "abc");
    expect(fromParts(toParts(s)).item.saved?.rev).toBe(3);
    const bad = { ...s, item: { ...s.item, saved: { rev: "x" } as never } };
    expect(fromParts(toParts(bad)).item.saved).toBeUndefined();
  });
});

describe("merging with another session's save", () => {
  const base = decisionsOf(review({ a: "proposed", b: "proposed", c: "proposed" }));

  it("keeps their decision on an item this session did not touch, and this session's own", () => {
    const local = review({ a: "accepted", b: "proposed", c: "proposed" });
    const remote = review({ a: "proposed", b: "rejected", c: "proposed" });
    const m = mergeDecisions(base, local, remote);
    expect([status(m.review, "a"), status(m.review, "b"), status(m.review, "c")]).toEqual(["accepted", "rejected", "proposed"]);
    expect(m.kept).toEqual(["b"]);
    expect(m.overwritten).toEqual([]);
  });

  it("where both changed the same item, this session's decision wins and is counted", () => {
    const m = mergeDecisions(base, review({ a: "accepted", b: "proposed", c: "proposed" }), review({ a: "rejected", b: "proposed", c: "proposed" }));
    expect(status(m.review, "a")).toBe("accepted");
    expect(m.overwritten).toEqual(["a"]);
  });

  it("the same decision on both sides is no conflict", () => {
    const m = mergeDecisions(base, review({ a: "accepted", b: "proposed", c: "proposed" }), review({ a: "accepted", b: "proposed", c: "proposed" }));
    expect(m.kept).toEqual([]);
    expect(m.overwritten).toEqual([]);
  });

  it("resolve: nothing to merge when Fabric has no newer revision", () => {
    const local = def({ a: "accepted" });
    const r = resolve(local, base, 3, def({ a: "rejected" }, 3));
    expect(r.def).toBe(local);
    expect(r.conflict).toBeUndefined();
    expect(r.baseRev).toBe(3);
  });

  it("resolve: a newer revision is merged, saved on top of it, and said in words", () => {
    const r = resolve(def({ a: "accepted", b: "proposed", c: "proposed" }), base, 1, def({ a: "proposed", b: "rejected", c: "proposed" }, 4));
    expect(r.baseRev).toBe(4);
    expect(status(r.def.review, "b")).toBe("rejected");
    expect(revisionOf(stamp(r.def, r.baseRev, "me"))).toBe(5);
    expect(conflictWords(r.conflict!)).toMatch(/Someone else saved this item at 10:00 UTC\. Their decision on 1 item you had not changed was kept\./);
  });

  it("resolve: Thinker's answers from both sides are kept, this session's first", () => {
    const local = def({ a: "proposed" });
    local.item.answers = { x: "keep" };
    const remote = def({ a: "proposed" }, 2);
    remote.item.answers = { y: "keep", x: "other" };
    expect(resolve(local, {}, 0, remote).def.item.answers).toEqual({ x: "keep", y: "keep" });
  });
});

describe("the draft in this browser", () => {
  const ITEM = "33333333-3333-3333-3333-333333333333";

  it("is written, read and cleared per item", () => {
    const st = new MemStore();
    expect(writeDraft(st, ITEM, def({ a: "accepted" }), 2, base0())).toBe(true);
    expect([...st.m.keys()]).toEqual([DRAFT_PREFIX + ITEM]);
    expect(readDraft(st, ITEM)?.baseRev).toBe(2);
    expect(readDraft(st, "another")).toBeUndefined();
    clearDraft(st, ITEM);
    expect(readDraft(st, ITEM)).toBeUndefined();
  });

  it("a blocked storage is no error: autosave goes on without recovery", () => {
    expect(writeDraft(new Blocked(), ITEM, def({}), 0, {})).toBe(false);
    expect(readDraft(new Blocked(), ITEM)).toBeUndefined();
    expect(() => clearDraft(new Blocked(), ITEM)).not.toThrow();
    expect(writeDraft(undefined, ITEM, def({}), 0, {})).toBe(false);
  });

  it("an old or broken draft is dropped", () => {
    const st = new MemStore();
    writeDraft(st, ITEM, def({}), 0, {}, new Date("2026-11-01T00:00:00Z"));
    expect(readDraft(st, ITEM, new Date(Date.parse("2026-11-01T00:00:00Z") + DRAFT_MAX_AGE_MS + 1))).toBeUndefined();
    expect(st.m.size).toBe(0);
    st.setItem(DRAFT_PREFIX + ITEM, "{not json");
    expect(readDraft(st, ITEM)).toBeUndefined();
  });

  it("recover: nothing when the draft is what Fabric has (only the stamp differs)", () => {
    const st = new MemStore();
    const inFabric = def({ a: "accepted" }, 3);
    writeDraft(st, ITEM, { ...inFabric, item: { ...inFabric.item, saved: undefined } }, 3, {});
    expect(recover(readDraft(st, ITEM), inFabric)).toBeUndefined();
  });

  it("recover: decisions made before a reload come back when Fabric did not get them", () => {
    const st = new MemStore();
    const inFabric = def({ a: "proposed", b: "proposed" }, 3);
    writeDraft(st, ITEM, def({ a: "accepted", b: "proposed" }), 3, decisionsOf(inFabric.review), new Date("2026-11-17T09:41:00Z"));
    const r = recover(readDraft(st, ITEM, new Date("2026-11-17T10:00:00Z")), inFabric)!;
    expect(status(r.def.review, "a")).toBe("accepted");
    expect(r.baseRev).toBe(3);
    expect(r.conflict).toBeUndefined();
    expect(recoveredWords(r)).toBe("Recovered changes from 09:41 UTC that were not saved in Fabric yet; they are being saved now.");
  });

  it("recover: a draft older than Fabric's copy is merged with it", () => {
    const st = new MemStore();
    const was = def({ a: "proposed", b: "proposed" }, 1);
    writeDraft(st, ITEM, def({ a: "accepted", b: "proposed" }), 1, decisionsOf(was.review));
    const r = recover(readDraft(st, ITEM), def({ a: "proposed", b: "rejected" }, 2))!;
    expect([status(r.def.review, "a"), status(r.def.review, "b")]).toEqual(["accepted", "rejected"]);
    expect(r.baseRev).toBe(2);
    expect(r.conflict?.kept).toBe(1);
  });
});

describe("the indicator's words", () => {
  it("every state has a mark that is not a colour", () => {
    expect(indicatorWords("pending")).toMatchObject({ mark: "•", tone: "wait" });
    expect(indicatorWords("saving")).toEqual({ mark: "…", tone: "wait", words: "Saving…" });
    expect(indicatorWords("saved", "2026-11-17T14:05:09Z")).toEqual({ mark: "✓", tone: "ok", words: "Saved 14:05 UTC" });
    expect(indicatorWords("failed", undefined, 4).words).toMatch(/after 4 tries\. Your changes are kept in this browser; Save again\./);
    expect(indicatorWords("idle").words).toBe("Saved");
  });
});

function base0() {
  return decisionsOf(review({ a: "proposed" }));
}
