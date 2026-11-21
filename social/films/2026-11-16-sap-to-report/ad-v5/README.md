# SAP film, ad cut v5 (round FM2, 21 Nov 2026)

A draft for the founder's review. Nothing here is published, uploaded to Meta or applied to the running ad
"SAP film reel - check". The earlier files in the folder above (-v2 to -v4) are not changed.

## Files

| File | What |
| --- | --- |
| `krusgraph-sap-to-report-9x16-ad-v5.mp4` | Reels / Stories, 1080 x 1920, 21.0 s, 30 fps, H.264, silent AAC track, 0.6 MB |
| `krusgraph-sap-to-report-4x5-ad-v5.mp4` | Feed, 1080 x 1350, the same cut, 0.6 MB |
| `krusgraph-sap-to-report-9x16-ad-v5-first-frame.png` | Frame 0 of the 9:16 film, decoded from the MP4 |
| `krusgraph-sap-to-report-4x5-ad-v5-first-frame.png` | Frame 0 of the 4:5 film, decoded from the MP4 |
| `krusgraph-sap-to-report-9x16-ad-v5-safe-zone-guide.png` | Review only: a frame at 9.8 s with the covered areas tinted |

sha256: 9:16 `f94d085655f51b423c0f81c2d9940a13da3283abbdb62f1b76bd5ba39147ba89`,
4:5 `1cb04ccf9aebaa7f32b3b0d468cf21bce950ea24c238049b21f89e8013e7c284`.

## Why

The ad ran 16-18 Nov (262 SEK): CTR 2.24 %, but 3 s average watch time and 3.6 % of plays reaching 25 %. The v4 reel
opens on an empty canvas with only the wordmark, the hook fades in, the diagram arrives after 3.9 s, there is a large
empty band between the prompt card and the mascots, a box with only the logo stands on its own, and the captions sit
at y 1540-1640, under Instagram's CTA bar.

## What changed against v4

1. **Hook in second 0-1.** Frame 0 already shows the hook line ("If you use Microsoft Fabric, you need to see this."),
   the Lakehouse panel with the 16 SAP table names of the sample, each with a "?", and the caption "Hundreds of SAP
   tables with short, cryptic names. How do they connect?". Nothing fades in from nothing.
2. **No empty space, no lone logo box.** The prompt card ("Claude - Turn my SAP tables into a report", "Use it in
   Claude") replaces the hook at 3.2 s in the same block, directly above the panel. The three mascots sit on the
   panel's header from frame 0; the Krusgraph box that showed only the logo is gone.
3. **Safe zones** (below): the diagram, the prompt, the captions and the end card are all inside them.
4. **Shorter:** 21 s instead of 55.6 s. The beats: tables (0 s), prompt (3.2 s), the map of 7 tables and 8 links
   (4.6 s), the check "32 of 34 links hold" (8.8 s), the two data products (11.2 s), the report (14.8 s), the end
   card (18.4 s). The semantic model beat is folded into the report's caption ("each order counted once").
5. **Silent with burned-in captions.** No voice, so no "Voice: AI-generated" line.
6. **No Microsoft or SAP logo as branding:** v4's Fabric logo in the hook and on the end card is gone. The Lakehouse
   and Report item icons stay as diagram symbols. The end card: mascots, the krusgraph wordmark, "Try it in your
   browser: krusgraph.com/check", "Use it in Claude", and the small print (synthetic SAP-shaped data, not from an SAP
   system; trademarks; not affiliated with Microsoft or SAP). No button shape.

## Safe zones used

| Format | Covered (left free of anything that matters) | Safe area used |
| --- | --- | --- |
| 9:16, 1080 x 1920 | top 14 % = 269 px (name, progress bar); bottom 35 % = 672 px, from y 1248 (the "Se mer"/CTA bar, name, caption); right 128 px (the icons); left 64 px margin | x 64-952, y 270-1248 (888 x 978 px) |
| 4:5, 1080 x 1350 | when Meta shows a 4:5 ad in the Reels placement it is centred in 1920 px (285 px offset), so the bottom 35 % starts at y 963; top 72 px and left 64 px margin; right 128 px | x 64-952, y 72-960 (888 x 888 px) |

Inside the 9:16 safe area: the hook / prompt block y 270-466, the panel y 482-1082, the caption block y 1098-1248.
The renderer checks every 0.1 s that every card, label, number, caption and end-card line lies inside the safe area,
that no link label covers a table box or another label, and that frame 0 has the hook, all 16 tables and the first
caption at full opacity; the build stops on any failure. All checks passed for both formats.

## Numbers and names

Every table name, link, the "32 of 34 links hold", the two data products and the report's numbers (750 EUR net order
value, 400 EUR billed, 600 / 100 / 50 by customer) come from `facts.json`, written by `build/facts.py` running
Krusgraph's engine on the synthetic SAP sample (`fabric_backend/sap_demo.py`). It was re-run for this cut against
fabric-backend `main` (cc79437): every value shown is unchanged from v4 (only the SAP pack's list of table names grew,
which the film does not show). The renderer stops when a caption has a number other than 32 and 34.

## Source and how to render

The source lives with the film's other build files in Krusmaster/krusgraph-business, branch `fm2-sap-film-ad-v5`,
folder `marketing/films/2026-11-15-sap-to-report/ad-v5/` (`film-ad.html`, `render-ad.js`, `facts.json`).

```
cd fabric-backend/fabric_backend && python3 -m http.server 8765 --bind 127.0.0.1 &
cd krusgraph-business/marketing/films/2026-11-15-sap-to-report/ad-v5
node render-ad.js http://127.0.0.1:8765 f916 krusgraph-sap-to-report-9x16-ad-v5.mp4
node render-ad.js http://127.0.0.1:8765 f45  krusgraph-sap-to-report-4x5-ad-v5.mp4
node render-ad.js http://127.0.0.1:8765 f916 still --stills=0,9.8 --guide   # review stills with the covered areas tinted
```

## Open for the founder

- Preview on the phone before any change to the ad. The running ad is not touched.
- The caption text of the ad (Meta's primary text) can stay as it is; the film itself now carries the hook.
