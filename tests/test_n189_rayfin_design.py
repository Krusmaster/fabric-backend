"""Round n189: the Rayfin App's design. The founder publishes the generated app with `rayfin up` and wants it to look good
the first time, and wants Fabric users to change the UI themselves (fabric_backend/rayfin_app.py, rayfin_app_ui.py,
docs/RAYFIN-APP.md):

- better default pages: a header with the data product's name and the last refresh, key figure cards (large number,
  label, unit), the ticked charts (bar by a dimension, line by month or week for a date), list pages with sort, search
  and paging, filters (category, customer country, order date range) that change the cards' and charts' queries, a
  Fluent-like look in light and dark, 375 px and up, labels, contrast, keyboard; read-only queries only;
- more choices without AI in the App card: each chart's type, the order of the pages, the accent, which filters; kept
  with the choices (outputs.json) and shown in the dry run;
- EDIT-WITH-AI.md in the package (Claude with Krusgraph for Claude, VS Code, Lovable, a prompt, the rules, publishing
  again), linked from the card;
- the generated app rendered against the shop's fake rows at 1280 x 720 and 375 x 812, light and dark, with axe-core;
  the screenshots go to RAYFIN_APP_SHOTS (CI keeps them as an artifact), never into the repository.
The package's type check is here and in tests/test_rayfin_app.py."""
from __future__ import annotations

import base64
import datetime
import io
import json
import os
import re
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("jwt")

from fabric_backend import demo, plan, rayfin_app, rayfin_app_ui, seed  # noqa: E402
from fabric_backend.rayfin import class_name, prop_name  # noqa: E402
from fabric_backend.seed import schema  # noqa: E402
from test_rayfin_app import _project, _tsc, node_modules  # noqa: F401,E402  (the pinned packages, installed when missing)
from test_workload_api import keys, tok  # noqa: F401,E402
from test_workload_create import make  # noqa: F401,E402  (the workload API against a workspace double)

ROOT = Path(__file__).resolve().parent.parent
RENDER = ROOT / "tests" / "fixtures" / "rayfin_check" / "render"


@pytest.fixture(scope="module")
def shop_rows():
    return plan(schema("shop"), keys=demo.DEMO_KEYS, execute=demo._demo_db())


@pytest.fixture(scope="module")
def opts(shop_rows):
    return rayfin_app.options(shop_rows)


def _all(opts, **extra):
    return {**{k: [o["id"] for o in opts[k]] for k in rayfin_app.TICKS}, **extra}


# ------------------------------------------------------------------ the choices -----------------------------------

def test_the_shop_defaults_have_a_line_chart_and_the_three_filters(opts):
    d = rayfin_app.defaults(opts)
    labels = {c["id"]: c["label"] for c in opts["charts"]}
    assert [labels[i] for i in d["charts"]] == ["Total quantity by customers (country)", "Total quantity by categories (name)",
                                                "Total quantity by month (orders.order_date)"]
    by_id = {c["id"]: c for c in opts["charts"]}
    assert [by_id[i]["type"] for i in d["charts"]] == ["bar", "bar", "line"]
    assert by_id[d["charts"][2]]["types"] == ["line", "bar", "table"] and by_id[d["charts"][0]]["types"] == ["bar", "table"]
    f = {x["id"]: x for x in opts["filters"]}
    assert d["filters"] == ["filter:customers.country", "filter:categories.name", "filter:orders.order_date"]
    assert [f[i]["label"] for i in d["filters"]] == ["Country", "Categories", "Order date"]
    assert [f[i]["kind"] for i in d["filters"]] == ["values", "values", "dates"]
    assert "filter:customers.name" not in f and not any(x["table"] == "addresses" for x in f.values())   # personal data
    assert [a["id"] for a in opts["accents"]] == list(rayfin_app_ui.ACCENTS) and d["accent"] == "blue"
    assert [p["id"] for p in opts["pages"]][0] == "overview"


def test_a_load_time_column_is_never_a_default_chart_and_is_the_last_refresh():
    import csv
    rows = list(csv.DictReader(open(ROOT / "examples" / "columns.csv", encoding="utf-8")))
    p = plan(__import__("fabric_backend").Schema.from_information_schema(rows), {"order_items": ["order_id", "line_no"]})
    o = rayfin_app.options(p)
    times = [c for c in o["charts"] if c["kind"] == "time"]
    stamp = next(c for c in times if c["date_column"] == "__timestamp")
    assert stamp["technical"] and not stamp["default"]
    assert next(c for c in times if c["default"])["date_column"] == "order_date"
    pkg = rayfin_app.package(p, rayfin_app.resolve(o, None))
    assert pkg["design"]["last_refresh"] == "order_items.__timestamp"
    assert ".orderBy({ timestamp: 'desc' }).first(1)" in pkg["files"]["src/lib/app-data.ts"]


