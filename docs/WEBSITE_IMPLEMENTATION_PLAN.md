Not applied: the founder kept the previous home page on 10 Nov 2026 (n194).

# Website implementation plan (round n190)

P0 is done in n190 (see `docs/WEBSITE_UX_AUDIT.md`, section 7). P1 starts only when P0 is deployed and green, and P2
after P1. Effort is in rounds of one session: S = part of a round, M = one round, L = two rounds or more.

## P0 (n190, done)

1. Hero: one promise, two CTAs and the 2 000 → 1 000 badge
2. Four intent tiles → `/check?example=sample&intent=…`, acted on by check.js
3. The map under the hero (`home_map_html`), and a before/after computed from the engine's run
4. `claims.py`: one chip per output on home, /start, /choose, /pricing, /docs and the Markdown twins
5. The new home order; the long text (session replay, film, hub, FAQ, developer note) left the home page. Its content
   lives on /docs, /it, /privacy, /partners and /support
6. Navigation: five entries and *Try free demo*

## P1: onboarding and guidance

| # | What | Effort | Notes |
| --- | --- | --- | --- |
| 1 | **Route A, no account:** a short "you are here" bar on /check when it comes from an intent tile ("Find broken relationships · sample data · step 1 of 3"), with *Try your own files* and *Connect Microsoft Fabric* at the end | M | Builds on `intent`. No account, nothing stored |
| 2 | **Route B, connect Fabric:** /start opens with a two-way choice, *In Fabric, no AI* (Krusgraph for Fabric pilot) or *In Claude* (connector), and the steps under each. Today the three cards and the three steps sit side by side | M | Reuse `offering.WAYS` and the steps; keep `#step-3` working |
| 3 | **Mascots guide the /check demo:** Onto for the map, Thinker for issues, Builder for the build tiles, each in the guided demo's step panel for its intent; never next to a partner name | M | `mascots.js` poses exist; the guide's text comes from the run |
| 4 | **Pricing presentation:** three cards with a chip line each (`claims.line_html`) and one sentence on what is free; the pilot deliveries as a checklist | S | Text only from /pricing today |
| 5 | **Intent → result copy:** after an intent lands, one sentence on what was opened and what to do next (from the run) | S | check.js |
| 6 | Status chips on /use-cases/build and in the docs' tool table | S | `claims.chip_html` |
| 7 | Clean-up: the session replay's CSS and site.js code, and its CSS-only tests (tests/test_n165_replay_progress.py, `.session` in site.css), now that no page renders it | S | Dead code since n190 |

## P2: warmth

| # | What | Effort | Notes |
| --- | --- | --- | --- |
| 1 | Motion: the map draws its links in sequence on first view (IntersectionObserver), off with prefers-reduced-motion | M | map.js already has a `still` option |
| 2 | Illustrations: one drawn scene per *Security and proof* card and per step, in the mascots' style, without partner logos | L | SVG, inline, small |
| 3 | A labelled synthetic-data screenshot of the Krusgraph Model item for the *Ways to use it* section | S | From the workload's dev server with synthetic data; never a customer tenant |
| 4 | The overview film back on the home page as a link, not inline | S | `film_html` |
| 5 | Measure Core Web Vitals on the deployed site (LCP, CLS, INP) before and after, and record them in `docs/SITE.md` | S | Needs the deployed site |

## Order

P0 deploy → measure → P1.1 and P1.2 together → P1.3 → P1.4–6 → P2.
