# QA: krusgraph-ontology-9x16.mp4

2026-11-17, round S1 (Opus). A draft for the founder's review. Nothing is scheduled or published.

**What it shows.** The v5 format: the hook "If you use / Microsoft Fabric [official Fabric logo] / you need to see this.",
the four steps in Claude, then the result: Krusgraph checks the keys and links of the SAP-shaped example against its rows
and drafts a Fabric IQ ontology for order to cash (customers, orders, order lines, invoices) with the links it checked.

## Real vs not possible

| On screen | Source |
| --- | --- |
| 17 of 17 keys unique; Order lines → Orders: 1 of 6 rows (16.7%) point at nothing | `evidence.validate` on `sap_demo.sqlite()` (engine output, fabric-backend `9e5f1a8b984195c96ddd3bae6642a3ccee6693bc`) |
| The ontology graph: 4 entity types (SapKna1, SapVbak, SapVbap, SapVbrk), 4 relationship types, each link's verdict | `ontology.summary`, `ontology.bindings` and `ontology.ontology_ttl` for those four tables: what `create_ontology` returns as its dry run (dry_run=true is its default). The TTL's four ObjectProperties are asserted equal to the links drawn |
| "Customers", "Orders", "Order lines", "Invoices" | the plain names the approved v5 short uses for KNA1, VBAK, VBAP, VBRK; the engine's entity type name and table code are under each |

**Not done: no ontology item was created in Fabric.** This session has no Fabric credentials (no token, no workspace
access; only Azure Speech is connected), so `create_ontology` could not run with dry_run=false. The film therefore says
"drafts" and "It creates it in Fabric only when you say yes", and the scene is labelled "Fabric IQ ontology · dry run".
`create_ontology` did create an ontology live once (28 Oct 2026, `docs/LIVE-TEST.md`, shop sample), not this one.

## Gates (build/build_short.sh in krusgraph-business, branch s1-shorts, marketing/shorts/2026-11-17-s1)

| Gate | Result |
| --- | --- |
| No UI imitation | the steps are plain text lines (no cards, badges, input box, cursor or click); no buttons, pills or chat boxes anywhere; link verdicts are plain ✓ / ! glyphs. Usable as an ad |
| hyperframes lint / check | 0 errors in lint, runtime, layout, motion, contrast, audio; warnings: lint 1 (dense captions file), contrast 2, craft 5 (fast-cut reading time and small type, as v5) |
| qa_c2.cjs on the live preview, every frame (839, 723 settled) | passed: every word in the safe area (y 288-1248, x 192-888, below y 840 only x 300-780), inside its card, nothing past the frame, no tiny text, centred (worst margin difference 15.6 px, end card), icons whole, mascots not upscaled. One earlier build failed it ("bio" popping from scale 0 read as tiny text); the pop now starts at 55 % and transparent |
| Flash gate (flash_check.py) | 839 frames, luma 34.6-46.1, 0 jumps over 15 %, 0 findings; no white overlay on cuts |
| Silence gate | the voice stem: 13 pauses, every one digital silence (no breaths). The V3f bed continues under the pauses by design (-37 to -34 dBFS rms in the mix), as in C2's shorts |
| Length | 27.97 s (23-30 s) |
| Loudness | -14.0 LUFS integrated, true peak -1.0 dBFS |
| Format | 1080 x 1920, 30 fps, H.264, AAC 48 kHz, 4.0 MB |
| End card | v5's: Krusgraph logo, "for Microsoft Fabric" + the official Fabric logo, "Link in bio", krusgraph.com, the three mascots (unchanged drawings), "Voice: AI-generated. Synthetic demo data." |
| Wording | no number spoken; generator lint refuses speed, compliance, certification, partnership, endorsement words and "Works with Claude"; captions.txt says "Use it in Claude", "Shown on our SAP-shaped example, not data from an SAP system" and "Krusgraph is independent and not affiliated with SAP or Microsoft"; no Claude logo |

Voice: Ava HD (en-US-Ava:DragonHDLatestNeural), +9 % (C2's rate, about 0.94x v4), one request via the environment's
Azure Speech proxy (no key in any file or log); "krusgraph.com/mcp" said as "Kroos graph dot com slash M C P".
Sound: V3f's synthesized premium bed (sound_premium.py, unchanged), 19 dB under the voice.

sha256 `f656c2f53634c84eb9a8e9d7cde4bf43c627ac7730f7af407262f151698736bd`
