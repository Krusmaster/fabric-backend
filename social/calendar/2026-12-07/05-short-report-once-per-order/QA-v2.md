# QA: s6, 'A report that counts each order once' (-v2)

2026-11-16, round C2 v2, by build/hf/qa_report.py. Slot w4-05. Built with H1 v5's HyperFrames pipeline (hyperframes 0.9.56, gsap 3.15.0).

File: 1080x1920 30/1 fps H.264 + AAC 48000 Hz 2 ch, **25.93 s**, **-14.0 LUFS**, true peak -1.4 dBFS, 4.32 MB.

## Gates

| Gate | Result | Measured |
| --- | --- | --- |
| Flash gate (H1 flash_check.py: no flash, dip, white or blank frame, max 3 flashes a second) | PASS | 778 frames, luma 35.2-53.6, 0 frame-to-frame jumps over 15%, 0 findings |
| No white overlay on cuts | PASS | no overlay in the build (scenes ease out over 0.3 s, the next eases in; the ground stays #141418); brightest frame mean 53.6 |
| Silence gate (H1 pause_check: every pause in the voice below -60 dBFS, no breaths) | PASS | 11 pauses, loudest digital silence |
| HyperFrames lint and check | PASS | errors lint/runtime/layout/motion/contrast 0/0/0/0/0; warnings 1/0/0/0/0 (the lint warning: the captions file has many timed elements, as in H1) |
| Centred layout and safe areas (qa_c2.cjs, every frame) | PASS | 778 frames, 642 settled; safe area y 288-1248, x 192-888 (YouTube's right edge, mirrored), below y 840 x 300-780 (TikTok's buttons); worst margin difference per scene: scene 1 12.4 px, scene 2 0.0 px, scene 3 0.0 px, scene 4 0.0 px, scene 5 0.0 px, scene 6 0.0 px, scene 7 8.9 px |
| Loudness -14 LUFS (within 0.5 LU), true peak below -1 dBTP | PASS | -14.0 LUFS integrated, true peak -1.4 dBFS |
| Length 15-30 s | PASS | 25.93 s |
| Size under 8 MB | PASS | 4.32 MB |

## The requirements

| Requirement | Where |
| --- | --- |
| Hook 'If you use / Microsoft Fabric [logo] / you need to see this.' | Line 1, said and shown: H1 v5's hook composition (three centred lines, the official Fabric logo with its glint), 0-2.92 s |
| Official Fabric logo on the end frame | End card: 'for Microsoft Fabric' + fabric_48_color (npm @fabric-msft/svg-icons 12.0.0, unchanged), held to the last frame |
| V3f premium synth sound bed | sound_premium.py (V3f, unchanged) driven by sound_bed_hf.py: pad, air, ticks, resolve, swell; bed -25.53 dB, 19 dB under the voice over speech, ducked 4 dB; in the voice's pauses the bed plays on at -39.0 to -31.3 dBFS RMS (no voice, no breath) |
| Ava HD voice about 0.93x v4 | en-US-Ava:DragonHDLatestNeural at +9%; measured 7.301 s at v4's +21% and 7.789 s at +9% for the same three lines: 0.937x |
| 'Voice: AI-generated' small print | End card small print, 28 px, from the end card's start to the last frame |

## Script, as said

1. 0.10-2.74 s: If you use Microsoft Fabric, you need to see this.
2. 3.04-6.26 s: A report on SAP-shaped tables. Is the total right?
3. 6.56-9.24 s: The semantic model keeps the order amount on the order header.
4. 9.54-13.14 s: Net order value: EUR 750, counted once per order.
5. 13.44-16.28 s: Summed over the order lines, it would be 1 950.
6. 16.58-20.93 s: After the build, Krusgraph reads the model back and counts the figures again from the rows.
7. 21.33-24.43 s: Try it in your browser: krusgraph.com/check
