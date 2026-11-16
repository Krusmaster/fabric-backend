# QA: s1, 'Before an agent sums anything, count' (-v2)

2026-11-16, round C2 v2, by build/hf/qa_report.py. Slot w2-02. Built with H1 v5's HyperFrames pipeline (hyperframes 0.9.56, gsap 3.15.0).

File: 1080x1920 30/1 fps H.264 + AAC 48000 Hz 2 ch, **27.50 s**, **-14.0 LUFS**, true peak -1.5 dBFS, 4.11 MB.

## Gates

| Gate | Result | Measured |
| --- | --- | --- |
| Flash gate (H1 flash_check.py: no flash, dip, white or blank frame, max 3 flashes a second) | PASS | 825 frames, luma 33.8-52.4, 0 frame-to-frame jumps over 15%, 0 findings |
| No white overlay on cuts | PASS | no overlay in the build (scenes ease out over 0.3 s, the next eases in; the ground stays #141418); brightest frame mean 52.4 |
| Silence gate (H1 pause_check: every pause in the voice below -60 dBFS, no breaths) | PASS | 16 pauses, loudest digital silence |
| HyperFrames lint and check | PASS | errors lint/runtime/layout/motion/contrast 0/0/0/0/0; warnings 1/0/0/0/0 (the lint warning: the captions file has many timed elements, as in H1) |
| Centred layout and safe areas (qa_c2.cjs, every frame) | PASS | 825 frames, 689 settled; safe area y 288-1248, x 192-888 (YouTube's right edge, mirrored), below y 840 x 300-780 (TikTok's buttons); worst margin difference per scene: scene 1 11.6 px, scene 2 0.0 px, scene 3 0.0 px, scene 4 0.0 px, scene 5 0.0 px, scene 6 7.3 px, scene 7 8.9 px |
| Loudness -14 LUFS (within 0.5 LU), true peak below -1 dBTP | PASS | -14.0 LUFS integrated, true peak -1.5 dBFS |
| Length 15-30 s | PASS | 27.50 s |
| Size under 8 MB | PASS | 4.11 MB |

## The requirements

| Requirement | Where |
| --- | --- |
| Hook 'If you use / Microsoft Fabric [logo] / you need to see this.' | Line 1, said and shown: H1 v5's hook composition (three centred lines, the official Fabric logo with its glint), 0-2.54 s |
| Official Fabric logo on the end frame | End card: 'for Microsoft Fabric' + fabric_48_color (npm @fabric-msft/svg-icons 12.0.0, unchanged), held to the last frame |
| V3f premium synth sound bed | sound_premium.py (V3f, unchanged) driven by sound_bed_hf.py: pad, air, ticks, resolve, swell; bed -25.92 dB, 19 dB under the voice over speech, ducked 4 dB; in the voice's pauses the bed plays on at -37.3 to -33.7 dBFS RMS (no voice, no breath) |
| Ava HD voice about 0.93x v4 | en-US-Ava:DragonHDLatestNeural at +9%; measured 7.301 s at v4's +21% and 7.789 s at +9% for the same three lines: 0.937x |
| 'Voice: AI-generated' small print | End card small print, 28 px, from the end card's start to the last frame |

## Script, as said

1. 0.10-2.36 s: If you use Microsoft Fabric, you need to see this.
2. 2.66-5.52 s: Before an agent sums anything, count three things.
3. 5.82-9.25 s: 1. Are the keys unique? In our example, 17 of 17.
4. 9.55-13.41 s: 2. Do the links hold? 32 of 34. One points at nothing.
5. 13.71-19.91 s: 3. Where does the amount live? Over the joined lines, 1 950. Once per order, 750.
6. 20.20-22.42 s: Krusgraph counts all three against your rows.
7. 22.82-26.00 s: Try it in your browser: krusgraph.com/check
