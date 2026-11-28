# QA: "Find and trust your data products" (DRAFT, not approved)

2026-11-22, round FV9. A fourth film in FV2's style, at the founder's request: the OneLake catalog and Purview.
**Nothing is scheduled, posted or published.** Silent with text and FV3's sound (same scene timings), 9:16 only.

| File | Format | Length |
| --- | --- | --- |
| krusgraph-catalog-purview-9x16.mp4 | 1080x1920, 30 fps, H.264 + AAC 192 kb/s | 19.5 s |
| cover-9x16.jpg | the frame at 15.0 s ("Boom." and the three cards) | |

## Shot by shot, and what backs it

| Time | On screen | What backs it today |
| --- | --- | --- |
| 0.0-2.6 s | "Your data is in / ▰ Fabric." | As FV3 |
| 2.6-5.2 s | "Data products? Who owns them? Can you trust them?" | Questions, no claim |
| 5.2-13.0 s | "Just ask." and "A few taps." | The start tool and the guided path |
| 13.0-16.4 s | **OneLake catalog**: description, owner, domain, tags | `publish_catalog` / "Publish to OneLake catalog" (CA1, `docs/CATALOG-ACCELERATOR.md`): a product card per data product with a description, the owner you name, the proposed domain and existing tags, after a diff of every change. CA1's own status: unit tests and a browser check, **not run against Fabric** |
| | **Quality, counted**: a dated line on every card | Every description ends with the dated evidence line from `validate_plan`'s counts (BL29, CA1) |
| | **Purview hand-over**: glossary and quality rules | `handover/purview.json` (`fabric_backend/catalog_publish/purview.py`): governance domain, data product, glossary terms and quality rules in Purview's rule types. **Krusgraph sends nothing to Purview** (it acts as the signed-in user, and Purview's Unified Catalog is being retired, in maintenance until 12 November 2027); hence "hand-over" and the fine print "Purview gets a file" |
| 16.4-19.5 s | "Find and trust your data products." / ▰ Microsoft Fabric / krusgraph.com | Fine print: "Synthetic demo data. Every change is shown before it is written; Purview gets a file. Krusgraph is independent and not affiliated with Microsoft." |

**Icons**: Microsoft's own, unmodified, from `@fabric-msft/svg-icons@12.0.0` (the workload's pinned version), read from
`workload/Workload/node_modules/`: `lakehouse_48_item.svg` for the catalog card (the package has no OneLake catalog
icon), `data_quality_48_item.svg`, `purview_48_color.svg`, and the Fabric logo `fabric_48_color.svg`. See FV5's note in
`../2026-11-22-ontology-products-app/QA.md` on the icons' terms.

## Open for the founder

1. Publishing to the OneLake catalog has not run against Fabric (CA1). The film shows the result, not a live run.
2. Purview: the Unified Catalog is retiring; decide whether a Purview card is worth showing at all.

sha256: `ce2747489baabe6bd005354af3e41c9dc6114218efc69bfa238ebb12e8659077`