def test_resolve_keeps_types_order_accent_and_refuses_what_does_not_fit(opts):
    cat, time = opts["charts"][0]["id"], next(c["id"] for c in opts["charts"] if c["kind"] == "time")
    ch = rayfin_app.resolve(opts, _all(opts, chart_types={cat: "table", time: "bar"}, page_order=["table:orders", "overview"], accent="teal"))
    assert ch["chart_types"][cat] == "table" and ch["chart_types"][time] == "bar"
    assert ch["page_order"][:2] == ["table:orders", "overview"] and set(ch["page_order"]) == {"overview", *(f"table:{t['table']}" for t in opts["tables"])}
    assert ch["accent"] == "teal"
    with pytest.raises(ValueError, match="can be bar, table, not 'line'"):
        rayfin_app.resolve(opts, _all(opts, chart_types={cat: "line"}))
    with pytest.raises(ValueError, match="accent"):
        rayfin_app.resolve(opts, _all(opts, accent="hotpink"))
    old = rayfin_app.resolve(opts, {"kpis": ["rows:orders"], "tables": [], "charts": []})     # an n181 outputs.json
    assert [f["id"] for f in old["filters"]] == rayfin_app.defaults(opts)["filters"] and old["accent"] == "blue"
    none = rayfin_app.resolve(opts, {"kpis": ["rows:orders"], "tables": [], "charts": [], "filters": []})
    assert none["filters"] == [] and none["page_order"] == ["overview"]


# ------------------------------------------------------------------ the package -----------------------------------

def _pkg(shop_rows, opts, choices=None, title="Shop sales"):
    return rayfin_app.package(shop_rows, rayfin_app.resolve(opts, choices), title=title)


def test_pages_cards_charts_and_filters_match_the_choices(shop_rows, opts):
    cat = opts["charts"][0]
    choices = {"kpis": ["sum:order_items.quantity"], "tables": ["table:orders", "table:products"], "charts": [cat["id"]],
               "filters": ["filter:categories.name"], "chart_types": {cat["id"]: "table"},
               "page_order": ["table:products", "overview", "table:orders"], "accent": "purple"}
    pkg = _pkg(shop_rows, opts, choices)
    f = pkg["files"]
    assert [p["id"] for p in pkg["pages"]] == ["table:products", "overview", "table:orders"]
    assert re.findall(r"render: \(\) => <(\w+) />", f["src/App.tsx"]) == ["ProductsListPage", "OverviewPage", "OrdersListPage"]
    assert "export const ACCENT = \"purple\";" in f["src/lib/app-config.ts"] and "export const APP_TITLE = \"Shop sales\";" in f["src/lib/app-config.ts"]
    ov = f["src/pages/OverviewPage.tsx"]
    assert ov.count("(async (): Promise<Kpi> =>") == 1 and "label: \"Total quantity\", unit: \"sum of order_items.quantity\"" in ov
    assert ov.count("(async (): Promise<Chart> =>") == 1 and f"title: {json.dumps(cat['label'])}, type: 'table'" in ov
    data = f["src/lib/app-data.ts"]
    assert re.findall(r"\{ key: '(\w+)'", data) == ["categoriesName"] and "customersCountry" not in data
    assert set(f) >= {"src/pages/ProductsListPage.tsx", "src/pages/OrdersListPage.tsx", "src/components/kg-ui.tsx",
                      "src/krusgraph-app.css", "src/lib/app-config.ts", "src/lib/app-data.ts"}
    assert "src/pages/OrderItemsListPage.tsx" not in f and "src/pages/KpisPage.tsx" not in f
    assert pkg["design"]["charts"] == [{"id": cat["id"], "label": cat["label"], "type": "table"}]
    assert pkg["design"]["filters"] == [{"id": "filter:categories.name", "label": "Categories", "kind": "values", "reaches": ["order_items"]}]
    lists = _pkg(shop_rows, opts, {"kpis": [], "tables": ["table:orders"], "charts": []})
    assert [p["id"] for p in lists["pages"]] == ["table:orders"] and "src/pages/OverviewPage.tsx" not in lists["files"]


