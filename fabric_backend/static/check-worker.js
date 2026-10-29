// /check's engine: Pyodide (the Python runtime, served from /static/pyodide/) running fabric_backend.browser_check, the
// same Python the hosted service runs (served as /check/engine.zip). Files come in as bytes from the page, are written to
// Pyodide's in-memory file system and read there; nothing is sent anywhere. Each step the engine finishes is posted to
// the page as it happens. Served at /check/worker.js with a Content-Security-Policy whose connect-src allows only those
// two paths on this host.
import { loadPyodide } from "/static/pyodide/pyodide.mjs";

const ENGINE = "/check/engine.zip?v=" + (new URL(self.location.href).searchParams.get("e") || "");
const SQLITE = "/static/pyodide/sqlite3-1.0.0-cp312-cp312-pyodide_2024_0_wasm32.whl";
let ready = null;
const step = (id, s) => self.postMessage({ id, step: s });

async function boot(id) {
  let t = performance.now();
  const py = await loadPyodide({ indexURL: "/static/pyodide/", stdout: () => {}, stderr: () => {} });
  step(id, { step: "runtime", title: "Python runtime", detail: "Pyodide " + py.version + " (CPython in WebAssembly) started in this browser", ms: Math.round(performance.now() - t) });
  t = performance.now();
  const [, zip] = await Promise.all([py.loadPackage(SQLITE, { messageCallback: () => {} }),
                                     fetch(ENGINE).then((r) => { if (!r.ok) throw new Error("engine " + r.status); return r.arrayBuffer(); })]);
  py.FS.writeFile("/engine.zip", new Uint8Array(zip));
  const n = py.runPython("import sys, zipfile\n_z = zipfile.ZipFile('/engine.zip')\n_z.extractall('/engine')\nsys.path.insert(0, '/engine')\n"
                         + "import fabric_backend.browser_check\nlen([x for x in _z.namelist() if x.endswith('.py')])");
  step(id, { step: "engine", title: "The engine", detail: n + " Python files of fabric_backend (infer.py, schema.py, evidence.py, graphs.py…) and sqlite3 loaded", ms: Math.round(performance.now() - t) });
  return py;
}

self.onmessage = async (event) => {
  const { id, kind, files, text } = event.data || {};
  try {
    const py = await (ready = ready || boot(id));
    if (kind === "boot") { self.postMessage({ id, ok: true }); return; }
    if (kind === "build") {                  // n49: the Power BI model and the app from the same input, previews and zips
      py.runPython("import os, shutil\nshutil.rmtree('/upload', ignore_errors=True)\nos.makedirs('/upload')");
      (files || []).forEach((f, i) => py.FS.writeFile("/upload/" + i, new Uint8Array(f.bytes)));
      py.globals.set("build_args", py.toPy({ input: event.data.input, names: (files || []).map((f) => f.name), text: text || "" }));
      const built = py.runPython(
        "import json, shutil\nfrom fabric_backend.browser_build import build\n_b = build_args\n"
        + "_bf = [(n, open('/upload/%d' % i, 'rb').read()) for i, n in enumerate(_b['names'])]\n"
        + "shutil.rmtree('/upload', ignore_errors=True)\njson.dumps(build(_b['input'], _bf, _b['text']), default=str)");
      self.postMessage({ id, ok: true, result: JSON.parse(built) });
      return;
    }
    py.runPython("import os, shutil\nshutil.rmtree('/upload', ignore_errors=True)\nos.makedirs('/upload')");
    const names = [];
    (files || []).forEach((f, i) => { py.FS.writeFile("/upload/" + i, new Uint8Array(f.bytes)); names.push(f.name); });
    py.globals.set("check_args", py.toPy({ kind, names, text: text || "" }));
    py.globals.set("check_emit", (s) => step(id, JSON.parse(s)));
    const out = py.runPython(
      "import json, shutil\nfrom fabric_backend.browser_check import analyze\n"
      + "_a = check_args\n_files = [(n, open('/upload/%d' % i, 'rb').read()) for i, n in enumerate(_a['names'])]\n"
      + "shutil.rmtree('/upload', ignore_errors=True)\n"
      + "json.dumps(analyze(_a['kind'], _files, _a['text'], emit=lambda e: check_emit(json.dumps(e, default=str))), default=str)");
    self.postMessage({ id, ok: true, result: JSON.parse(out) });
  } catch (e) {
    self.postMessage({ id, ok: false, error: String((e && e.message) || e).split("\n").slice(-3).join(" ") });
  }
};
