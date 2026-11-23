"""BL44 (issue #104), 23 November 2026: the guided path's state survives a second replica.

Two "replicas" are two copies of fabric_backend.flow_state loaded separately, sharing nothing but one store
(registration_store.MemoryStore stands in for the Table Storage both hosted replicas use). The same taps, landing on
either replica in turn, give the same state as one replica alone; a write that meets the other replica's newer write
retries instead of undoing it; without a shared store nothing changes (memory, as before)."""
import importlib.util
import sys

import pytest

from fabric_backend import flow_state, registration_store as rs

WHO, WS, SRC, SCHEMA = "u1", "ws", "shop_lh", "shop"
ACC = {"item": "rel:orders.customer_id>customers", "review": "accepted"}
REJ = {"item": "rel:orders.customer_id>customers", "review": "rejected"}
KEY = {"item": "key:orders", "review": "rejected"}
LINK = [{"source": "orders", "source_cols": ["customer_id"], "target": "customers", "target_cols": ["customer_id"]}]


def replica(name):
    """A fresh copy of the module: its own memory, its own lock, nothing shared with the others."""
    spec = importlib.util.find_spec("fabric_backend.flow_state")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"_replica_{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


def taps(on):
    """Accept, Reject, Accept on the link and Reject on a key, each tap on the replica `on(i)` gives."""
    seq = [(ACC, True), (REJ, True), (ACC, True), (KEY, True)]
    out = None
    for i, (d, tapped) in enumerate(seq):
        out = on(i).record(WHO, WS, SRC, SCHEMA, "decide", [d], LINK, tapped)
    return out


@pytest.fixture
def store():
    s = rs.MemoryStore()
    yield s
    flow_state.use_store(None)


def _final(view):
    return sorted((d["item"], d["review"]) for d in view["decisions"]), view["confirmed"]


def test_two_replicas_replay_the_taps_to_the_same_state_as_one(store):
    one = replica("one")
    one.use_store(None)
    alone = _final(taps(lambda i: one))
    a, b = replica("a"), replica("b")
    a.use_store(store)
    b.use_store(store)
    together = _final(taps(lambda i: (a, b)[i % 2]))
    assert together == alone == ([("key:orders", "rejected"), ("rel:orders.customer_id>customers", "accepted")], LINK)
    assert _final(b.state(WHO, WS, SRC, SCHEMA)) == alone                         # the other replica reads the same
    assert a.rejected(WHO, WS, SRC, SCHEMA) == {"key:orders"} == b.rejected(WHO, WS, SRC, SCHEMA)


def test_an_older_card_on_the_other_replica_does_not_undo_a_newer_tap(store):
    a, b = replica("a2"), replica("b2")
    a.use_store(store)
    b.use_store(store)
    a.record(WHO, WS, SRC, SCHEMA, "decide", [REJ], LINK, True)                    # the newest tap: rejected
    b.record(WHO, WS, SRC, SCHEMA, "outputs", [ACC], LINK, False)                  # an older card's arguments: accepted
    assert a.rejected(WHO, WS, SRC, SCHEMA) == {"rel:orders.customer_id>customers"}


class RacingStore(rs.MemoryStore):
    """Another replica writes between this replica's read and its write, once."""
    def __init__(self, other):
        super().__init__()
        self.other, self.raced = other, False

    def replace(self, kind, key, data, etag, ttl=None):
        if not self.raced:
            self.raced = True
            self.other()
        return super().replace(kind, key, data, etag, ttl)


def test_a_write_that_meets_the_other_replicas_write_retries_and_keeps_both():
    holder = {}
    s = RacingStore(lambda: holder["b"].record(WHO, WS, SRC, SCHEMA, "decide", [KEY], LINK, True))
    a, b = replica("a3"), replica("b3")
    a.use_store(s)
    b.use_store(s)
    holder["b"] = b
    a.record(WHO, WS, SRC, SCHEMA, "decide", [ACC], LINK, True)                    # creates the record
    a.record(WHO, WS, SRC, SCHEMA, "decide", [REJ], LINK, True)                    # b writes KEY in between: retried
    got = dict((d["item"], d["review"]) for d in b.state(WHO, WS, SRC, SCHEMA)["decisions"])
    assert got == {"rel:orders.customer_id>customers": "rejected", "key:orders": "rejected"}


def test_the_record_holds_names_and_decisions_only(store):
    a = replica("a4")
    a.use_store(store)
    a.record(WHO, WS, SRC, SCHEMA, "decide", [ACC], LINK, True)
    (key,) = [k for (kind, k) in store._rows if kind == "flow"]
    assert key.startswith("flow-") and WS not in key and SRC not in key and WHO not in key       # a hash, not the names
    data = store.get("flow", key)[0]
    assert set(data) == {"decisions", "step", "seq", "n"}


def test_without_a_shared_store_it_is_memory_as_before(monkeypatch):
    monkeypatch.delenv("KRUSGRAPH_REGISTRATION_STORE", raising=False)
    m = replica("m")
    assert m._shared() is None
    m.record(WHO, WS, SRC, SCHEMA, "decide", [REJ], LINK, True)
    assert m.rejected(WHO, WS, SRC, SCHEMA) == {"rel:orders.customer_id>customers"}
    assert replica("m2").state(WHO, WS, SRC, SCHEMA) is None                       # another process: nothing shared
