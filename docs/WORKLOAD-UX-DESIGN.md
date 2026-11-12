# The Model item in Fabric: a shorter flow (design, D1)

Round D1, 12 November 2026. A design only: no product code changes here. It covers the Krusgraph Model item's editor
(`workload/Workload/app/items/ModelItem/`). The clickable mockups are in `docs/design/workload-flow/` (start with
`index.html`). n225 is changing the editor now (the Data product page, Open in Fabric for the ontology, the App card's
words, the editor on a phone). Nothing here changes that work. Section 10 says which changes wait until n225 releases.

## 1. Why

The founder tested the item on a phone in Fabric on 12 November 2026 and said: *"we need to work on the UI in the
workload; there are possibilities for a better flow."*

**What worked, and stays:**
- the mascots (Onto, Thinker and Builder), one sentence each
- the map
- Check against the rows
- Create 8 of 8
- the data flow diagram

**What the screenshots showed:**

| Seen | Where it comes from now |
| --- | --- |
| Very long pages that scroll | Each view renders everything it has: `ReviewView`, `OutputsView`, `PreviewView` and `ResultView` in `ModelItemViews.tsx` |
| The dry run is a wall of text | `PreviewView` renders each `OutputCard` in full: `cardFacts`, `AppPanel` (key figures, charts, filters, colour), `JobsPanel`, `AgentPanel`, connector lists and portal steps, all open |
| A toolbar of icons without labels | `homeActions()` in `ModelItemEditor.tsx` passes labels. At narrow widths the ribbon has no overflow, so actions get cut off or squeezed. The kit's `.ribbon-action-button` (`components/ItemEditor/ItemEditor.scss`) sets 12 px text |
| At 375 to 412 px the editor renders at desktop width and the text is tiny | `index.html` has no viewport meta, and the editor's CSS has almost no narrow-width rules. Inside Fabric, the iframe's width comes from Fabric's own page (see section 7) |
| The data product page mixes owner, health, items, update, retire and leftovers on one page | `DataProductView.tsx` has five sections stacked under one heading |
| Next steps are a numbered text list | `FinishView` renders `createWords.nextSteps()` as an `<ol>` of sentences, with no button for each step |

**The founder's standing goals, which this design follows:**
- as simple as possible
- a suggestion you can click comes first
- everything can be done on a phone
- a mascot explains a complex thing in one true sentence
- Krusgraph guides the process (suggest, check, build, update, version, retire) and shows where you are

## 2. What Microsoft's guidelines require (read 12 November 2026)

- **Fabric Extensibility toolkit validation guidelines and requirements for items**, Microsoft Learn,
  `learn.microsoft.com/en-us/fabric/extensibility-toolkit/publishing-requirements-item` (ms.date 24 February 2026,
  updated 4 March 2026):
  - **3.1:** one ribbon, sticky above the canvas, holding all actions; *"The ribbon tabs can't be used to switch the
    view."*
  - **3.2:** ribbon actions use the Fabric button *"in subtle state"*; other components are at most 32 px high.
  - **3.3:** a tab called Home comes first.
  - **3.4:** Save or AutoSave (optional); the save *"button is icon only"*.
  - **3.10:** no gap between adjacent buttons, 4 px either side of a divider, 4 px between different components.
  - **4.3:** empty states give *"helpful messaging and clear actions"*.
  - **4.6:** tabs in the canvas follow the Fabric style.
  - **4.7:** switches follow the Fabric style.
  - **6.x:** dialogs follow the Fabric style.
- **Fabric Extensibility toolkit validation guidelines and requirements for workloads**, same site,
  `.../publishing-requirements-workload` (ms.date 24 February 2026, updated 11 March 2026):
  - **2.9 Accessibility:** *"The workload and all Item types … need to comply with the Fabric UX guidelines"*.
  - **Section 3** points to the Fabric UX System (`aka.ms/fabricux`) and says *"Fabric users expect a fast loading
    UX"*.