def test_the_filters_become_the_queries_where_arguments(shop_rows, opts):
    data = _pkg(shop_rows, opts)["files"]["src/lib/app-data.ts"]
    items = data[data.index("export async function whereOrderItems"):data.index("export type OrdersWhere")]
    # categories.name → products.category_id → order_items.product_id, each step a read of keys
    assert ".where({ name: { in: f.categoriesName } })" in items and ".where({ categoryId: { in: keys } })" in items
    assert "and.push({ productId: { in: keys } });" in items
    assert ".where({ country: { in: f.customersCountry } })" in items and "and.push({ orderId: { in: keys } });" in items
    assert ".where({ orderDate: dateRange(f.ordersOrderDate) })" in items
    orders = data[data.index("export async function whereOrders("):]
    assert "and.push({ orderDate: dateRange(f.ordersOrderDate) });" in orders and "categoriesName" not in orders.split("export function lookup")[0]
    ov = _pkg(shop_rows, opts)["files"]["src/pages/OverviewPage.tsx"]
    assert "await data.OrderItems.where(where).aggregate(" in ov and "await data.OrderItems.where(where).groupBy(['productId'])" in ov
    assert "const [orderItemsWhere, ordersWhere] = await Promise.all([whereOrderItems(data, f), whereOrders(data, f)]);" in ov
    assert ov.count("const where = w.orderItemsWhere;") == 5                            # read once per change, used by each
    assert "notReached(f, ['customersCountry', 'ordersOrderDate'])" in ov                     # orders: no category link
    lst = _pkg(shop_rows, opts)["files"]["src/pages/ProductsListPage.tsx"]
    assert "return { name: { contains: q } };" in lst and ".orderBy({ [sort.column]: sort.dir } as OrderBy)" in lst
    assert ".first(PAGE_SIZE)" in lst and "query.after(after)" in lst and "executePaginated()" in lst


def test_read_only_and_no_network_call_beyond_the_connector(shop_rows, opts):
    for choices in (None, _all(opts)):
        files = _pkg(shop_rows, opts, choices)["files"]
        for path, text in files.items():
            if not path.endswith((".ts", ".tsx", ".css")):
                continue
            assert not re.search(r"\.(create|update|delete)\(|'(create|update|delete)'|mutation", text, re.I), path
            assert not re.search(r"\bfetch\(|XMLHttpRequest|WebSocket|https?://|@import", text), path
            assert "dangerouslySetInnerHTML" not in text and "localStorage" not in text, path
        for path in ("rayfin/connectors/shop/schema.ts", "src/lib/app-connectors.ts"):
            assert re.findall(r"operations: \[([^\]]*)\]", files[path]) == ["'read'"]
        imports = {m for t in files.values() for m in re.findall(r"from '([^'.][^']*)'", t)}
        assert imports <= {"react", "@microsoft/rayfin-client", "@microsoft/rayfin-connectors", "@microsoft/rayfin-core",
                           "@microsoft/rayfin-connector-fabric-graphql"}, imports  # the template's own packages


