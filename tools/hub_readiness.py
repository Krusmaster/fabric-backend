"""Workload Hub readiness pre-check (round n178, docs/HUB-READINESS.md).

Microsoft's validator (microsoft/fabric-extensibility-toolkit-validator) needs a browser signed in to Fabric and the
workload published to a tenant, so it cannot run in CI. This script runs the part of its checks that need neither:
it reads the validator's own test-case specifications (Testcases_Workload.json, Testcases_Item.json, as data; none of
the validator's code is run or copied) and checks them against what this repository holds:

- ATTESTATION tests: every term the validator searches for (case-insensitive) is in docs/HUB-ATTESTATION.md, with
  {{workloadName}} replaced by the proposed workload name.
- MANIFEST tests: the field the test reads exists in workload/Workload/Manifest/Product.json or the item JSON
  ("product." is Product.json, "artifacts" the item manifests), localized keys resolved through en-US translations.
- LINK tests: HTTPS, the expected domains, and (with --online) an HTTP answer of 200-399.
- IMAGE / IMAGES tests: PNG dimensions against the test's approved dimensions, else the validator's default set.
- MANUAL, UX and MANIFEST_IMAGE_ASSETS tests are listed as "manual": only the founder's run can answer them.

Usage:
  python tools/hub_readiness.py --spec-dir <validator checkout>/specifications/testcases [--online]
         [--workload-name Krusgraph.Modeler] [--stage Preview] [--report out.md]

Exit code 1 only when the attestation draft lacks a term the validator searches for, or the specifications cannot be
read. Manifest gaps are reported, not failed: they are known, and fixing them is workload/ code (HUB-READINESS.md).
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "workload" / "Workload" / "Manifest"
ATTESTATION = ROOT / "docs" / "HUB-ATTESTATION.md"
DEFAULT_DIMS = ["16x16", "20x20", "24x24", "32x32", "40x40", "48x48", "64x64"]  # the validator's ImageValidator default
# Microsoft's requirement 1.3.1 lists these for the license link; the validator's spec checks the domain only in 1.3.2
MARKETPLACE = ["https://azuremarketplace.microsoft.com", "https://appsource.microsoft.com", "https://marketplace.microsoft.com"]


def load_manifest() -> tuple[dict, list[dict], dict]:
    product = json.loads((MANIFEST / "Product.json").read_text(encoding="utf-8"))
    items = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((MANIFEST / "items").glob("*/*.json"))]
    words = json.loads((MANIFEST / "assets" / "locales" / "en-US" / "translations.json").read_text(encoding="utf-8"))
    return product, items, words


def walk_tests(spec: dict):
    def walk(node):
        for value in node.values():
            if isinstance(value, dict) and "testNumber" in value:
                yield value
            elif isinstance(value, dict):
                yield from walk(value)
    yield from walk(spec["testCases"])


def resolve(field: str, product: dict, item: dict | None) -> list:
    """Resolve the validator's field expressions for the shapes it uses; [] when absent."""
    field = field.replace("?.", ".")
    m = re.match(r"artifacts\.find\(a => a\.name === '\{\{itemName\}\}'\)\.(.+)$", field)
    if m:
        return path_values(item or {}, m.group(1))
    m = re.match(r"product\.createExperience\.cards\.find\(c => c\.artifactType === '\{\{itemName\}\}'\)\.(.+)$", field)
    if m:
        cards = [c for c in product.get("createExperience", {}).get("cards", [])
                 if item and c.get("itemType", c.get("artifactType")) == item.get("name")]
        rest = m.group(1)
        inc = re.match(r"availableIn\.includes\('([^']+)'\)$", rest)
        if inc:
            return [inc.group(1) in c.get("availableIn", []) for c in cards]
        out = []
        for c in cards:
            out += path_values(c, rest)
        return out
    m = re.match(r"(.+)\.map\(\w+ => \w+\.(\w+)\)$", field)
    if m:
        return [v.get(m.group(2)) for v in resolve(m.group(1), product, item) for v in (v if isinstance(v, list) else [v])
                if isinstance(v, dict) and v.get(m.group(2))]
    if field.startswith("product."):
        return path_values(product, field[len("product."):])
    if field.startswith("tabs[]"):
        return []  # tabs come from the item editor at run time; not in the files read here
    return []


def path_values(node, path: str) -> list:
    values = [node]
    for part in path.split("."):
        nxt = []
        many = part.endswith("[]")
        key = part[:-2] if many else part
        for v in values:
            if isinstance(v, dict) and key in v:
                got = v[key]
                if many and isinstance(got, list):
                    nxt += got
                else:
                    nxt.append(got)
        values = nxt
    return [v for v in values if v not in (None, "", [], {})]


def png_size(path: Path) -> str | None:
    try:
        head = path.read_bytes()[:24]
    except OSError:
        return None
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h = struct.unpack(">II", head[16:24])
    return f"{w}x{h}"