- **Fabric Item Overview**, same site, `.../concept-item-overview` (ms.date 15 December 2025): the editor is
  built from `ItemEditor`, `ItemEditorEmptyView`, `ItemEditorDefaultView` and `ItemEditorDetailView`, with the
  Home toolbar for standard actions such as save and settings.

The Fabric UX System pages at `aka.ms/fabricux` were not opened in this round, so this design cites none of their
details. Read them before building (section 12).

**What this means for the design:**
- **Where-you-are stays in the canvas.** The step indicator lives in the canvas, not in the ribbon, because ribbon
  tabs must not switch the view (3.1).
- **The tabs on the Data product page are canvas tabs** (4.6), not ribbon tabs.
- **Save stays icon only** (3.4). Every other ribbon action keeps a visible label and uses `appearance="subtle"`. Today
  the kit renders `secondary` by default (`RibbonActionButton.tsx`), which already breaks 3.2.
- **Nothing here replaces the kit's `ItemEditor`.** The flow is the content of the canvas.

## 3. The flow: six steps, one primary action each

```
1 Source  ->  2 Map  ->  3 Check  ->  4 Dry run  ->  5 Create  ->  6 Data product
```

**The step indicator** sits at the top of the canvas.
- **1280 px:** a horizontal `<ol>` of six labelled steps. Each step is ✓ done, ● now, or ○ ahead. Done steps link back.
- **375 px:** one line, *"Step 3 of 6 · Check · Next: Dry run"*, over a progress bar.
- The current step has `aria-current="step"`.
- Steps ahead can't be clicked until they can run. A reopened item lands on the furthest step it reached.

**The primary action** sits in a bar at the foot of the canvas.
- That bar sticks to the bottom and holds one primary button, a Back button where there is a step to go back to,
  and one line saying what will happen.
- On a phone the primary button is full width and 44 px high.
- No other button on the screen is primary. A card offers a secondary action, or says "Or choose X below".

**Progressive disclosure.** A screen shows:
- a summary
- the one suggestion
- the primary action

Details sit behind "Show …" (Fluent `Accordion`, collapsed by default). The full text the editor shows today is not
removed. It moves behind Show.

**Defaults let a first user click straight through.** With the shop sample, a first user goes from an empty item to
eight items in Fabric with seven clicks:
1. Find keys and links
2. Keep it without a key
3. Next
4. Check against the rows
5. Accept the 13 that passed
6. Create 8 items
7. Run the pipeline once

Each default is the suggestion the engine already makes, shown as already chosen and easy to change.

**Mapping today's views to the steps:**

