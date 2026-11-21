# QA: the vision teaser (DRAFT, not approved)

2026-11-21, round FV1 (Opus). A draft for the founder's review. **Nothing is scheduled, posted or published.** The film
shows where Krusgraph is heading: a page where you sign in, see what your Fabric data is missing, tap a suggestion,
see a dry run and get a pull request. **That page does not exist yet**, and every shot of it carries the on-screen label
"Concept. In development."

| File | Format | Length | Size | Loudness |
| --- | --- | --- | --- | --- |
| krusgraph-vision-teaser-4x5.mp4 | 1080x1350, 30 fps (LinkedIn) | 43.3 s | 2.5 MB | -14.0 LUFS, true peak -1.6 dBFS |
| krusgraph-vision-teaser-9x16.mp4 | 1080x1920, 30 fps (site, Reels) | 43.3 s | 2.5 MB | -14.0 LUFS, true peak -1.6 dBFS |
| krusgraph-vision-short-9x16.mp4 | 1080x1920, 30 fps (Reels, Shorts) | 18.7 s | 1.1 MB | -14.0 LUFS, true peak -1.3 dBFS |

Captions are burned in (English); `.en.srt` and `.sv.srt` beside each cut; `captions.txt` has draft post texts.

## Real vs concept, shot by shot

| Shot | Label on screen | Source |
| --- | --- | --- |
| "Your SAP data is in Fabric" / "Weeks of data engineering" | none (a statement of the problem; no number) | |
| "Point at it. Tap." with the mascots | Concept. In development. | |
| Sign-in card and "Your data" card (17 tables read, 4 things missing) | Concept. In development. · Concept screen · synthetic SAP-shaped example | Mock screens; the 17 tables are the example's real table count |
| 17 of 17 keys unique, 32 of 34 links hold, order lines → orders 1 of 6 rows point at nothing | **Real today** · Krusgraph's check · synthetic SAP-shaped example | `evidence.validate` on `sap_demo.sqlite()` at `39daaa7` |
| 1 950 summed over the order lines, 2.6x too high, 750 once per order | **Real today** | `amounts.before_after` on the VBAK/VBAP finding, same commit |
| Dry run card, tap on "Make pull request" | Concept. In development. · Dry run and create exist today · this page is a concept | The create tools' dry run exists; this page and its pull-request button do not |
| Create card, "Pull request opened" | Concept. In development. | Not built (the pull-request path is planned) |
| "Your data stays in Fabric." | Concept. In development. · A design goal of the builder · not built yet | Not built. Today's hosted server passes sample rows and query results through memory (`docs/TRUST.md`) |
| End card: Get early access · krusgraph.com | "Concept. In development. Voice: AI-generated. Synthetic demo data." | There is no early-access page yet |

## Gates

| Gate | Result |
| --- | --- |
| Safe area (renderer, every 0.1 s, all three files) | Passed: 9:16 clear of top 230, bottom 420 and right 150 px; 4:5 in a 60-90 px margin; the caption covers no card |
| Frames decoded from the MP4s and looked at (contact sheets every 3 s) | Done. Nobody has watched it on a phone yet |
| Wording | No number spoken. No speed, compliance, certification, partnership or endorsement words; no "replaces data engineers"; no customer names; no Claude mention; no person's face or name. "Sign in with Microsoft" is a plain button without Microsoft's logo |
| Voice | Ava HD, +9 %, one request through the environment's Azure Speech proxy (no key stored or printed). "Voice: AI-generated" in a corner of every frame and on the end card |
| Sound | V3f's synthesized bed (no samples), under the voice |

## Open for the founder

1. The early-access page does not exist, and the privacy page says no e-mail addresses are stored; both must change
   before the end card can run.
2. "Your data stays in Fabric" is a design goal, labelled so; cut the shot if it should wait until it is built.
3. The short opens on "Making it usable?"; SAP appears at 3.6 s.

sha256: teaser-4x5 `c34a19899eb3ba21db506c5820b77b2144b8129c21ab754513e4de27fd210d95`, teaser-9x16
`0b215376e285383486b7f61d928f8257b1cfbe73cc6f8ac256a8faebeeea7138`, short-9x16
`39de3c40c94c052b38883a729dac295ec67c7938470d21f286692d28f6467055`.
