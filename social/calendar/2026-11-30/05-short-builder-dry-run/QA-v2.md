# QA: s4, 'Builder: a dry run first' (-v2)

2026-11-16, round C2 v2, by build/hf/qa_report.py. Slot w3-05. Built with H1 v5's HyperFrames pipeline (hyperframes 0.9.56, gsap 3.15.0).

File: 1080x1920 30/1 fps H.264 + AAC 48000 Hz 2 ch, **25.80 s**, **-14.1 LUFS**, true peak -1.1 dBFS, 3.97 MB.

## Gates

| Gate | Result | Measured |
| --- | --- | --- |
| Flash gate (H1 flash_check.py: no flash, dip, white or blank frame, max 3 flashes a second) | PASS | 774 frames, luma 35.6-68.5, 0 frame-to-frame jumps over 15%, 0 findings |
| No white overlay on cuts | PASS | no overlay in the build (scenes ease out over 0.3 s, the next eases in; the ground stays #141418); brightest frame mean 68.5 |
| Silence gate (H1 pause_check: every pause in the voice below -60 dBFS, no breaths) | PASS | 16 pauses, loudest digital silence |
| HyperFrames lint and check | PASS | errors lint/runtime/layout/motion/contrast 0/0/0/0/0; warnings 1/0/0/0/0 (the lint warning: the captions file has many timed elements, as in H1) |
| Centred layout and safe areas (qa_c2.cjs, every frame) | PASS | 773 frames, 635 settled; safe area y 288-1248, x 192-888 (YouTube's right edge, mirrored), below y 840 x 300-780 (TikTok's buttons); worst margin difference per scene: scene 1 8.7 px, scene 2 0.0 px, scene 3 0.0 px, scene 4 0.0 px, scene 5 0.0 px, scene 6 0.0 px, scene 7 8.9 px |
| Loudness -14 LUFS (within 0.5 LU), true peak below -1 dBTP | PASS | -14.1 LUFS integrated, true peak -1.1 dBFS |
| Length 15-30 s | PASS | 25.80 s |
| Size under 8 MB | PASS | 3.97 MB |

## The requirements

| Requirement | Where |
| --- | --- |
| Hook 'If you use / Microsoft Fabric [logo] / you need to see this.' | Line 1, said and shown: H1 v5's hook composition (three centred lines, the official Fabric logo with its glint), 0-2.83 s |
| Official Fabric logo on the end frame | End card: 'for Microsoft Fabric' + fabric_48_color (npm @fabric-msft/svg-icons 12.0.0, unchanged), held to the last frame |
| V3f premium synth sound bed | sound_premium.py (V3f, unchanged) driven by sound_bed_hf.py: pad, air, ticks, resolve, swell; bed -26.08 dB, 19 dB under the voice over speech, ducked 4 dB; in the voice's pauses the bed plays on at -36.9 to -32.8 dBFS RMS (no voice, no breath) |
| Ava HD voice about 0.93x v4 | en-US-Ava:DragonHDLatestNeural at +9%; measured 7.301 s at v4's +21% and 7.789 s at +9% for the same three lines: 0.937x |
| 'Voice: AI-generated' small print | End card small print, 28 px, from the end card's start to the last frame |

## Script, as said

1. 0.10-2.65 s: If you use Microsoft Fabric, you need to see this.
2. 2.95-6.11 s: Meet Builder. One idea today: a dry run first.
3. 6.41-10.02 s: Type “start Krusgraph” in Claude. There are 9 steps.
4. 10.32-14.90 s: 8 of them only read: the map, the check, the doubled totals, and the dry run.
5. 15.20-18.39 s: The last one: “Create, only on your confirmation”.
6. 18.69-20.69 s: Nothing is built until you say yes.
7. 21.09-24.27 s: Try it in your browser: krusgraph.com/check