def _lum(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_every_accent_and_the_muted_text_keep_4_5_to_1_in_light_and_dark():
    for mode, (page, card, text, muted) in rayfin_app_ui.NEUTRALS.items():
        for bg in (page, card):
            assert _contrast(text, bg) >= 7 and _contrast(muted, bg) >= 4.5, (mode, bg)
        for name, (light, dark) in rayfin_app_ui.ACCENTS.items():
            accent = light if mode == "light" else dark
            on = "#ffffff" if mode == "light" else "#1f1f1f"
            assert _contrast(accent, page) >= 4.5 and _contrast(accent, card) >= 4.5 and _contrast(on, accent) >= 4.5, (mode, name)
    css = rayfin_app_ui.css()
    assert ".dark .kg-app {" in css and "@media (max-width: 640px)" in css and ":focus-visible" in css
    assert all(f".kg-app[data-accent='{k}']" in css for k in rayfin_app_ui.ACCENTS)


# ------------------------------------------------------------------ EDIT-WITH-AI.md and the dry run -----------------

def test_edit_with_ai_says_how_and_the_rules(shop_rows, opts):
    pkg = _pkg(shop_rows, opts)
    md = rayfin_app.edit_with_ai("shop_app", "Krusgraph demo", pkg["pages"], pkg["connector"])
    for part in ("https://krusgraph.com/mcp/connect", "## Open it in Claude", "## Open it in VS Code", "## Open it in Lovable",
                 "Add a chart of <measure> by <dimension> on the <page> page; keep queries read-only; run npm run typecheck",
                 "**Read-only.**", "**No secrets in code.**", "**Keep the type check green.**",
                 'npx rayfin up --workspace "Krusgraph demo"', rayfin_app.TYPECHECK_SETUP, "`src/pages/OverviewPage.tsx`",
                 "rayfin/connectors/shop/"):
        assert part in md, part


def test_the_dry_run_shows_the_design_and_links_change_it_yourself(make):
    from test_n181_rayfin_app import Apps, _app
    from test_workload_create import _review
    client, fake, priv = make(Apps())
    rv = _review(client, priv)
    a = _app(client, priv, rv, product={"name": "Shop sales"})["answer"]
    assert a["chosen"]["accent"] == "blue" and a["chosen"]["page_order"][0] == "overview"
    assert a["chosen"]["filters"] == ["filter:customers.country", "filter:categories.name", "filter:orders.order_date"]
    assert a["design"]["page_order"][0] == "Overview" and a["design"]["accent_colours"] == {"light": "#0f6cbd", "dark": "#479ef5"}
    overview = a["pages"][0]
    assert overview["title"] == "Overview" and "line chart Total quantity by month (orders.order_date)" in overview["shows"]
    assert "filter Order date" in overview["shows"] and "key figure Total quantity (sum of order_items.quantity)" in overview["shows"]
    e = a["edit_yourself"]
    assert e["title"] == "Change the app yourself" and e["file"] == "EDIT-WITH-AI.md" and "krusgraph.com/mcp/connect" in e["markdown"]
    z = zipfile.ZipFile(io.BytesIO(base64.b64decode(a["package"]["zip_base64"])))
    assert z.read("EDIT-WITH-AI.md").decode() == e["markdown"]
    assert "EDIT-WITH-AI.md" in z.read("KRUSGRAPH-APP.md").decode()
    assert "export const APP_TITLE = \"Shop sales\";" in z.read("src/lib/app-config.ts").decode()   # the data product's name
    # the person's choices go with the request and come back
    cat = a["options"]["charts"][0]["id"]
    mine = {"kpis": ["rows:orders"], "tables": ["table:orders"], "charts": [cat], "filters": [],
            "chart_types": {cat: "table"}, "page_order": ["table:orders", "overview"], "accent": "green"}
    b = _app(client, priv, rv, app=mine)["answer"]
    assert b["chosen"] == mine and [p["id"] for p in b["pages"]] == ["table:orders", "overview"]
    assert b["design"]["filters"] == [] and b["design"]["charts"][0]["type"] == "table"
    bad = _app(client, priv, rv, app={**mine, "accent": "hotpink"})["answer"]
    assert bad["kind"] == "bad_input" and "accent" in bad["error"]
    from test_workload_create import _post
    from test_workload_api import SRC
    r = _post(client, "/build", {**SRC, "review": rv, "outputs": [{"kind": "rayfin_app", "name": "shop_app",
                                                                    "app": {**mine, "chart_types": {cat: "pie"}}}]}, priv)
    assert r.status_code == 400 and "chart_types" in r.text


# ------------------------------------------------------------------ type check -------------------------------------

@pytest.mark.parametrize("case", ["all_tables_teal", "lists_only", "no_filters"])
def test_the_package_type_checks_with_every_choice(case, shop_rows, opts, node_modules, tmp_path):  # noqa: F811
    if case == "all_tables_teal":
        choices = _all(opts, chart_types={c["id"]: "table" for c in opts["charts"]}, accent="teal",
                       page_order=[f"table:{t['table']}" for t in opts["tables"]][::-1])
    elif case == "lists_only":
        choices = {"kpis": [], "tables": ["table:orders", "table:audit_log"], "charts": []}
    else:
        choices = {**rayfin_app.defaults(opts), "filters": []}
    files = _pkg(shop_rows, opts, choices)["files"]
    root = _project(tmp_path / case, node_modules, files)
    for config in ("rayfin/tsconfig.json", "tsconfig.json"):
        r = _tsc(root, config)
        assert r.returncode == 0, r.stdout + r.stderr


# ------------------------------------------------------------------ rendered: screenshots and accessibility ---------

def _playwright() -> bool:
    if not shutil.which("node"):
        return False
    return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, text=True).returncode == 0


def _fake_rows() -> dict:
    """The shop's seed rows by entity and property, as the connector would answer them (dates as ISO text)."""
    out = {}
    for t, rows in seed.rows().items():
        cols = [c.split()[0] for c in seed.SCHEMAS[t].split(", ")]
        out[class_name(t)] = [{prop_name(c): v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v
                               for c, v in zip(cols, r)} for r in rows]
    return out


