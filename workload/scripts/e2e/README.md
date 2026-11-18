# The Model editor, end to end (W13)

The real Krusgraph Model editor (`ModelItemEditor`) runs in Chromium with a stand-in Fabric host (`harness.tsx`). It
calls the real `/workload/v1` routes, which `engine.py` serves on `tests/golden_support.py`'s Fabric and SQL doubles
(the golden workspace, lakehouse `demo_lh`, and `seed.py`'s synthetic shop rows). No tenant, no secret, no network.
`run.js` walks every flow and writes a screenshot per step and `results.json` (pass or fail, with evidence).

From the repository root (needs the test extras in the Python you pass, and `npm ci` in `workload/Workload`):

```sh
node workload/scripts/e2e/run.js <out dir> --python <python>            # this branch
node workload/scripts/e2e/run.js <out dir> --python <python> --before   # the same steps on an older editor (no W13 checks)
```

| Scenario (`POST /e2e/scenario`) | What the doubles do |
| --- | --- |
| `shop` | the golden workspace (default); the schema `dbo` exists and has no tables |
| `forbidden` | Fabric answers 403 to every workspace read |
| `big` | `shop` has 240 more tables (247 tables, 493 suggestions) |

W14 adds two flows at phone width (390 px), on a context of their own: **18** a decision in the review is saved
without Save (one more `updateItemDefinition`, the line says `✓ Saved hh:mm UTC` in a `role="status"` region, no
horizontal scroll), and **19** a decision made in a tab that is closed while its save is still on its way
(`?slowsave=60000`) comes back on the next opening, with the note "Recovered changes from …", and is saved then. The
autosave itself is `Workload/app/items/ModelItem/autosave.ts` (unit tests in `autosave.test.ts` and, in the real editor,
`autosave.editor.test.tsx`, which also covers another session's save in the meantime and a save Fabric refuses).

WB10 adds flow **20**: the editor inside `frame.html`, an iframe with Fabric's default sandbox (`allow-same-origin
allow-scripts`: no `allow-downloads`, no `allow-popups`; Microsoft Learn, "How to relax the iFrame", ms.date 12/15/2025).
A `data:` link with `download` clicked in the frame saves nothing there, as in Fabric (Gustav's live test, 18 Nov 2026).
**Download as draw.io** then goes through the engine's single-use link (`POST /workload/v1/file`), which the stand-in
host's `openBrowserTab` hands to the top frame to open, as Fabric's host does: one `.drawio` file is saved, and a second
GET of the same link answers 410. Flow **21**: the Data Science starter's **Dry run** says what would be created
and that Krusgraph trains no model; **Create** sends one notebook to the doubles (#64).

A network failure is made in the browser (`page.route(...).abort()`). What the doubles cannot show: a data agent
(the double has no route for it, so its card shows Try again), real Fabric ids (Look for leftovers expects GUIDs),
Fabric's own frame (the iframe's width, theme, the picker's look). `tests/test_w13_workload_e2e.py` checks the scenarios
without a browser.
