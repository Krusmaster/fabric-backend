# Mascot art needed (n216)

The founder asked on 11 November 2026 for one look for Onto, Thinker and Builder everywhere: the glossy, soft 3D figures
of the overview film and the home page, not the flatter cartoon drawn in SVG. This page records what the repository has,
what n216 changed, and the renders that are still missing. With the renders below, every remaining flat figure can be
swapped the same way, without drawing a character in code.

## What the repository has

| Source | What it is | Usable as a cut-out? |
| --- | --- | --- |
| `fabric_backend/static/media/krusgraph-overview-web.mp4` (1920 x 1080) | The overview film; the closing frame (43 s) shows the three resting side by side, about 90 px wide, on a flat #F4F4F4 ground | Yes: the only 3D render in the repository. `tools/mascot_renders.py` cuts it out |
| `krusgraph-overview-web-4x5.mp4` (1080 x 1350) | The same film for phones; the figures are smaller (about 60 px) | No: smaller than the 16:9 film |
| `krusgraph-overview-poster.webp` | The film's poster | No: no mascots in it |
| The film's middle part | The three as small figures (about 40 px) beside the map | No: too small |
| `docs/design/little-connections/mascots/*.jpg` | Early concept sheets, older names and colours, on a painted ground | No: not the film's characters, not cut out |
| `fabric_backend/static/mascots.js`, `fabric_backend/mcp_apps_mascots.py` | The flat SVG figures with poses (the site's guides, /mascots, the MCP Apps cards) | They are the flat style this round replaces where it can |
| A brag skill's assets, a `/mascots` route with 3D renders, a sales deck | Not in this repository | — |

`tools/mascot_renders.py` writes `fabric_backend/static/mascots/{onto,thinker,builder}.webp` and `.png` and
`workload/Workload/app/assets/mascots/*.png`: 112 x 112 px, transparent ground, each figure at the film's scale and
ground line, the film's contact shadow replaced by a soft shadow in a dark tint of the figure's colour so it works on a
dark page. 112 px is crisp at 2x up to 56 CSS px.

## What n216 changed

| Place | Before | Now |
| --- | --- | --- |
| Home page and /choose: "Choose how you work", the four product cards | Flat SVG mascot hugging a drawn prop | The 3D figure (56 px, 2x) with the prop as a small badge at its lower right; one `role="img"` with alt text per card; hidden by the site's mascot switch |
| Fabric workload page: banner (`Workload_Hub_Banner.png`) | Flat figures at 168 px | 3D figures at 112 px, their render size, so they stay sharp |
| Fabric workload page: Get started card (`Workload_Hub_GetStarted_1.png`) | Flat figures at 52 px | 3D figures at 56 px |
| Fabric workload page: quick look (`Workload_Hub_SlideMedia_1.png`) | Flat figures at 64 px | 3D figures at 64 px |
| Krusgraph Model editor: Onto, Thinker and Builder beside their messages, the data flow's Builder, the finish banner | Flat SVG with arm poses | 3D figure at 48 px; the pose is kept as `data-pose` and drawn as a small lean, tilt or hop of the whole figure (still under reduced motion); the "Mascots: on/off" switch removes them as before |
| Item icon, workload icon, favicon | The logo mark (Fluent-style container for the item) | Unchanged: a mascot does not read at 16-32 px, so the icons stay the three-dot logo mark |

Fabric's asset rules, from Microsoft Learn, *Product Manifest* (`fabric/extensibility-toolkit/manifest-product`, ms.date
15 December 2025, read 11 November 2026): at most 15 files in the assets folder, each at most 1.5 MB, only `.jpeg`,
`.jpg` and `.png`, each referenced. The package has 8 images, the largest 82 KB; `tests/test_workload_manifest.py`
checks all four rules.

## Still flat, waiting for renders

These keep the flat SVG figures because they need a pose or a prop the film does not have:

- The site's guides and helpers drawn by `static/mascots.js`: /check (loading, Onto's notes, the follower), /start,
  /support, /partners, /use-cases, the local demo and the chat demo (poses look, point, explain, listen, calm,
  celebrate, think, notice; idle bounce, breathe, nod; the Builder's build sequence with its tool).
- /mascots, the page that shows the figures and their poses.
- The MCP Apps cards in Claude (`mcp_apps_mascots.py`): inline SVG, posed per answer, inside the card's own HTML;
  moving them to images means deciding how a card loads them (embedded or fetched), which is not part of n216.

## Renders to produce

Every render: the film's characters, materials and light (glossy, soft 3D, as in the closing frame); one figure per
file; **PNG with a transparent background** (no ground, no baked-in shadow: the pages add their own); the figure centred
and standing on the bottom edge with 6 % padding; square **512 x 512 px** (crisp at 2x up to 256 CSS px, enough for the
1920 x 240 banner at 168 px and the largest page slot). Names below are the file names to deliver; put them in
`fabric_backend/static/mascots/` and the next round wires them in.

### Props for the product cards (most wanted)

| File | Character | Pose | Prop |
| --- | --- | --- | --- |
| `onto-table.png` | Onto (sage green, wide and low) | Hugging the prop against its front, arms around it | A small data table: white card, mustard header row, grey grid lines |
| `thinker-bubble.png` | Thinker (lavender, round pear) | Hugging the prop | A white speech bubble with three dots in coral, sage and lavender |
| `builder-screen.png` | Builder (coral, upright egg) | Hugging the prop | A small app screen: white window, three dots in its title bar, a sage tile and three text lines |
| `onto-code.png` | Onto | Hugging the prop | A white rounded card with code brackets `< / >`, the slash in coral |

### Poses for the editor and the site's guides

For each of Onto, Thinker and Builder (24 files: `<character>-<pose>.png`):

| Pose | What it shows | Used by |
| --- | --- | --- |
| `rest` | Standing, arms down, eyes forward (as the film's closing frame, at 512 px) | Everywhere; replaces the 112 px cut from the film |
| `point` | One arm raised to the side, pointing at the text next to it | Editor (Builder in the data flow and the finish), /check |
| `explain` | One arm open toward the viewer, slight lean | Editor (Onto), /check notes |
| `think` | Head tilted, one arm at the chin | Editor (Thinker), chat demo |
| `notice` | Eyes wide, small lean back, arms up a little | Editor (Thinker when a check failed) |
| `calm` | Eyes half closed, settled | Editor, /use-cases |
| `celebrate` | Both arms up, a small hop | Editor finish banner, /check |
| `look` | Looking to the side, toward the content | /check, /start, /support |

An animated hop or wave is not needed: the pages animate the still.
