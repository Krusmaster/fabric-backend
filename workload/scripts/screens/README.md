# Model editor screenshots

Screenshots of the Krusgraph Model editor for the website docs, on seed.py's synthetic shop schema. No Fabric tenant is
involved: `harness.tsx` renders the editor's own view components (`workload/Workload/app/items/ModelItem/`) with the
engine's answers, and every image carries the label "Synthetic data (shop schema)".

From the repository root:

```sh
# 1. the engine's answers: /workload/v1/review, /check and /build (dry run) on the Fabric and SQL doubles of
#    tests/golden_support.py; the flow is the dry run's own -> workload/scripts/screens/fixtures/*.json
python workload/scripts/screens/build_fixtures.py

# 2. bundle harness.tsx with esbuild (the .scss compiled with sass), serve it on 127.0.0.1 and photograph each view
#    -> fabric_backend/static/workload-shots/model-{review,outputs,preview-cards,flow}.webp
node workload/scripts/screens/shoot.js
```

Needs the Python package's test extras (`jwt`, `cryptography`, `starlette`), `npm ci` in `workload/Workload`, and
Playwright with Chromium. To look at a view by hand, keep the bundle (comment out the `fs.rmSync` in `shoot.js`) and
open `index.html#review`, `#outputs`, `#preview` or `#flow` from it.

When the editor's views or the engine change, run both steps again. The docs (fabric_backend/offering.py, SHOTS) show
model-review, model-outputs, model-preview-cards and model-flow.

The images are kept as .webp only (the PNG is removed after encoding; `--keep-png` keeps it).
