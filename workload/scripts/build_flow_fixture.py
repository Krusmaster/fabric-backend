"""Krusgraph (n174): the data flow of seed.py's shop schema, as the editor's unit tests read it.

fabric_backend/data_flow.py builds the flow the Model editor draws (FlowView.tsx) from the engine's silver, gold and
pipeline drafts. This script writes that flow for the synthetic shop schema (silver notebook, gold views, pipeline and a
semantic model, all chosen) to

    workload/Workload/app/items/ModelItem/flow.fixture.json

so dataFlow.test.ts and FlowView.test.ts lay out and render exactly what the engine sends. Run it from the repository
root after data_flow.py, silver.py, gold.py or pipeline.py change:

    python workload/scripts/build_flow_fixture.py           # writes the file
    python workload/scripts/build_flow_fixture.py --check   # exit 1 when the file is stale

tests/test_workload_build.py fails while the file differs from what this script writes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = "workload/Workload/app/items/ModelItem/flow.fixture.json"
INFO = {"workspace_id": "00000000-0000-0000-0000-000000000000", "item_id": "00000000-0000-0000-0000-000000000001",
        "item_name": "demo_lh", "item_kind": "Lakehouse", "schema": "shop", "sql_endpoint": "", "sql_db": "demo_lh",
        "schemas_enabled": True}


def render() -> str:
    sys.path.insert(0, str(ROOT))
    from fabric_backend import data_flow, seed, semantic_model
    from fabric_backend.infer import plan
    p = plan(seed.schema("shop"))
    model = semantic_model.draft(p, INFO, "shop_sales", None)["parts"]
    chosen = {"silver_notebook": "shop_silver", "gold_views": "shop_gold", "pipeline": "shop_flow", "semantic_model": "shop_sales"}
    items = [{"output": "semantic_model", "label": "Semantic model", "name": "shop_sales", "reads": "reads shop (bronze) directly",
              "code": data_flow.tmdl_excerpt(model), "language": "tmdl", "code_title": "shop_sales: relationships and measures"}]
    f = data_flow.flow(p, INFO, chosen, pipeline_names=("shop_silver", "shop_gold", "shop_flow_check"), items=items)
    return json.dumps(f, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    text, path = render(), ROOT / OUT
    if "--check" in argv:
        same = path.exists() and path.read_text(encoding="utf-8") == text
        print(f"{OUT}: {'current' if same else 'STALE: run python workload/scripts/build_flow_fixture.py'}")
        return 0 if same else 1
    path.write_text(text, encoding="utf-8")
    print(f"wrote {OUT} ({len(text)} characters)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