def fetch_text(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": "krusgraph-hub-readiness"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read(5_000_000).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return None


def check_link(url: str, cfg: dict, online: bool) -> tuple[str, str]:
    if not isinstance(url, str) or not url.startswith("https://"):
        return "not met", f"not an HTTPS URL: {url!r}"
    domains = cfg.get("expectedDomains")
    if cfg.get("field", "").endswith("supportLink.license.url"):
        domains = MARKETPLACE
    if domains and not any(url.startswith(d.rstrip("/")) for d in domains):
        return "not met", f"{url} is not on {', '.join(domains)}"
    if not online:
        return "met (offline)", f"{url} is HTTPS; reachability not checked (--online)"
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "krusgraph-hub-readiness"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            code = resp.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:  # noqa: BLE001 - any network failure is a finding, not a crash
        return "not met", f"{url}: {type(e).__name__}"
    return ("met" if 200 <= code < 400 else "not met"), f"{url}: HTTP {code}"


def run(spec_dir: Path, workload_name: str, stage: str, online: bool) -> tuple[list[tuple], bool]:
    product, items, words = load_manifest()
    attestation = ATTESTATION.read_text(encoding="utf-8").lower() if ATTESTATION.exists() else ""
    rows, attestation_ok = [], True
    cert_urls = path_values(product, "productDetail.supportLink.certification.url")
    hosted = fetch_text(cert_urls[0]) if online and cert_urls else None
    hosted = hosted.lower() if hosted else None
    for kind, fname in (("Workload", "Testcases_Workload.json"), ("Item", "Testcases_Item.json")):
        spec = json.loads((spec_dir / fname).read_text(encoding="utf-8"))
        targets = [None] if kind == "Workload" else items
        for test in walk_tests(spec):
            req = test.get("requirement", {}).get(stage, {}).get("required", False)
            methods = test.get("validation", {}).get("methods", {})
            for item in targets:
                results = []
                for method, body in methods.items():
                    cfg = (body or {}).get("config") or {}
                    if method == "ATTESTATION":
                        terms = [t.replace("{{workloadName}}", workload_name) for t in cfg.get("containsStrings", [])]
                        missing = [t for t in terms if t.lower() not in attestation]
                        if missing:
                            attestation_ok = False
                        results.append(("not met" if missing else "met (draft)",
                                        "missing in the draft: " + ", ".join(missing) if missing
                                        else "draft has: " + ", ".join(terms)))
                        if online:
                            gone = terms if hosted is None else [t for t in terms if t.lower() not in hosted]
                            results.append(("not met" if gone else "met",
                                            f"hosted document at {cert_urls[0] if cert_urls else 'no URL'} lacks: "
                                            + ", ".join(gone) if gone else "hosted document has them"))
                    elif method == "MANIFEST":
                        field = cfg.get("field", "")
                        vals = resolve(field, product, item)
                        if cfg.get("isAssetLocal"):
                            vals = [words.get(v, v) for v in vals]
                        if cfg.get("valueCheckEqual") is not None:
                            ok = bool(vals) and all(v == cfg["valueCheckEqual"] for v in vals)
                        else:
                            ok = bool(vals) or cfg.get("required") is False
                        shown = "; ".join(str(v)[:80] for v in vals) or "absent"
                        results.append(("met" if ok else "not met", f"{field} = {shown}"))
                    elif method == "LINK":
                        for url in resolve(cfg.get("field", ""), product, item) or [None]:
                            results.append(check_link(url, cfg, online))
                    elif method in ("IMAGE", "IMAGES"):
                        dims = cfg.get("approvedDimensions") or DEFAULT_DIMS
                        refs = resolve(cfg.get("field", ""), product, item)
                        if not refs:
                            results.append(("unknown", f"{cfg.get('field')}: not in the files read here"))
                        for ref in refs:
                            size = png_size(MANIFEST / ref)
                            ok = size in dims
                            results.append(("met" if ok else "not met",
                                            f"{ref}: {size or 'not a PNG'} (approved: {', '.join(dims)})"))
                    else:
                        results.append(("manual", f"{method}: the founder's run in Fabric"))
                order = ["not met", "unknown", "manual", "met (offline)", "met (draft)", "met"]
                status = min((r[0] for r in results), key=order.index) if results else "manual"
                label = f"{kind} {test['testNumber']}" + (f" ({item.get('name')})" if item else "")
                rows.append((label, test["name"].strip(), "required" if req else "optional", status,
                             " / ".join(r[1] for r in results)))
    return rows, attestation_ok


def report(rows, workload_name, stage, spec_commit) -> str:
    counts = {}
    for r in rows:
        if r[2] == "required":
            counts[r[3]] = counts.get(r[3], 0) + 1
    lines = [f"# Workload Hub pre-check: {workload_name}, stage {stage}", "",
             f"Validator specifications at commit `{spec_commit}`. Required tests by result: "
             + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) + ".", "",
             "| Test | Name | Stage | Result | Evidence |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append("| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spec-dir", required=True, type=Path)
    ap.add_argument("--spec-commit", default="unknown")
    ap.add_argument("--workload-name", default="Krusgraph.Modeler")
    ap.add_argument("--stage", default="Preview", choices=["Preview", "GeneralAvailability"])
    ap.add_argument("--online", action="store_true")
    ap.add_argument("--report", type=Path)
    a = ap.parse_args(argv)
    try:
        rows, attestation_ok = run(a.spec_dir, a.workload_name, a.stage, a.online)
    except (OSError, KeyError, ValueError) as e:
        print(f"Could not read the validator's specifications: {e}", file=sys.stderr)
        return 1
    text = report(rows, a.workload_name, a.stage, a.spec_commit)
    if a.report:
        a.report.write_text(text, encoding="utf-8")
    print(text)
    if not attestation_ok:
        print("docs/HUB-ATTESTATION.md lacks a term the validator searches for (see 'missing in the draft').",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
