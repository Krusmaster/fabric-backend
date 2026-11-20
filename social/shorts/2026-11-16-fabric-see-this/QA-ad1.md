# QA: krusgraph-fabric-see-this-9x16-ad1.mp4 (ad-safe variant of v5)

2026-11-17, round S1 (Opus). A draft for paid use on TikTok. Nothing is scheduled, published or submitted.

## Why

TikTok's automated ad review rejected v5 as an ad: "The ad contains buttons that are not functional and displays
that intentionally lead users to low-quality content" (suggestion: remove buttons that do not function). -ad1 is
v5 with every imitation of an interface removed. Everything else is v5.

## What changed against v5 (picture only)

| Scene | v5 | -ad1 |
| --- | --- | --- |
| The four steps (2.9-11.4 s) | Four white cards, a numbered coral badge on each, a four-segment progress bar, a "Paste" input box with letters typed in and a blinking caret | Four plain text lines on the dark background, centred, all four visible from the first frame of the scene (dim), each brightening as it is said: "1 In Claude: Connectors", "2 Add custom connector", "3 Paste krusgraph.com/mcp", "4 Sign in with your work account". No card, badge, bar, box, caret or cursor |
| Data products | "Owner: you choose" with an empty radio circle, and a coral "Ready to build" pill | Both removed; the cards show the product name and what it contains |
| Semantic model | The measures as bordered chips | Plain text (no border, no fill) |
| Pipeline | A grey ring on each step that turns into a green filled circle with a tick | A plain green tick, no ring and no circle |
| Report | "Semantic model ✓ / Pipeline ✓ / Report ✓ in Fabric" as bordered pills | The same words and icons as plain text |

Nothing in the film has a button shape, input box, cursor, click, play symbol or tappable-looking chrome. The map's
table nodes, the data-product cards and the report page are diagrams and result frames, not controls.

## Unchanged (checked)

- Audio: the decoded audio of -ad1 is byte-identical to v5's (same voice, Ava HD, same placement, same silences; v5 has no sound bed).
- Hook, captions (27 groups), timing (every cut from the same word times), end card ("Link in bio", krusgraph.com,
  "for Microsoft Fabric" with the official Fabric logo, the mascots unchanged, "Voice: AI-generated. Synthetic demo data.").
- Every number and name on screen comes from H1's `facts.json` (engine output on the SAP-shaped example), as in v5.

## Gates (all run by `build/build_ad.sh` in krusgraph-business, branch s1-shorts; the build stops at the first failure)

| Gate | Result |
| --- | --- |
| `hyperframes lint` | 0 errors, 1 warning (`timeline_track_too_dense` in captions; advice, not a fault) |
| `hyperframes check` (runtime, layout, motion, contrast, audio, safe areas for TikTok/Reels/Shorts) | ok; 0 errors in every category |
| H1's `qa.cjs` on the live preview (every word in the safe area, nothing clipped, nothing past the frame, icons whole, lines on card edges, mascots never upscaled, centred balance) | passed, 0 findings. The first build failed it: the plain pipeline tick reached 2 px below y 840 at x 904 (under TikTok's buttons); it was made smaller and the build passed |
| Flash gate (`flash_check.py`: no flash, dip, white or blank frame, max 3 jumps a second) | 786 frames, mean luma 34.2-74.3, 0 findings; no white overlay on any cut |
| Silence gate (`pause_check.py`) | 13 pauses, loudest -149.5 dBFS (limit -60): true digital silence, no breaths |
| Length | 26.2 s (within 23-30 s) |
| Loudness | -14.2 LUFS integrated, true peak -4.5 dBFS |
| Format | 1080 x 1920, 30 fps, H.264 yuv420p, AAC 48 kHz, 4.3 MB |

sha256 `8c90d9b3706cdc671f2ab1101c73c37f10d6e67ac94478befc1c6dfefc4128cb`

## Open for the founder

- The end card's small print is v5's ("Synthetic demo data."), kept identical as asked; it does not say "Shown on our
  SAP-shaped example, not data from an SAP system". The ad text can carry that line.
- TikTok may still reject for other reasons; this variant removes only what the review named.
