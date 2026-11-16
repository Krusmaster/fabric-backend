# QA: s2, 'From SAP-shaped tables to data products' (-v2)

2026-11-16, round C2 v2, by build/hf/qa_report.py. Slot w2-05. Built with H1 v5's HyperFrames pipeline (hyperframes 0.9.56, gsap 3.15.0).

File: 1080x1920 30/1 fps H.264 + AAC 48000 Hz 2 ch, **23.73 s**, **-14.0 LUFS**, true peak -1.4 dBFS, 3.98 MB.

## Gates

| Gate | Result | Measured |
| --- | --- | --- |
| Flash gate (H1 flash_check.py: no flash, dip, white or blank frame, max 3 flashes a second) | PASS | 712 frames, luma 35.8-60.2, 0 frame-to-frame jumps over 15%, 0 findings |
| No white overlay on cuts | PASS | no overlay in the build (scenes ease out over 0.3 s, the next eases in; the ground stays #141418); brightest frame mean 60.2 |
| Silence gate (H1 pause_check: every pause in the voice below -60 dBFS, no breaths) | PASS | 12 pauses, loudest digital silence |
| HyperFrames lint and check | PASS | errors lint/runtime/layout/motion/contrast 0/0/0/0/0; warnings 1/0/0/0/0 (the lint warning: the captions file has many timed elements, as in H1) |
| Centred layout and safe areas (qa_c2.cjs, every frame) | PASS | 712 frames, 575 settled; safe area y 288-1248, x 192-888 (YouTube's right edge, mirrored), below y 840 x 300-780 (TikTok's buttons); worst margin difference per scene: scene 1 10.3 px, scene 2 0.0 px, scene 3 0.0 px, scene 4 0.0 px, scene 5 0.0 px, scene 6 0.0 px, scene 7 8.9 px |
| Loudness -14 LUFS (within 0.5 LU), true peak below -1 dBTP | PASS | -14.0 LUFS integrated, true peak -1.4 dBFS |
| Length 15-30 s | PASS | 23.73 s |
| Size under 8 MB | PASS | 3.98 MB |

## The requirements

| Requirement | Where |
| --- | --- |
| Hook 'If you use / Microsoft Fabric [logo] / you need to see this.' | Line 1, said and shown: H1 v5's hook composition (three centred lines, the official Fabric logo with its glint), 0-2.73 s |
| Official Fabric logo on the end frame | End card: 'for Microsoft Fabric' + fabric_48_color (npm @fabric-msft/svg-icons 12.0.0, unchanged), held to the last frame |
| V3f premium synth sound bed | sound_premium.py (V3f, unchanged) driven by sound_bed_hf.py: pad, air, ticks, resolve, swell; bed -24.3 dB, 19 dB under the voice over speech, ducked 4 dB; in the voice's pauses the bed plays on at -37.7 to -33.3 dBFS RMS (no voice, no breath) |
| Ava HD voice about 0.93x v4 | en-US-Ava:DragonHDLatestNeural at +9%; measured 7.301 s at v4's +21% and 7.789 s at +9% for the same three lines: 0.937x |
| 'Voice: AI-generated' small print | End card small print, 28 px, from the end card's start to the last frame |

## Script, as said

1. 0.10-2.55 s: If you use Microsoft Fabric, you need to see this.
2. 2.85-5.39 s: Your SAP tables are in Fabric. Who owns what?
3. 5.69-9.14 s: Krusgraph checks the links first: 32 of 34 hold.
4. 9.44-13.94 s: Then it suggests two data products: Order to cash, and Customer master.
5. 14.24-16.85 s: Order to cash uses customers from Customer master.
6. 17.15-18.54 s: Each gets an owner you choose.
7. 18.94-22.22 s: Try it in your browser: krusgraph.com/check
