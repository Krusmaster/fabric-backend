# QA: "A few taps" (DRAFT, not approved)

2026-11-22, round FV2. A draft for the founder's review. **Nothing is scheduled, posted or published.**

The founder asked for a simpler, general film after the vision teaser (FV1, PR #126): no SAP trap, no double-counted
order total, just "tap into your Fabric data and, after a few taps, you have your data pipeline and Power BI report".
Silent with text, 9:16 only. Inspiration: Lovable's ads put one chat box at the centre and talk about the result
("Idea to app in seconds"); Strawberry sells AI "colleagues" with a personality, which is what the mascots are here.
Nothing of theirs is used: the colours, fonts (Fredoka and Nunito from `fabric_backend/static/fonts/`), logo and
mascots are Krusgraph's own, and the three item icons are drawn for this film. No Microsoft logo.

| File | Format | Length | Size | Loudness |
| --- | --- | --- | --- | --- |
| krusgraph-few-taps-9x16.mp4 | 1080x1920, 30 fps, H.264 + AAC 192 kb/s | 19.5 s | 4.0 MB | -13.1 LUFS integrated, peak -1.0 dBFS |
| cover-9x16.jpg | 1080x1920, the frame at 15.0 s ("Boom." and the three cards) | | | |

## Shot by shot, and what backs it

| Time | On screen | What it says, and what backs it today |
| --- | --- | --- |
| 0.0-2.6 s | "Your data is in Fabric." Table chips: orders, customers, products, invoices ... | Generic table names, no customer, no SAP names |
| 2.6-5.2 s | "Making it useful? Pipelines. Models. Reports. Years." | The problem, no number |
| 5.2-9.2 s | "Just ask." A chat box; "Start Krusgraph" is typed and sent | "Start Krusgraph" is the start tool and prompt of the hosted connector |
| 9.2-13.0 s | "A few taps." Your data, Check, Decide, Dry run, Create, each ticked | The guided path's five steps (SM2, SM3). SM1 measured the path at 10 taps |
| 13.0-16.4 s | "Boom." Data pipeline, Semantic model, Power BI report | `create_pipeline`, `create_semantic_model` and `create_report` exist; the default build is pipeline, model and agent (SM3), the report is built on the model (ED1) |
| 16.4-19.5 s | Logo, "Krusgraph", "From Fabric data to Power BI in a few taps.", krusgraph.com, the three mascots | Fine print: "Demo on synthetic data. Krusgraph is independent and not affiliated with Microsoft." |

No concept label is needed: every step shown exists today. The film shows no real screen; it is animated text and
cards, and the chat box is drawn, not Claude's interface (no Claude name or logo).

## Sound

Synthesized in `source/sound.py` with numpy (no samples, no licence needed): a chord pad per scene, a plucked
arpeggio and a kick on the beat from 5.2 s (four beats per 2.6 s scene step), hats from 9.2 s, a click on the send tap
(8.25 s) and on each of the five steps (10.2 to 12.2 s), typing ticks, a whoosh into a low boom at 13.0 s, and a fade
out. Mixed and normalised with ffmpeg `loudnorm` (I=-14, TP=-1.5). **Nobody has listened to it yet**; the round could
only measure it. A licensed music track can replace it (see below).

## Gates

| Gate | Result |
| --- | --- |
| Safe area | Text and cards between y 300 and 1500 and x 60 to 1020; the bottom 420 px (Reels UI) hold nothing but the glow |
| Frames looked at | Contact sheet every 1 s, and stills at 1.5, 4.0, 8.3, 11.8, 15.0 and 18.8 s. Not watched on a phone yet |
| Wording | No sales words from `tests/test_site.py`; no number claimed; no customer; no "partner", "certified" or Microsoft endorsement; no Claude mention |
| Source | `source/film.html` renders the same frames as the film (checked pixel for pixel at 8.3 and 18.8 s) |

## Render again

From the repository root, with Playwright's Chromium and ffmpeg:

```bash
node social/films/2026-11-22-few-taps/source/render.js silent.mp4
python3 social/films/2026-11-22-few-taps/source/sound.py sound.wav
ffmpeg -y -i silent.mp4 -i sound.wav -filter_complex "[1]loudnorm=I=-14:TP=-1.5:LRA=11[a]" -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -shortest krusgraph-few-taps-9x16.mp4
```

With a licensed music track instead of the synthesized one (`musik.mp3`):

```bash
ffmpeg -y -i silent.mp4 -i musik.mp3 -filter_complex "[1]atrim=0:19.5,afade=t=in:d=0.5,afade=t=out:st=17.5:d=2,loudnorm=I=-14:TP=-1.5[a]" -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -shortest krusgraph-few-taps-9x16.mp4
```

## Open for the founder

1. Watch and listen on a phone.
2. "Years." in the problem line is a statement, not a measured figure; drop it if it reads as a claim.
3. Choose: keep the synthesized sound, or a licensed track.

sha256: `82d4550350572163aca923be9f86fca1654c4865ac2fc0c85f4aed323fde8fbe`
