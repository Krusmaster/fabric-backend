# QA: krusgraph-data-agent-9x16.mp4

2026-11-17, round S1 (Opus). A draft for the founder's review. Nothing is scheduled or published.

**What it shows.** The v5 format: the hook "If you use / Microsoft Fabric [official Fabric logo] / you need to see this.",
the four steps in Claude, then the result. On the SAP-shaped example, the order total comes out at 1 950 summed over the
order lines, against 750 once per order (2.6x). Krusgraph writes a Fabric data agent's instructions that count each
order's total once. The film then shows one question and its answer.

## Real vs not possible

| On screen | Source |
| --- | --- |
| 1 950 over the order lines, 750 once per order, 2.6x too high | `amounts.before_after` on the VBAK/VBAP finding of `evidence.validate`, `sap_demo.sqlite()` (fabric-backend `9e5f1a8b984195c96ddd3bae6642a3ccee6693bc`) |
| "Order to cash agent", AMOUNTS: "never SUM(sap_vbak.NETWR) over sap_vbap rows" | `data_agent.draft`: the instructions `create_data_agent` writes in its dry run (dry_run=true is its default), quoted word for word from its "- Amounts:" line |
| "What is the total netwr per sap kna1?" and Demo Customer 10 600, Demo Customer 11 100, Other Client Customer 10 50, together 750 EUR | one of the example question/T-SQL pairs `data_agent.draft` writes for the agent, quoted word for word. Its T-SQL was run on the example rows (sqlite) and its rows are shown. The names come from sap_kna1.NAME1 for each returned MANDT+KUNNR. The sum is asserted equal to the engine's once-per-order total |

**Not done: no data agent was created in Fabric, and no agent answered.** This session has no Fabric credentials (no
token, no workspace; only Azure Speech is connected), so `create_data_agent` ran only as its dry run. The answer on
screen comes from the T-SQL the engine gives the agent as an example, run on our example rows. It is not a live reply
from a Fabric data agent, and the scene says so: "The agent's example question" and "Its T-SQL, run on our SAP-shaped
example rows". Also, `create_data_agent` has no recorded live run (`fabric_backend/tool_status.py`).

## Gates (build/build_short.sh in krusgraph-business, branch s1-shorts, marketing/shorts/2026-11-17-s1)

| Gate | Result |
| --- | --- |
| No UI imitation | The steps are plain text lines: no cards, badges, input box, cursor or click. The question is plain quoted text, not a chat bubble or input box. The tick on the 750 tile is a plain glyph with no circle. Usable as an ad |
| hyperframes lint / check | 0 errors in lint, runtime, layout, motion, contrast and audio. Warnings: lint 1 (dense captions file), craft 6 (reading time and small type: the instruction line is fitted to the card at about 20 px) |
| qa_c2.cjs on the live preview (826 frames, 711 settled) | Passed: safe area, words in their boxes, nothing past the frame, no tiny text, centred, icons whole, mascots not upscaled |
| Flash gate | 827 frames, luma 35.6-53.5, 0 jumps over 15 %, 0 findings |
| Silence gate | Voice stem: 11 pauses, all digital silence (no breaths). The V3f bed runs under the pauses by design (-37 to -32 dBFS rms) |
| Length | 27.57 s |
| Loudness | -14.0 LUFS, true peak -1.8 dBFS |
| Format | 1080 x 1920, 30 fps, H.264, AAC 48 kHz, 4.3 MB |
| End card | v5's, unchanged: logo, "for Microsoft Fabric" with the Fabric logo, "Link in bio", krusgraph.com, mascots, "Voice: AI-generated. Synthetic demo data." |
| Wording | No number is spoken. No speed, compliance, certification, partnership or endorsement words. "Use it in Claude"; no Claude logo. captions.txt includes the SAP-shaped example line and the independence line |

Voice: Ava HD, +9 %, one request via the environment's Azure Speech proxy (no key stored). Sound: V3f's bed, unchanged.

sha256 `1caa4babb308172daffdd30f10988231486e743fd827e886b97e596de97d5e63`