| Today's view (`ModelView`) | Becomes |
| --- | --- |
| `empty` (`EmptyView`) | 1 Source |
| `review` (`ReviewView`) | 2 Map (the map and Thinker's questions) and 3 Check (the check, accepting what passed, the list behind Show) |
| `outputs` (`OutputsView`) + `preview` (`PreviewView`) | 4 Dry run. "Choose what to build" becomes the **Change** drawer on the dry run, and the dry run starts with the suggested set |
| `result` (`ResultView`, `FinishView`) | 5 Create (progress, then "Next, one at a time") |
| `product` (`DataProductPage`) | 6 Data product, in tabs |

`ModelView` keeps its values, so saved items reopen as before. `outputs` becomes an internal state of step 4 (the
drawer open). No saved definition changes.

## 4. Each screen

The sample on every screen is the synthetic shop schema (`fabric_backend/seed.py`):
- **7 tables:** customers, categories, products, addresses, orders, order_items, audit_log
- **6 keys:** order_items keyed on `order_id + line_no`
- **7 links:** 6 by R1, and `orders.ship_to_id → addresses` by R5

`docs/LIVE-TEST.md` rows 4 and 6 give the same counts.

### 4.1 Source (`01-source.html`)

- **Onto:** *"I read the table and column names of one source and suggest keys and links; nothing is created until
  you choose Create."*
- **Suggested, already chosen:**
  - **Source:** the lakehouse this item used last, or else the only lakehouse in the item's workspace.
  - **Schema:** the one with the most tables.
- **Secondary:**
  - "Choose another source" (the OneLake catalog, as today, through `callDatahubOpen`)
  - the schema dropdown
  - for a read-only source, the target lakehouse (`targetLine`), shown only for read-only sources
- **Behind Show:** what Krusgraph reads and the permissions it needs (today's `PermissionsNote`).
- **Primary:** **Find keys and links.**
- **375 px:** the suggested source fills the width, the schema dropdown sits under it, and the primary is in the foot
  bar.
- **1280 px:** the schema and "another source" sit side by side under the suggestion.
- **Needs:** listing the lakehouses in the item's workspace. Until that exists, the suggestion is the last-used source
  (in `source.json`), or the empty state with one primary, "Choose a source".

### 4.2 Map (`02-map.html`)

- **Onto:** the totals in one sentence: *"7 tables, 6 keys and 7 links; each comes with the rule that found it."*
- **Three stat tiles:** 7 tables, 6 keys, 7 links.
- **Thinker's questions,** one card each. The suggested answer is the first button ("Keep it without a key").
  Answered questions fold away.
- **Map | List (13):** a segmented control.
  - The map is today's `PlanMap`, with a second layout for narrow widths: two columns, 14 px labels.
  - Tapping a table or a line shows its rule (today's `RulePill` tooltip becomes a `Popover`, because a tooltip can't
    be tapped on a phone).
- **Primary:** **Next: check against the rows.**
- **Hidden:** Accept and Reject for each row are not on this screen. They move to Check, where the evidence is.

### 4.3 Check (`03-check.html`, two states)

- **Thinker (before):** *"I count rows to see whether each key is unique and each link finds its row; I never show a
  value, and nothing in Fabric changes."*
- **Primary (before):** **Check against the rows.**
- **After the check:**
  - **Thinker:** *"Everything I checked holds: 6 of 6 keys are unique and 7 of 7 links find their row."*
  - **Tiles:** 13 passed, 0 failed, 0 not checked.
  - **Primary:** **Accept the 13 that passed**, which also starts the dry run.
- **Behind "Show the 13, one by one":** today's `ReviewRow` list, with Accept and Reject on each row and the "it holds
  in the rows" warning (`holdsText`, `rejectedRowText`).
- **When something failed:**
  - Thinker names how many.
  - The primary becomes **Review the 2 that failed**, which opens the list filtered to the failed items.
  - "Accept the 11 that passed" is secondary.
- **Without a check:** a secondary "Skip the check". The dry run then says what was not checked, as `dryRunCheckLine`
  does today.

### 4.4 Dry run (`04-dry-run.html`)

- **Builder:** *"Here is what Create would make; nothing exists in Fabric yet."*
- **One summary card (selected border):**
  - *"8 outputs · 1 data product 'shop'"*
  - *"The suggested set, in this item's workspace. App (Rayfin, preview) is left out."*
  - A **Change** button opens a drawer (Fluent `OverlayDrawer`, `position="end"`; full width at 375 px). The drawer
    holds:
    - today's `OutputsView` choices as a checkbox list
    - the data product's name
    - the suggested data products (`SuggestedProductsPanel`)
    - Build in, the names, the pipeline's run and schedule, and the agent's publishing, behind Show
  - **Dry run again** closes the drawer.
- **Data flow:** today's `FlowView`, open by default, collapsible. At 375 px it runs vertically.
- **One summary card per output:**
  - the item type's icon
  - the label
  - the item's name
  - a state badge (*Would be created*, *Would be updated*, *Create will ask*, *Refused*)
  - **one sentence** saying what the output is
  - **Show details**, which opens the full card as it is today
- **Today's text moves behind Show details:**
  - `cardFacts`
  - `JobsPanel`
  - `AgentPanel`
  - the App's key figures, charts, filters, colour and pages (`AppPanel`)
  - connector lists
  - portal steps
  - permissions
- **A card opens by itself** when it needs you: refused, *Create will ask*, or a permission problem. Its problem shows
  above Show details as a `MessageBar`.
- **"Left out by your review (n) · not checked (n)":** behind Show.
- **Primary:** **Create 8 items** (today's `createLabel`).
- **The default set changes.** Today only the API for GraphQL is ticked on a new item (`buildWords.ts`,
  `enabled: k.kind === "graphql"`). The suggested set becomes every output except the App (preview), with these
  safety defaults kept as today:
  - nothing runs or is scheduled unless ticked
  - the agent stays an unpublished draft

  This is the change that lets a first user click straight through. **The founder decides it** (section 11).

### 4.5 Create (`05-create.html`, two states)

- **While it runs:**
  - **Builder:** *"I build them in order, the semantic model before its report; each card keeps its own result."*
  - One progress card: *"5 of 8 created · Report next"* over a `ProgressBar`, then one row for each output (✓ Created,
    spinner Creating, ○ Waiting, ✕ Failed with Try again).
  - Capacity waits and "still running in Fabric" stay as today's `MessageBar`s on their row.
  - The foot bar says *"You can leave this page; Create carries on and the item shows where it got to."* (n197's
    reopening already does this.)
- **When done:**
  - **Onto:** *"8 of 8 are in Fabric. Two things are left for you, below."*
  - **"Next, one at a time"** replaces the numbered list:
    - The first next step is a card with its own button. The foot bar's primary is that step: **Run demo_lh_pipeline
      once**.
    - The second step is a card under it.
    - The rest are behind "Show the other 6", each with Open.
  - Every card's result is behind Show.
  - "Keep it up to date" moves to the Data product's Update tab.

### 4.6 Data product (`06-data-product.html`)

- **Onto:** *"This is the data product: 8 items built from one reviewed plan. From here you keep it up to date or
  retire it."*
- **A life strip under the heading** shows where the product is: Suggested ✓ · Checked ✓ · Built ✓ · **Keep up to
  date** · Versions (planned) · Retire.
  - Versions and Undo are designed in `docs/LIFECYCLE-DESIGN.md` and not built. The strip says "planned" until
    they are.
- **Canvas tabs** (Fluent `TabList`, not ribbon tabs):

| Tab | Holds (from today's `DataProductView.tsx`) |
| --- | --- |
| **Overview** (default) | Tiles: built, need you, health. **One "Suggested next" card**, the first that applies: choose an owner, fix a failed item, check health, check for updates. Plan and domains behind Show |
| **Items (8)** | One row per item: state word and mark, name, Open. "Items in the workspace that are not in this product" (leftovers, Adopt) behind Show |
| **Update** | Thinker's sentence, **Check for updates**, then one card per item that would change, each with its own dry run (today's `updates`) |
| **Retire** | Take out of the product, or delete from Fabric. A dry run comes first; deleting asks for the typed name (today's `RetirePanel`). Its buttons are never primary |

- **The foot bar's primary** is the Overview's suggested next action (here, **Make me the owner**). On the other tabs
  it is that tab's one action.

## 5. The ribbon

The ribbon has one tab, **Home**, first and sticky (Learn 3.1, 3.3).

| Action | Shown | When |
| --- | --- | --- |
| Save | icon only, tooltip "Save" (3.4) | always; disabled when nothing changed |
| Source | icon + label | always |
| Check | icon + label | from step 2 |
| Dry run | icon + label | from step 3 |
| Create | icon + label | from step 4 (and disabled while a Create runs) |
| Data product | icon + label | once anything was created or removed (today's rule, n198) |

- **Every button is `appearance="subtle"`, 32 px high, with no gap between adjacent buttons** (3.2, 3.10).
- **Back leaves the ribbon.** It is in the foot bar, next to the primary.
- **"Read the lakehouse again"** moves to a More menu on step 2.
- **At narrow widths, labels stay.** The ribbon uses Fluent `Overflow`, and actions that don't fit move into a
  **More** menu (`Menu` with `MenuItem`s that keep their labels). The current step's own action stays outside.
- The ribbon repeats the step actions so that a person who knows the flow can jump straight to a step. The foot bar is
  still the guided path.

## 6. What to cut or hide

- **Choose what to build as a page of its own:** it becomes the Change drawer.
- **The mascot on/off Switch in the review:** it moves to the item's settings (Learn 7.6), or behind More. Keep the
  plain-text fallback (`Mascots.plain`) for people who turn the mascots off.
- **The "About and notices" disclosure under the outputs:** it moves to the item's settings or the Data product's
  Overview behind Show.
- **The full output cards in the dry run and the result:** they go behind Show details (4.4).
- **The duplicated product summary** (`ProductView` in Choose, Preview and Result): it is shown once, in the dry run's
  summary card, and in full on the Data product page.
- **"Accept all" without a check:** it becomes the secondary "Accept all 13 without the check" behind Show, so the
  path that uses the evidence comes first.
- **The trial line:** it moves into a `MessageBar` above the step indicator, once, dismissible.
- **Nothing is deleted from the engine's answers.** Every word the editor shows today stays one Show away.

## 7. The phone: honest limits

- **The editor runs in an iframe that Fabric sizes.** A `<meta name="viewport">` in `index.html` matters when the
  editor opens on its own (the dev server and the browser tests). Inside Fabric, the iframe's width is whatever Fabric's
  own page gives it.
- **On the founder's phone that may be a desktop-width layout,** which the browser then scales down. The CSS can't fix
  that from inside the iframe. Two things we can do:
  1. **Lay out by the canvas's own width, not the device's.** Use CSS container queries on the canvas
     (`container-type: inline-size`, as the mockups do) rather than `@media`. The layout then follows the iframe at
     whatever width Fabric gives it. Add the viewport meta for standalone use.
  2. **Measure first.** One line in the editor's debug output, or a test page, reports `innerWidth`,
     `devicePixelRatio` and `visualViewport.scale` inside the iframe on the founder's phone. Then we know whether
     Fabric gives a narrow iframe (our layout fixes it) or a scaled desktop one. In the second case, the fix is larger
     type and fewer columns at every width, not a phone layout.
- **Type is never below 12 px for captions,** and body text is 14 to 15 px. Touch targets in the foot bar are 44 px; the
  ribbon stays at 32 px (Learn 3.2).
- **n225 claimed "the editor on a phone" today.** This section is input for that work, not a parallel change. Whatever
  n225 lands first stays, and this design adapts to it.

## 8. Fluent UI v9 components

The workload locks `@fluentui/react-components` 9.75.1 (`Workload/package-lock.json`). Everything below is in that
package. None is new to the dependency tree.

| Need | Component |
| --- | --- |
| Step indicator | No Fluent stepper exists: an `<ol>` with Fluent tokens, `aria-current="step"`, and `ProgressBar` on narrow widths |
| Primary action bar | `Button` (`appearance="primary"`, one per screen), `Button` for Back, `Caption1` for the hint |
| Mascot sentence | today's `MascotSays` (figure `aria-hidden`, sentence as text) |
| Summary cards | `Card`, `CardHeader` (icon via `ItemTitle`, `Badge` for the state) |
| Show details | `Accordion`, `AccordionItem`, `AccordionHeader`, `AccordionPanel` (collapsed) |
| Change drawer | `OverlayDrawer` (`position="end"`, `size="full"` under 640 px), `DrawerHeader`, `DrawerBody`, `Checkbox`, `Field`, `Input` |
| Map or List | `TabList` with `size="small"` and `appearance="subtle"`, or a `ToggleButton` pair |
| Rule on tap | `Popover` (keeps `Tooltip` for hover on desktop) |
| Stat tiles | `Card` with `Title2` and `Caption1`, or `CounterBadge` where a count sits on a label |
| Progress | `ProgressBar` (with `aria-valuetext`, "5 of 8 created"), `Spinner` size `tiny` on a row |
| Problems and waits | `MessageBar` (`intent` warning, error, info, success) |
| Data product tabs | `TabList` and `Tab` in the canvas (Learn 4.6) |
| Owner | `Persona` for the chosen owner. A people picker if the Fabric client offers one, else `Combobox` |
| Delete confirmation | `Dialog` with a typed name (today's rule) |
| Ribbon overflow | `Overflow`, `OverflowItem`, `useOverflowMenu`, `Menu`, `MenuItem`, `ToolbarButton` (`appearance="subtle"`) |
| Loading | `Skeleton` (already used by `Busy`) |

## 9. Accessibility

- **One `h1` per step** (the step's name). Sections have `h2`. The step indicator is a `nav` named "Where you are",
  with `aria-current="step"`.
- **Every state has a word and a mark,** never colour alone (as `DataProductView.tsx` does today): Passed ✓, Failed ✕,
  Not checked, Would be created.
- **Focus:**
  - When a step changes, focus moves to its `h1`.
  - When the check ends, focus moves to Thinker's result.
  - When the drawer opens, focus moves inside it and comes back to Change when it closes. Escape closes it.
- **Keyboard:** the canvas tabs and Map | List use the arrow keys (Fluent `TabList` does). Every action is a button in
  the tab order. The foot bar comes after the content in the DOM, so tab order follows reading order.
- **Live regions:**
  - progress ("5 of 8 created") in `role="status"`, read on change, not on every poll
  - errors in `MessageBar` with `role="alert"` only for a failure
- **Mascot images** are decorative (`alt=""`, `aria-hidden`). The sentence is real text. With the mascots off, the
  same sentences show as plain text.
- **The map** has a text alternative: the List tab holds the same 13 items. The SVG has a `title`.
- **Contrast:** Fluent tokens only, light and dark. The mockups' colours were chosen for 4.5:1 for text; the contrast was not measured in this round.
  `prefers-reduced-motion` stops spinners and the celebration poses.
- **Touch:** 44 px targets in the foot bar and drawer, 32 px in the ribbon (Learn 3.2). No hover-only information.
- **Testing:** the n198 pattern (render the states to fixtures, open them at 375 and 1280 px, light and dark, by
  keyboard) extends to each step.

## 10. Changes mapped to files, with estimates

A round is one session like n225's: claim, build, test (vitest and the browser renders at 375 and 1280 px, light and
dark), release.

| # | Change | Files | Estimate | Waits for |
| --- | --- | --- | --- | --- |
| A | **Dry run as summary cards.** One sentence per output, the rest behind Show details. The Change drawer replaces the Choose page. The suggested set is the default | `ModelItemViews.tsx` (`PreviewView`, `OutputCard`, `OutputsView` into a drawer), `ModelItemEditor.tsx` (views, `previewBuild` after Accept), `buildWords.ts` (`choicesFor` default), a new `outputSummary.ts` (one sentence per kind from the card, tested), tests `planCards`, `createButton`, `dryRunEqualsCreate` | 1½ rounds | founder's yes on the default set |
| B | **Step indicator and foot bar.** One primary per screen, labelled subtle ribbon with More | a new `FlowStepper.tsx` and `FootBar.tsx`, `ModelItemEditor.tsx` (`homeActions`, `wrap`), `components/ItemEditor/RibbonActionButton.tsx` (`subtle`; a `Krusgraph:` comment, since it is the kit's file), `Ribbon.tsx` (`Overflow`), `ModelItem.scss` (container queries) | 1 round | n225's release of Workload |
| C | **Data product in tabs,** a "Suggested next" card and the life strip | `DataProductView.tsx` (sections into tab panels), `productWords.ts` (`suggestedNext()`, pure and tested), `dataProductPage.test.ts` and the n198 fixtures | 1 round | n225 (who is changing this page now) |
| D | **Review split into Map and Check.** Accept the passed ones as the primary, the list behind Show, the narrow map layout, the rule in a Popover | `ModelItemViews.tsx` (`ReviewView`), `planMapView.tsx`, `cardMap.ts` (two layouts), `modelWords.ts` (sentences), `ModelItemDefinition.ts` (no change to the saved shape) | 1 round | B |
| E | **Create: progress card, and "Next, one at a time"** with buttons | `ModelItemViews.tsx` (`ResultView`, `FinishView`), `createWords.ts` (`nextSteps` returns `{text, action}`), `jobsWords.ts` (Run once from the card), tests `createWords`, `jobsWords` | 1 round | B |
| F | **Source: the suggested lakehouse** | `ModelItemViews.tsx` (`EmptyView`), `sourceWords.ts`, and, for listing a workspace's lakehouses, `fabric_backend/workload_api.py` (Workload area) | 1 round | a check of the Fabric call and its scope |
| G | **Phone: measure inside Fabric's iframe,** the viewport meta, the type floor | `index.html`, `ModelItem.scss`, one diagnostic line | ½ round | n225 (its phone work may already cover it) |

**Total:** about 7 rounds. A, B and C are independent of each other. D and E build on B.

## 11. What I would build first

1. **A, the dry run as summary cards** with the Change drawer and the suggested default set. It removes the wall of
   text, the page that was longest in the screenshots. It also removes one whole page (Choose what to build), and it is
   the change that lets a first user click straight through. Founder's decision needed: the default ticks every output
   but the App (preview). Nothing runs, is scheduled or is published unless ticked, as today.
2. **B, the step indicator, the foot bar with one primary action, and the labelled subtle ribbon with More.** This
   shows where you are on every screen and fixes the toolbar against Learn 3.2.
3. **C, the Data product page in four tabs with a "Suggested next" card.** This splits the mixed page and makes the
   next thing to do a button. It starts after n225 releases this page.

## 12. Not verified, and open questions

- **What width Fabric's iframe gets on a phone** (section 7). Measure it before designing further for 375 px.
- **The Fabric UX System pages** (`aka.ms/fabricux`) were not opened in this round. Read them for exact paddings, the
  canvas border and tooltip timing before B is built.
- **Listing the lakehouses of the item's workspace** for the suggested source (F): the call and the scope it needs are
  not checked yet.
- **Whether the mascot toggle may move to the item's settings** (Learn 7.6, optional) or should stay visible.
- **The mockups' card sentences are illustrative.** The real words come from the engine's dry run (`cardFacts`,
  `previewLine`). The counts (7 tables, 6 keys, 7 links, 8 outputs) are the shop sample's.

## The mockups

`docs/design/workload-flow/`. They are self-contained (inline CSS and a small inline script, mascot images from
`fabric_backend/static/mascots/` embedded as data URIs, no external scripts or fonts):

| File | Step | Click |
| --- | --- | --- |
| `index.html` | all six at 375 px, light and dark, side by side | each opens at desktop width |
| `01-source.html` | Source | Find keys and links |
| `02-map.html` | Map | Map / List (13); Next |
| `03-check.html` | Check | Check against the rows → the result → Accept the 13 that passed |
| `04-dry-run.html` | Dry run | Change (the drawer; Escape closes it); Show details; Create 8 items |
| `05-create.html` | Create | "Show the finished state" → Next, one at a time |
| `06-data-product.html` | Data product | Overview / Items / Update / Retire (arrow keys work) |

Each page has controls for width (375 px or desktop) and theme (light, dark, system). The page also takes them as
`?w=375&theme=dark`. The layout responds to the frame's width through container queries, so the 375 px view is the real
narrow layout, not a scaled picture. They were checked in Chromium at 375 and 1280 px, light and dark: no horizontal
scroll, no text under 12 px, no script errors.
