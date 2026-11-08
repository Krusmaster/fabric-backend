# The mascots' new names and colours: a prompt for Lovable, and what to change by hand

The founder decided on 7-8 November 2026 that the three mascots' names follow their colours differently. The repository
was changed in round n164 (`fabric_backend/static/mascots.js` `KINDS`, the `--onto`, `--thinker` and `--builder` tokens
in `site.css`, the MCP Apps cards, the chat demo, `/mascots`). The Shop Desk app in Lovable is not in this repository;
paste the prompt below into Lovable to make the same change there.

| Name | Colour | Hex (fill / light / dark) | Role | Figure |
| --- | --- | --- | --- | --- |
| Onto | green | `#9DB8A0` / `#CDDFCD` / `#84A188` | maps how the data connects (the ontology) and says the numbers | wide and low, like a cushion |
| Thinker | violet | `#A99AD8` / `#D4CBF0` / `#9282C6` | checks against the rows, finds what does not hold, asks the questions | a round pear, leaning |
| Builder | coral | `#F2735C` / `#FFB29A` / `#D9604B` | creates the API, model, report or ontology, always with a dry run first | an upright egg, leaning forward |

Before: Onto was coral, the Thinker green, the Builder violet. The logo (three dots) stays as it is.

## Prompt to paste into Lovable (Shop Desk)

```text
Rename how our three mascots map to their colours. Keep every place where a mascot speaks; only change which
figure and colour each name uses, and the text that describes them.

New mapping (use these exact names, colours and roles everywhere):
- Onto = GREEN (#9DB8A0; light #CDDFCD; dark #84A188). The wide, low, cushion-shaped figure.
  Role: maps how the data connects (the ontology) and says the numbers (tables, keys, links found, counts).
- Thinker = VIOLET (#A99AD8; light #D4CBF0; dark #9282C6). The round pear-shaped figure, leaning.
  Role: checks against the rows, finds what does not hold, asks the questions.
- Builder = CORAL (#F2735C; light #FFB29A; dark #D9604B). The upright egg-shaped figure, leaning forward.
  Role: creates the API, model, report or ontology, always with a dry run first.

What to change:
1. Wherever a mascot is drawn for a name (component, image, SVG, avatar, icon), show the figure and colour above
   for that name. If the colour is a theme token (for example a CSS variable or a Tailwind colour), define one token
   per name (onto, thinker, builder) pointing at green, violet and coral, with soft and text variants for light and
   dark mode, and use those tokens instead of a fixed colour.
2. Keep each role where it is: Onto still says the counts, the Thinker still raises the open points and questions,
   the Builder still announces what would be created (and does a dry run first).
3. Update every text that describes a mascot by colour or role, including alt texts and aria-labels:
   - Onto: "Onto, the green one who maps how the data connects and says the numbers"
   - Thinker: "Thinker, the violet one who checks against the rows and asks the questions"
   - Builder: "Builder, the coral one who builds, always after a dry run"
   Remove any remaining "coral Onto", "green/sage Thinker", "violet/lavender Builder" or "maker".
4. The mascots are glad (celebrate, heart, confetti) only when every check passes; never on a failed check, an error
   or a cancelled action. Keep that rule.
5. Do not change the logo, the app's other colours, data, API calls or layout.

When done, list every file you changed and show me Onto, Thinker and Builder side by side in light and dark mode.
```

## Outside the repository, to change by hand

- **The PowerPoint deck**: every slide that shows or names a mascot (the cover and the "how it works" slides, if they
  have them): Onto green, Thinker violet, Builder coral, and the speaker notes and alt texts that name a colour.
- **The Shop Desk app in Lovable**: with the prompt above; afterwards check its alt texts and its dark mode.
- **The design sketches** in `docs/design/little-connections/mascots/*.jpg` carry the old names in their pixels
  (02 "Onto" in coral, 03 "The thinker" in sage, 04 "The maker" in lavender). They are kept as the record of the design
  work, with a note in their README; new sketches would need new images.
- **The overview film** (`fabric_backend/static/media/`) shows the three figures (green cushion, violet pear, coral
  egg) without names or roles, and its captions name none of them: nothing to change.
- **The LinkedIn cover** is already correct; nothing to do.
