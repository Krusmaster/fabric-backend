# QA: "Advanced analytics" (DRAFT, not approved)

2026-11-22, round FV4. A third film in the style of FV2's "A few taps", from the founder's own script: "Your data is
ready and the data engineering is done. Let's leverage that data with advanced analytics! Boom! With Krusgraph it's
done in a heartbeat. Krusgraph workload on Microsoft Fabric." **Nothing is scheduled, posted or published.** Silent
with text and a synthesized sound (`source/sound.py`: FV2's instruments with this film's cue times, and a heartbeat in
scene 5). 9:16 only.

| File | Format | Length | Size | Loudness |
| --- | --- | --- | --- | --- |
| krusgraph-advanced-analytics-9x16.mp4 | 1080x1920, 30 fps, H.264 + AAC 192 kb/s | 19.5 s | 3.9 MB | -13.5 LUFS integrated, peak -0.5 dBFS |
| cover-9x16.jpg | 1080x1920, the frame at 12.6 s ("Boom!" and the three analyses) | | | |

## Shot by shot, and what backs it

| Time | On screen | What backs it today |
| --- | --- | --- |
| 0.0-3.2 s | "Your data is ready. The data engineering is done." Pipeline, Semantic model, Data products ticked | FV2's and FV3's films (pipeline, model on gold DPM1, data products) |
| 3.2-6.0 s | "Let's put it to work with advanced analytics!" | The founder's line, lightly shortened |
| 6.0-10.4 s | "Three steps, by rules." 1 Feature table → 2 Model → 3 Predictions in gold, each ticked | `docs/ADVANCED-ANALYTICS.md` (AA1, merged 22 November 2026): the three stages, notebooks written by fixed rules |
| 10.4-13.8 s | "Boom!" Weekly orders forecast (backtested on 8 weeks), Customer segments (grouped by how they buy), Top 10 drivers | AA1's three recommended analyses: a seasonal naive baseline and a regression backtested on 8 weeks; k-means on RFM; a descriptive top 10 |
| 13.8-16.4 s | "With Krusgraph it's done in a heartbeat." An ECG line | The founder's line. **A figure of speech, not a measured time:** creating the notebooks takes a few taps, but training runs in the user's own Fabric workspace when they press Run now, and that takes as long as Spark takes |
| 16.4-19.5 s | Logo, "Krusgraph", "Workload on Microsoft Fabric" with a "preview" tag, krusgraph.com, mascots | The workload runs in the founder's tenant as "Krusgraph (preview)"; `Krusgraph.Modeler` is not yet registered (`docs/MODELER-GO-LIVE.md`), so "preview" stays. Fine print: "Demo on synthetic data. You run each notebook in your own workspace. Krusgraph is independent and not affiliated with Microsoft." |

No Microsoft or Claude logo; the icons are drawn for this film.

## Gates

| Gate | Result |
| --- | --- |
| Safe area | As FV2: text and cards between y 300 and 1500, x 60 to 1020 |
| Frames looked at | Contact sheet every 1 s and stills at 2.6, 5.4, 9.8, 13.2, 15.6 and 19.0 s (the end card was set on two lines after the first still). Not watched on a phone yet |
| Wording | No sales words from `tests/test_site.py`; no number claimed beyond AA1's own "8 weeks" and "top 10"; no customer; no "partner", "certified" or endorsement |

## Open for the founder

1. "Done in a heartbeat" is your line and reads as a figure of speech; the fine print says each notebook runs in your
   own workspace. Drop or soften it if a reader could take it as a promised speed.
2. "preview" after "Workload on Microsoft Fabric": keep it until `Krusgraph.Modeler` is live in the Workload Hub.

## Render again

From the repository root (`render.js` is FV2's):

```bash
cp social/films/2026-11-22-few-taps/source/render.js social/films/2026-11-22-advanced-analytics/source/ && node social/films/2026-11-22-advanced-analytics/source/render.js silent.mp4
python3 social/films/2026-11-22-advanced-analytics/source/sound.py sound.wav
ffmpeg -y -i silent.mp4 -i sound.wav -filter_complex "[1]loudnorm=I=-14:TP=-1.5:LRA=11[a]" -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -shortest krusgraph-advanced-analytics-9x16.mp4
```

sha256: `34d53a2d56757f7583f58200263ca846b9df1e5859fa105b8315116007c5aa8e`
