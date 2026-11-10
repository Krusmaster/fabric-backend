Not applied: the founder kept the previous home page on 10 Nov 2026 (n194).

# Website copy rewrite (round n190)

The core story, from the UX review of 9 November 2026: *Krusgraph understands how your business data connects, checks
that the relationships hold against your rows, and gets the data ready for reports, apps and AI agents.*
(`claims.STORY`.)

## Headline: the three candidates

| Candidate | For | Against |
| --- | --- | --- |
| Turn your Fabric data into something useful. | Short, outcome-led | Says nothing Krusgraph does differently. "Useful" is a claim anyone could make, and it hints that the data is useless today. |
| From messy tables to trusted data products. | Names the outcome (trust) | "Data products" is one of the terms the review says competes for attention, and "messy" blames the visitor. |
| **Your data already has connections. Krusgraph finds them.** | Starts from what the visitor has and names the one thing Krusgraph does first (finding and proving the links). It is true on the first click of the demo, and it leads into the map right below. | Does not name Fabric. The eyebrow and the supporting line do. |

**Chosen: "Your data already has connections. Krusgraph finds them."** (`claims.HEADLINE`). The demo proves it at once,
it makes no speed or compliance claim, and it does not lean on a term the visitor must already know.

Supporting line (`claims.SUPPORT`): *Discover how your tables connect, catch data issues before anyone sees them, and
build trusted Power BI models, APIs and AI-ready data products in Microsoft Fabric.*

Primary CTA: **Try the free demo** (no account; the guided demo on synthetic data). Secondary: **Connect Microsoft
Fabric** (/start; the same label site-wide, `pages.CONNECT_LABEL`). Under the buttons: *The demo runs in your browser on
synthetic data: no account, nothing uploaded.* The badge *One order, 2 lines, sample data: 2 000 → 1 000 why* stays.

## Intent tiles

Heading: *What would you like to do with your data?* There are four fixed choices and no text box (`pages.INTENTS`).

| Tile | Line | Opens |
| --- | --- | --- |
| Find broken relationships | References with no matching row, keys that are not unique, totals that double. | /check, all findings open |
| Understand how my tables connect | The map of keys and links, each with the rule behind it. | /check, the map |
| Build a Power BI model | A report preview and the model as a Power BI project, from the checked plan. | /check, the Power BI preview opened |
| Prepare my data for an AI agent | The ontology file and the evidence an agent can ground its answers on. | /check, the ontology and evidence tiles |

Each tile ends with *Sample data, no account*.

## See your data come together

*The engine's own run on a synthetic shop: 7 tables, 6 links. Each line carries its rule; a dashed line is a suggestion
you decide on.* The numbers come from the run. Under the map are the findings as buttons that mark the map, and a button
labelled *Open the map in the demo*.

## Before and after

Heading: *Why is the order total twice what finance says?*

- Before: *7 tables, and nothing written down about how they connect* · *1 link nobody is sure of: `orders.ship_to_id`* · *Order total in the report: 2 000*
- After: *6 links explained, each with the rule behind it* · *Checks passed: 6 of 6 keys unique, 6 of 6 relationships hold without orphans* · *Order total, once per order: 1 000*
- *What still needs a look, in plain words:* each finding as one line, with the engine's own title and rule on expand.
  For example, *We could not find what identifies a row in audit_log* expands to `audit_log has no key (K3)`. For an
  orphan check the plain line reads *Some orders rows reference customers we could not find*. The sample has no
  orphans, so that line does not appear on the page. No number on the page is typed by hand.

## What you can build

*From the plan you reviewed, in your own Fabric workspace. Each chip says how far that output has been proven today.*
The tiles and chips come from `claims.OUTPUTS`. After them:
*Krusgraph creates an item only when you ask, after a dry run, with your own Fabric permissions. Running or scheduling
the pipeline is a separate, opt-in step that needs DataPipeline.Execute.All: Krusgraph for Fabric offers it (Run once,
Schedule) when your admin grants it; the hosted connector does not request it, so in Claude the pipeline is run in
Fabric by you.* After that, the /check line (drafts only).

## Ways to use it

Heading: *Ways to use it: one engine, built in Fabric*. The n183 diagram is unchanged, followed by *Not sure which way
in? Compare the ways to use Krusgraph* → /choose.

## Three steps

*Explore* (point it at a lakehouse or drop exports; keys and links with rules) · *Review* (the checks count your rows;
you decide what a person must decide) · *Build* (choose outputs; a dry run first; nothing created until you say so).

## Security and proof

Six short cards, each with one link: Sign in with Microsoft Entra ID · Delegated permissions · Where it runs · No table
contents stored · Open source, MIT · Host it yourself.

## Final CTA

*See what your data can become.* *The demo and the connector are free and open source. A pilot around one number your
team cannot agree on is quoted after a short call.* Buttons: Try the free demo · Connect Microsoft Fabric · Talk about a
pilot.

## Navigation

Product · Examples · How it works · Pricing · Docs, then the button **Try free demo**.

## Words we do not use

No speed claims, no compliance claims, no customer logos, testimonials or endorsements, no "partner of" or "certified".
Microsoft, Anthropic and Lovable appear as plain text only. No material from Microsoft that is not public.
