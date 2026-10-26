# Little Connections – Krusgraph design reference

The chosen visual direction for Krusgraph (October 2026). These are **design sketches**, not screenshots of
implemented features: sign-in, payment and partner workspace shown here are concepts unless the code says otherwise.

Start here:
1. `images/00-selected-direction.jpg` – the original concept that was chosen ("Good things happen when data connects.")
2. `images/01-home.jpg` – home page
3. `images/02-graph-explorer.jpg` – the product workspace: table list, graph canvas, and the "Why this connection?"
   panel that shows the rule behind a link
4. `DESIGN.md` – the six pages and their intended behaviour
5. `mascots/` – the three companions (coral guide "Onto" is a working name; sage thinker; lavender maker) and their poses

How to read them:
- Palette: coral `#ff7666`, sage `#91a88f`, lavender `#b5a0dc`, near white `#fdfbf8`; black rounded grotesk headings.
- The images were generated; small texts, key icons and cardinalities must be checked against real metadata and the
  inference rules. The image is a visual reference, not a schema.
- A cheerful mascot must never make a *suggested* connection look *verified*.
- No fake customer logos, user counts, testimonials or endorsements, ever.
- Product flow these sketches support: tables and metadata → explained keys and relationship suggestions → plan reviewed
  by the user → create or update a GraphQL API → query the data.

`IMAGE-PROMPTS-pages.md` and `IMAGE-PROMPTS-mascots.md` hold the prompts used, for consistent new images.

`motion/` holds the movement concept for the three companions (storyboards, `motion-spec.json` with proposed timings,
and an implementation brief in `HANDOFF-CLAUDE.md`). Proposed design values, not implemented and not measured.