def _png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", head[16:24])


@pytest.fixture(scope="module")
def rendered(shop_rows, opts, node_modules, tmp_path_factory):  # noqa: F811
    """The default package built with Vite against the fake connector and checked in Chromium (render/shoot.mjs)."""
    if not _playwright():
        pytest.skip("node + playwright not available")
    root = _project(tmp_path_factory.mktemp("render") / "app", node_modules, _pkg(shop_rows, opts)["files"])
    (root / "kg-render").mkdir()
    (root / "kg-render" / "fake-data.json").write_text(json.dumps(_fake_rows()), encoding="utf-8")
    shots = Path(os.environ.get("RAYFIN_APP_SHOTS") or tmp_path_factory.mktemp("shots"))
    cmd = ["node", str(RENDER / "shoot.mjs"), str(root), str(shots)]
    if os.environ.get("PLAYWRIGHT_CHROMIUM"):
        cmd.append(os.environ["PLAYWRIGHT_CHROMIUM"])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-4000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_the_screenshots_at_1280_and_375_in_light_and_dark(rendered):
    names = {Path(p).stem: Path(p) for p in rendered["shots"]}
    for page in ("overview", "list"):
        for size, width in (("desktop", 1280), ("phone", 375)):
            for theme in ("light", "dark"):
                w, h = _png_size(names[f"{page}-{size}-{theme}"])
                assert w == width and h >= (720 if size == "desktop" else 812)
    assert not any(str(ROOT) in p for p in rendered["shots"]), "screenshots never go into the repository"


def test_the_rendered_pages_pass_axe_and_fit_375_px(rendered):
    assert set(rendered["axe"]) == {f"{p}-{s}-{t}" for p in ("overview", "list") for s in ("desktop", "phone") for t in ("light", "dark")}
    assert {k: v for k, v in rendered["axe"].items() if v} == {}
    assert all(v <= 0 for v in rendered["overflow"].values()), rendered["overflow"]
    assert rendered["errors"] == [] and rendered["external"] == [] and rendered["mutations"] == []
    c = rendered["checks"]
    assert c["first_tab"] == "Skip to the content" and c["after_enter"] == "products"
    assert "ascending" in c["aria_sort"]


def test_the_rendered_overview_shows_what_was_chosen(rendered):
    c = rendered["checks"]
    assert c["title"] == "Shop sales" and c["refreshed"].startswith("Data read ") and c["accent"] == "blue"
    assert c["tabs"] == ["Overview", "products", "orders", "order_items"]
    assert [(k["label"], k["value"], k["unit"]) for k in c["cards"]] == [
        ("Rows in orders", "60", "rows"), ("Rows in order_items", "134", "rows"), ("Total quantity", "324", "sum of order_items.quantity")]
    assert [(x["title"], x["kind"]) for x in c["charts"]] == [
        ("Total quantity by customers (country)", "bar"), ("Total quantity by categories (name)", "bar"),
        ("Total quantity by week (orders.order_date)", "line")]                                     # Sept-Oct: by week
    assert c["filters"] == ["Country", "Categories", "Order date"]


def test_the_filters_sort_search_and_paging_change_the_queries_arguments(rendered):
    c = rendered["checks"]
    agg = lambda qs, e: [q for q in qs if q["entity"] == e and q["kind"] == "aggregate"]  # noqa: E731
    assert all(q["where"] == {} for q in agg(c["before"], "OrderItems"))
    # Country: the first value ticked → customers' keys → orders' keys → order_items.order_id in [...]
    after = agg(c["after_values"], "OrderItems")
    assert after and all("orderId" in q["where"] and q["where"]["orderId"]["in"] for q in after)
    looked = [q for q in c["after_values"] if q["entity"] == "Customers" and q["kind"] == "rows" and q["where"]]
    assert looked and looked[0]["where"]["country"]["in"] == ["DE"]
    assert [int(x) for x in c["cards_after"]] < [60, 134, 324]
    dated = agg(c["after_dates"], "Orders")
    assert dated and dated[0]["where"]["orderDate"]["gte"].startswith("2026-10-01")
    page = [q for q in c["after_sort"] if q["kind"] == "page"]
    assert page and page[0]["orderBy"] == {"name": "asc"} and page[0]["first"] == rayfin_app.PAGE_SIZE
    searched = [q for q in c["after_search"] if q["kind"] == "page"]
    assert searched and searched[0]["where"] == {"name": {"contains": "a"}}
