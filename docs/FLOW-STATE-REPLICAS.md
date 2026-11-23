# Flow state across replicas

Round BL44, 23 November 2026 (issue #104, first part). `fabric_backend/flow_state.py`.

## The problem
The guided path (the start card in Claude) keeps the person's decisions: accepted and rejected links and keys, and the
step last shown. Until this round they were kept in the memory of one server process. The hosted service runs up to two
replicas, so a tap that lands on the other replica found no decisions there, and a dry run on that replica built
with a link the person had rejected.

## The two options, and the choice
1. **Stateless: carry the state in the card's own arguments.** No store. But that is how WB15 started, and it broke:
   an older card's arguments, sent a second after a newer tap, carried an older decision back (issue E of Gustav's
   phone test, 19 November 2026). Making the arguments authoritative again would bring that back.
2. **A store keyed by person and source, shared by the replicas.** The server already has one: the store the client
   registration and the workload's background operations use (`registration_store.py`, Azure Table Storage when
   `KRUSGRAPH_REGISTRATION_STORE` is set). **Chosen.**

## How it works
- One record of kind `flow` per person and (workspace, source, schema). The record key is a SHA-256 hash of those four,
  so no workspace, source or user name is in the key.
- The record holds the decisions (item id, accepted / rejected / skipped, and an accepted link's columns), the step
  last shown, and two counters. Names and decisions only: no row values, no tokens.
- It expires after `TTL` (4 hours), as in memory before.
- Every change reads the record and writes it back with `If-Match` on its ETag. When the other replica wrote in
  between, the write is refused and redone on the newer version (up to six times), so neither replica undoes the
  other's tap. The latest tap still wins, as WB15 decided.
- The sequence numbers are counted per flow, inside the record, so they mean the same on both replicas.
- Without `KRUSGRAPH_REGISTRATION_STORE` (local runs, one replica, tests) the state stays in memory, as before.

## Verified, and how
`tests/test_bl44_flow_state_store.py`: two copies of the module that share nothing but a store (a
`registration_store.MemoryStore` standing in for Table Storage) replay the same taps to the same state as one replica
alone; an older card on the other replica does not undo a newer tap; a write that meets the other replica's write
retries and keeps both; the record holds names and decisions only, under a hashed key; without a shared store it is
memory as before. Not run against Azure Table Storage itself; the store's Table Storage code is the one
`tests/test_client_registration.py` covers.

## Still open in issue #104
The card-fold part (folding the earlier cards once the path moves on) changes the click-through and is for a later
round. Issue #104 stays open until that is done.
