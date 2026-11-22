# QA: "Ontologies, data products and apps" (DRAFT, not approved)

2026-11-22, round FV3. A second film in the style of FV2's "A few taps" (`social/films/2026-11-22-few-taps/`), for the
founder's review. **Nothing is scheduled, posted or published.** Silent with text and the same synthesized sound
(`../2026-11-22-few-taps/source/sound.py`; the scene timings are the same), 9:16 only.

| File | Format | Length | Size | Loudness |
| --- | --- | --- | --- | --- |
| krusgraph-ontology-products-app-9x16.mp4 | 1080x1920, 30 fps, H.264 + AAC 192 kb/s | 19.5 s | 3.9 MB | -13.2 LUFS integrated, peak -1.0 dBFS |
| cover-9x16.jpg | 1080x1920, the frame at 15.0 s ("Boom." and the three cards) | | | |

## Shot by shot, and what backs it

| Time | On screen | What backs it today |
| --- | --- | --- |
| 0.0-2.6 s | "Your data is in Fabric." Generic table chips | As in FV2 |
| 2.6-5.2 s | "So many tables. What do they mean for your business?" | A question, no claim |
| 5.2-9.2 s | "Just ask." "Start Krusgraph" typed and sent | The start tool and prompt |
| 9.2-13.0 s | "A few taps." The five steps ticked | The guided path (SM2, SM3) |
| 13.0-16.4 s | "Boom." **Ontology** (preview), customer → order → invoice | `create_ontology` created ontologies live on 28 October and 2 November 2026 (`fabric_backend/tool_status.py`); Fabric's ontology item is a preview and needs a tenant setting |
| | **Data products**, in the OneLake catalog | The data product catalog (DP1, DP2) and `publish_catalog` (CA1: descriptions, owners, tags; dry run by default) |
| | **Fabric app** (preview), ready to publish | The App (Rayfin, preview) output builds an app package; the user publishes it with `npx rayfin up` (`docs/RAYFIN-APP.md`). "Ready to publish", not "published": deploying with `rayfin up` is not verified by a round |
| 16.4-19.5 s | Logo, "Ontologies, data products and apps in a few taps.", krusgraph.com, mascots | Fine print: "Demo on synthetic data. Ontology and Fabric apps are Fabric previews. Krusgraph is independent and not affiliated with Microsoft." |

The two preview items carry a small "preview" tag on their cards. The card icons are drawn for this film. The Fabric
logo stands in scene 1 ("Your data is in / ▰ Fabric.") and in the end card's "▰ Microsoft Fabric" line; "Fabric" and its
logo always on a line of their own (FV6).

**The Microsoft Fabric logo** (round FV5, at the founder's request) is Microsoft's own `fabric_48_color.svg`, unmodified, from the npm package `@fabric-msft/svg-icons@12.0.0` (MIT; the same pinned version the workload uses, see `THIRD_PARTY_NOTICES.md`, *Microsoft Fabric item icons in the workload editor*). No icon file is stored here: `source/film.html` reads it from `workload/Workload/node_modules/` (run `npm ci` in `workload/Workload` first). Microsoft's page on the icons (https://learn.microsoft.com/fabric/fundamentals/icons) offers them for Fabric platform extension development; Krusgraph is a Fabric workload, and the logo stands only beside the words Microsoft Fabric, next to the fine print "Krusgraph is independent and not affiliated with Microsoft". No Claude logo.

## Gates

| Gate | Result |
| --- | --- |
| Safe area | As FV2: text and cards between y 300 and 1500, x 60 to 1020 |
| Frames looked at | Contact sheet every 1 s and stills at 4.0, 15.0 and 18.8 s (scene 2's headline was shortened to one line after the first still). Not watched on a phone yet |
| Wording | No sales words from `tests/test_site.py`; no number claimed; no customer; no "partner", "certified" or endorsement |

## Render again

From the repository root:

```bash
node social/films/2026-11-22-few-taps/source/render.js silent.mp4   # after copying render.js next to this film.html, or:
cp social/films/2026-11-22-few-taps/source/render.js social/films/2026-11-22-ontology-products-app/source/ && node social/films/2026-11-22-ontology-products-app/source/render.js silent.mp4
python3 social/films/2026-11-22-few-taps/source/sound.py sound.wav
ffmpeg -y -i silent.mp4 -i sound.wav -filter_complex "[1]loudnorm=I=-14:TP=-1.5:LRA=11[a]" -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -shortest krusgraph-ontology-products-app-9x16.mp4
```

sha256: `41c1a2441317bc122170f55ff4ea31ead11debc8efe760513e9a4e313be92135`
