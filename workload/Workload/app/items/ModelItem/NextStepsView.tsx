/**
 * W13: "Next with other Fabric workloads" (nextSteps.ts), under the result of a Create and on the Data product page.
 * One card per suggestion: the workload, the title, one line of why, what Krusgraph does for it (a status word, never
 * colour alone) and one button. Cards wrap to one column on a phone (ModelItem.scss, .kg-next).
 * WB4: below them, Recommended analyses (analysisPlan.ts): analysis_plan's ranking on this item, once the check passed.
 */
import React, { createContext, useContext, useEffect, useState } from "react";
import { Badge, Body1, Button, Caption1, Checkbox, Subtitle2 } from "@fluentui/react-components";
import { Open20Regular, Play20Regular } from "@fluentui/react-icons";
import { CopyText, FileActions, OutLink } from "./fileOffer";
import { LEARN, NextInput, NextStep, grainLine, nextSteps, proofLine, proofOf, staleCheckLine, toIpynb, workloadLine } from "./nextSteps";
import { FABRIC_PORTAL } from "./openInFabric";
import { AnalysisPlan, STAGE_WORD, StageNotebook } from "./advancedStages";

/** AA1: docs/ADVANCED-ANALYTICS.md on GitHub */
export const ADVANCED_DOCS = "https://github.com/Krusmaster/fabric-backend/blob/main/docs/ADVANCED-ANALYTICS.md";
import { TypeIcon } from "./itemIcons";
import { AnalysisAnswer, AnalysisCard, analysisCards, analysisKey, analysisSummary } from "./analysisPlan";
import type { OutputKind } from "./engineClient";
import type { CreatedItem } from "./ModelItemDefinition";
import { CreatedActions } from "./RunNowView";
import { outputTable } from "./runNow";
import { analysisName, ipynbCells, madeFor, pickedByDefault } from "./advancedAnalytics";

/** WB10 (#64): the Data Science starter's Dry run, then Create (POST /workload/v1/starter): the notebook in the item's
 * workspace, attached to the source lakehouse. Never run by Krusgraph. */
export interface StarterAnswer {
  would: "create" | "exists" | "created";
  name: string;
  words: string;
  confirm: string | null;
  created?: CreatedItem;
  /** ED3: the lakehouse the notebook is attached to (the data product's silver and gold), for Run now's preview */
  lakehouse_id?: string;
}
export interface StarterSource {
  run: (opts: { name: string; cells: string[]; dryRun: boolean; confirm?: string | null; output?: string }) => Promise<StarterAnswer>;
  onCreated?: (item: CreatedItem) => void;
}
export const StarterContext = createContext<StarterSource | undefined>(undefined);

function StarterCreate(props: { name: string; cells: string[]; output?: string }) {
  const source = useContext(StarterContext);
  const [state, setState] = useState<{ busy?: boolean; answer?: StarterAnswer; problem?: string }>({});
  if (!source) return null;
  const go = async (dryRun: boolean) => {
    setState((s) => ({ ...s, busy: true, problem: undefined }));
    try {
      const answer = await source.run({ name: props.name, cells: props.cells, dryRun, confirm: dryRun ? null : state.answer?.confirm,
        ...(props.output ? { output: props.output } : {}) });   // AA1: ds_model or ds_predictions
      if (answer.created) source.onCreated?.(answer.created);
      setState({ answer });
    } catch (e) {
      const err = e as { answer?: { error?: string; hint?: string }; message?: string };
      setState((s) => ({ ...s, busy: false, problem: [err.answer?.error ?? err.message ?? "The engine could not answer.", err.answer?.hint].filter(Boolean).join(" ") }));
    }
  };
  const a = state.answer;
  // ED3: once created the card shows the item with Open in Fabric and Run now and one line; nothing more is said here
  if (a?.would === "created") return null;
  return (
    <>
      {(

        <Button appearance="secondary" icon={<Play20Regular />} onClick={(): void => void go(true)} disabled={state.busy}
          aria-label={`Dry run: create the notebook ${props.name}`}>
          Dry run
        </Button>
      )}
      {a?.would === "create" && a.confirm && (
        <Button appearance="primary" onClick={(): void => void go(false)} disabled={state.busy}>Create {a.name}</Button>
      )}
      {(a || state.problem) && (
        <Caption1 role="status" className="kg-next-starter-said">{state.problem ?? a?.words}</Caption1>
      )}
    </>
  );
}

// ------------------------------------------------------------------ AA1: Advanced analytics, three stages ------------

const STAGE_OUTPUT: Record<StageNotebook["stage"], string> = { features: "ds_features", model: "ds_model", predictions: "ds_predictions" };

/** The notebook this item created for a stage (outputs.json, by its name), with an id: Open in Fabric and Run now. */
export function stageMade(s: StageNotebook, created: CreatedItem[] | undefined): CreatedItem | undefined {
  return [...(created ?? [])].reverse().find((c) => c.type === "Notebook" && c.id && c.workspace && c.name.toLowerCase() === s.name.toLowerCase());
}

/** One stage of one analysis: its word, what it writes, and Dry run, Create and Download; once created, Open in Fabric
 * and Run now (ED3's CreatedActions), with a preview of the table it writes. */
function StageRow(props: { n: number; s: StageNotebook; analysis: AnalysisPlan; made?: CreatedItem; waits: boolean; featureCells: string[] }) {
  const { s, made, analysis } = props;
  const word = STAGE_WORD[s.stage];
  const cells = s.stage === "features" ? props.featureCells : s.cells ?? [];
  const writes = s.stage === "features" ? { table: s.output, schema: "dbo" }
    : s.stage === "predictions" || analysis.analysis === "drivers" ? { table: analysis.gold_table.split(".")[1], schema: "gold" } : undefined;
  const say = s.stage === "features" ? `Writes ${s.output}, one row per order: the items summed per order first.`
    : props.waits ? "Waits for more rows."
      : s.stage === "model" && analysis.analysis !== "drivers"
        ? `Trains one baseline, logs it to the ML experiment and registers ${analysis.model_name} as an ML model.`
        : s.stage === "model" ? `No model: writes ${analysis.gold_table} directly.`
          : `Scores with the registered model (PREDICT) and writes ${s.output}, with the model version and run id on every row.`;
  return (
    <li className="kg-adv-stage" data-stage={s.stage}>
      <Body1><strong>{`${props.n}. ${word}`}</strong>{` · ${s.output}`}</Body1>
      <Caption1>{say}</Caption1>
      {made ? (
        <CreatedActions item={{ id: made.id, workspaceId: made.workspace, type: made.type, displayName: made.name }}
          preview={made.attached && writes ? { lakehouse: made.attached, ...writes } : undefined} />
      ) : !props.waits && cells.length > 0 && (
        <div className="kg-next-actions" role="group" aria-label={`${analysis.title}: ${word}`}>
          <StarterCreate name={s.name} cells={cells} output={STAGE_OUTPUT[s.stage]} />
          <FileActions file={{ filename: `${s.name}.ipynb`, mime: "application/x-ipynb+json", text: toIpynb(cells) }}
            label="Download (.ipynb)" copy={false} appearance="secondary" ariaLabel={`Download (.ipynb): ${s.name}`} />
        </div>
      )}
    </li>
  );
}

/** AA1: each analysis the rules recommend on the proven grain, in three stages: Feature table, Model, Predictions in gold.
 * Krusgraph runs none of them unless you press Run now, and reads no metric: the experiment's metrics are your own run's. */
export function ThreeStages(props: { plan: NonNullable<NextStep["advanced"]>; featureCells: string[]; created?: CreatedItem[] }) {
  const { plan } = props;
  const tooFew = plan.analyses.find((a) => a.too_few)?.too_few;
  const ws = (props.created ?? []).find((c) => c.workspace)?.workspace;
  return (
    <section className="kg-adv" aria-labelledby="kg-adv-title">
      <Subtitle2 as="h3" id="kg-adv-title">From the feature table to predictions in gold</Subtitle2>
      <Caption1>
        Each analysis in three stages, written by rules from the proven keys and links; no AI. Stage 2 logs one baseline model
        to the ML experiment {plan.experiment} and registers it; stage 3 scores with it into gold, where the next semantic
        model dry run adds the table. Nothing leaves Fabric.
      </Caption1>
      {tooFew && <Body1 role="status" data-say="thinker">{tooFew}</Body1>}
      <ol className="kg-adv-list">
        {plan.analyses.map((a) => (
          <li key={a.analysis} className="kg-adv-analysis" data-stages={a.analysis}>
            <Subtitle2 as="h4">{a.title}</Subtitle2>
            <Body1>{a.why}</Body1>
            <ol className="kg-adv-stages" aria-label={`${a.title}: the stages`}>
              {a.stages.map((s, i) => (
                <StageRow key={s.stage} n={i + 1} s={s} analysis={a} made={stageMade(s, props.created)} featureCells={props.featureCells}
                  waits={!!a.too_few && s.stage !== "features"} />
              ))}
            </ol>
            {a.analysis === "drivers" && <Caption1>Descriptive: no model, so there is nothing to score in a third stage.</Caption1>}
          </li>
        ))}
      </ol>
      <Caption1>
        {`Metrics and parameters are in the ML experiment ${plan.experiment}, from your own run; Krusgraph does not read them `
          + "(Fabric's REST API for experiments has no runs or metrics). "}
        {ws
          ? <OutLink url={`${FABRIC_PORTAL}/groups/${ws}`} className="kg-next-guide"><Open20Regular aria-hidden /> Open the experiment (in the workspace)</OutLink>
          : <OutLink url={LEARN.experiment} className="kg-next-guide"><Open20Regular aria-hidden /> About ML experiments</OutLink>}
        {" · "}
        <OutLink url={ADVANCED_DOCS} className="kg-next-guide">How the three stages work</OutLink>
      </Caption1>
    </section>
  );
}

// ------------------------------------------------------------------ WB4: Recommended analyses ------------------------

/** WB4: the engine's analysis_plan on this item (POST /workload/v1/analysis). Read-only; set by the editor. */
export interface AnalysisSource {
  run: () => Promise<AnalysisAnswer>;
}
export const AnalysisContext = createContext<AnalysisSource | undefined>(undefined);

/** One answer per source, schema and check, kept while the tab is open: the result view and the Data product page show
 * the same ranking without counting the rows again. */
const analysisAnswers = new Map<string, AnalysisAnswer>();
export function forgetAnalyses(): void {
  analysisAnswers.clear();
}

const READINESS_COLOR: Record<AnalysisCard["readiness"], "success" | "warning" | "subtle"> = {
  ready: "success", partial: "warning", missing: "subtle",
};

/** ED3: Dry run and Create for the ticked analyses (the top one ticked by default): each a notebook in this item's
 * workspace, attached to the data product's lakehouse, through the same starter route as the feature table. */
function AnalysisCreate(props: {
  cards: AnalysisCard[]; picked: string[]; where: { displayName: string; schema: string }; created?: CreatedItem[];
  state: Record<string, { busy?: boolean; answer?: StarterAnswer; problem?: string }>;
  setState: React.Dispatch<React.SetStateAction<Record<string, { busy?: boolean; answer?: StarterAnswer; problem?: string }>>>;
}) {
  const starter = useContext(StarterContext);
  if (!starter) return null;
  const chosen = props.cards.filter((c) => props.picked.includes(c.id) && c.action.kind === "notebook" && !madeFor(c, props.created, props.where));
  const dry = chosen.every((c) => props.state[c.id]?.answer?.would === "create" && props.state[c.id]?.answer?.confirm);
  const busy = chosen.some((c) => props.state[c.id]?.busy);
  const go = async (dryRun: boolean) => {
    for (const c of chosen) {
      if (c.action.kind !== "notebook") continue;
      props.setState((s) => ({ ...s, [c.id]: { ...s[c.id], busy: true, problem: undefined } }));
      try {
        const answer = await starter.run({ name: analysisName(c, props.where), cells: ipynbCells(c.action.content, c.action.code), dryRun,
          confirm: dryRun ? null : props.state[c.id]?.answer?.confirm, output: `analysis_${c.id}` });
        if (answer.created) starter.onCreated?.(answer.created);
        props.setState((s) => ({ ...s, [c.id]: { answer } }));
      } catch (e) {
        const err = e as { answer?: { error?: string; hint?: string }; message?: string };
        props.setState((s) => ({ ...s, [c.id]: { problem: [err.answer?.error ?? err.message ?? "The engine could not answer.", err.answer?.hint].filter(Boolean).join(" ") } }));
      }
    }
  };
  if (!chosen.length) return <Caption1>Tick an analysis above to create its notebook here.</Caption1>;
  return (
    <div className="kg-next-actions" role="group" aria-label="Create the ticked analyses">
      <Button appearance={dry ? "secondary" : "primary"} icon={<Play20Regular />} disabled={busy} onClick={(): void => void go(true)}>
        {`Dry run: ${chosen.length === 1 ? "1 notebook" : `${chosen.length} notebooks`}`}
      </Button>
      {dry && (
        <Button appearance="primary" disabled={busy} onClick={(): void => void go(false)}>
          {`Create ${chosen.length === 1 ? analysisName(chosen[0], props.where) : `${chosen.length} notebooks`}`}
        </Button>
      )}
    </div>
  );
}

function AnalysisCardView(props: {
  card: AnalysisCard; name?: string; created?: CreatedItem; ticked?: boolean; onTick?: (on: boolean) => void;
  said?: { busy?: boolean; answer?: StarterAnswer; problem?: string };
}) {
  const { card, created } = props;
  const a = card.action;
  return (
    <li className="kg-analysis-card" data-analysis={card.id} data-readiness={card.readiness}>
      <div className="kg-next-head">
        <Caption1 className="kg-analysis-rank">{`Rank ${card.rank}`}</Caption1>
        {/* the word is the readiness; the colour only repeats it */}
        <Badge appearance="tint" color={READINESS_COLOR[card.readiness]}>{card.word}</Badge>
      </div>
      <Subtitle2 as="h4">{card.title}</Subtitle2>
      <Body1>{card.line}</Body1>
      <Caption1>{card.missing}</Caption1>
      {a.kind === "notebook" && !created && props.ticked !== undefined && (
        <Checkbox className="kg-analysis-pick" checked={props.ticked} onChange={(_, d) => props.onTick?.(!!d.checked)}
          label={`Create the notebook ${props.name ?? card.title} in this workspace`} />
      )}
      {!created && (props.said?.problem || props.said?.answer) && (
        <Caption1 role="status" className="kg-next-starter-said">{props.said.problem ?? props.said.answer?.words}</Caption1>
      )}
      {a.kind === "notebook" && created && (
        <>
          <Caption1>{`The notebook ${created.name} is in this item's workspace. It writes ${a.output} when it runs.`}</Caption1>
          <CreatedActions item={{ id: created.id, workspaceId: created.workspace, type: created.type, displayName: created.name }}
            preview={created.attached && /^[A-Za-z_][A-Za-z0-9_]*$/.test(a.output) ? { lakehouse: created.attached, table: a.output, schema: "dbo" } : undefined} />
        </>
      )}
      <div className="kg-next-actions" role="group" aria-label={`${card.title}: ${card.word}`}>
        {a.kind === "notebook" ? (
          <>
            <FileActions file={{ filename: a.filename, mime: a.mime, text: a.content }} label={a.label} copy={false}
              appearance="secondary" ariaLabel={`${a.label}: ${card.title}`} />
            <CopyText text={a.code} label="Copy the code" appearance="secondary" />
          </>
        ) : (
          <CopyText text={a.text} label={a.label} appearance="secondary" />
        )}
      </div>
      {a.kind === "notebook" && (
        <>
          {!created && <Caption1>{`Writes ${a.output} when it runs. Krusgraph trains no model.`}</Caption1>}
          <details className="kg-next-code">
            <summary><Caption1>Show the code</Caption1></summary>
            <pre>{a.code}</pre>
          </details>
        </>
      )}
      {a.kind === "ask" && <Caption1 className="kg-next-ask">{a.text}</Caption1>}
    </li>
  );
}

/** WB4: the SAP order-to-cash analyses analysis_plan ranks on this item, after the check has passed. Ranked; each with a
 * readiness word, one line of why, what is missing and one action. Not shown without the editor's AnalysisContext. */
export function RecommendedAnalyses(props: { review: NextInput["review"]; source: NextInput["source"]; created?: CreatedItem[] }) {
  const source = useContext(AnalysisContext);
  const starter = useContext(StarterContext);
  const [picked, setPicked] = useState<string[] | undefined>();
  const [made, setMade] = useState<Record<string, { busy?: boolean; answer?: StarterAnswer; problem?: string }>>({});
  const key = analysisKey(props.source, props.review);
  const [state, setState] = useState<{ key?: string; busy?: boolean; answer?: AnalysisAnswer; problem?: string }>(
    () => (analysisAnswers.has(key) ? { key, answer: analysisAnswers.get(key) } : {}));
  const load = async () => {
    if (!source) return;
    setState({ key, busy: true });
    try {
      const answer = await source.run();
      if (!answer.waiting) analysisAnswers.set(key, answer);
      setState({ key, answer });
    } catch (e) {
      const err = e as { answer?: { error?: string; hint?: string }; message?: string };
      setState({ key, problem: [err.answer?.error ?? err.message ?? "The engine could not answer.", err.answer?.hint].filter(Boolean).join(" ") });
    }
  };
  useEffect(() => {
    if (!source) return;
    if (analysisAnswers.has(key)) {
      if (state.key !== key) setState({ key, answer: analysisAnswers.get(key) });
      return;
    }
    if (state.key !== key) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, key]);
  if (!source) return null;
  const where = { displayName: props.source?.displayName ?? "the source", schema: props.source?.schema ?? "" };
  const cards = analysisCards(state.answer, where);
  const ready = cards.filter((c) => c.readiness !== "missing");
  const notYet = cards.filter((c) => c.readiness === "missing");
  const land = state.answer?.land_next?.[0];
  return (
    <section className="kg-analysis" aria-labelledby="kg-analysis-title" aria-busy={state.busy ? true : undefined}>
      <Subtitle2 as="h3" id="kg-analysis-title">Recommended analyses</Subtitle2>
      <Caption1>
        SAP order-to-cash analyses, ranked by fixed rules over the proven model and row counts (analysis_plan); no AI. Counts
        only: no row value leaves the lakehouse. Krusgraph runs a notebook only when you choose Run now.
      </Caption1>
      {state.busy && <Body1 role="status">Ranking the analyses: counting rows, read-only…</Body1>}
      {state.problem && (
        <div role="alert" className="kg-analysis-problem">
          <Body1>{state.problem}</Body1>
          <Button appearance="secondary" onClick={(): void => void load()}>Try the ranking again</Button>
        </div>
      )}
      {state.answer?.waiting && <Body1>{state.answer.waiting}</Body1>}
      {state.answer?.applies === false && <Body1>{state.answer.words}</Body1>}
      {cards.length > 0 && (
        <>
          <Body1 role="status">{analysisSummary(cards)}</Body1>
          {ready.length > 0 && (
            <ol className="kg-next-list kg-analysis-list" aria-label="Ready and partly ready analyses, ranked">
              {ready.map((c) => (
                <AnalysisCardView key={c.id} card={c} name={analysisName(c, where)} created={madeFor(c, props.created, where)}
                  ticked={starter ? (picked ?? pickedByDefault(cards)).includes(c.id) : undefined}
                  onTick={(on) => setPicked((p) => { const now = p ?? pickedByDefault(cards); return on ? [...new Set([...now, c.id])] : now.filter((x) => x !== c.id); })}
                  said={made[c.id]} />
              ))}
            </ol>
          )}
          {starter && ready.some((c) => c.action.kind === "notebook") && (
            <AnalysisCreate cards={ready} picked={picked ?? pickedByDefault(cards)} where={where} created={props.created}
              state={made} setState={setMade} />
          )}
          {notYet.length > 0 && (
            <details className="kg-analysis-later" open={!ready.length}>
              <summary><Body1>{`Not ready yet (${notYet.length}): what data would make them ready`}</Body1></summary>
              {land && <Caption1>{`Landing ${land.land} would unlock ${land.unlocks.join(", ")}.`}</Caption1>}
              <ol className="kg-next-list kg-analysis-list" start={ready.length + 1} aria-label="Analyses not ready yet, ranked">
                {notYet.map((c) => <AnalysisCardView key={c.id} card={c} />)}
              </ol>
            </details>
          )}
        </>
      )}
    </section>
  );
}

const STATUS_COLOR: Record<NextStep["status"], "brand" | "informative" | "success" | "subtle"> = {
  builds: "brand", starter: "success", "in Claude": "informative", "guide only": "subtle",
};
const STATUS_WORD: Record<NextStep["status"], string> = {
  builds: "Krusgraph builds it", starter: "Starter to download", "in Claude": "Krusgraph in Claude", "guide only": "Guide only",
};

function StepCard(props: { step: NextStep; onBuild: (outputs: OutputKind[]) => void; made?: CreatedItem }) {
  const { step, made } = props;
  const how = step.how;
  return (
    <li className="kg-next-card" data-step={step.id}>
      <div className="kg-next-head">
        {/* WB11: the icons of the item types this step makes, at the card's top left, beside their names in text */}
        <span className="krusgraph-item-title kg-next-workload">
          {step.items.map((t) => <TypeIcon key={t} type={t} beside={workloadLine(step)} />)}
          <Caption1>{workloadLine(step)}</Caption1>
        </span>
        <Badge appearance="tint" color={STATUS_COLOR[step.status]}>{STATUS_WORD[step.status]}</Badge>
      </div>
      <Subtitle2 as="h3">{step.title}</Subtitle2>
      <Body1>{step.why}</Body1>
      {step.note && <Caption1>{step.note}</Caption1>}
      {/* ED3: a notebook this item created: Open in Fabric first (a new tab), Run now beside it */}
      {how.kind === "starter" && made && (
        <CreatedActions item={{ id: made.id, workspaceId: made.workspace, type: made.type, displayName: made.name }}
          preview={made.attached && outputTable(how.code) ? { lakehouse: made.attached, table: outputTable(how.code)!, schema: "dbo" } : undefined} />
      )}
      <div className="kg-next-actions">
        {how.kind === "build" && (
          <Button appearance="secondary" icon={<Play20Regular />} onClick={() => props.onBuild(how.outputs)}
            aria-label={`${how.label}: ${step.title}`}>
            {how.label}
          </Button>
        )}
        {how.kind === "starter" && (
          <>
            {!made && <StarterCreate name={how.name} cells={how.cells} />}
            <FileActions file={{ filename: how.filename, mime: how.mime, text: how.content }} label={how.label} copy={false}
              appearance="secondary" ariaLabel={`${how.label}: ${how.filename}`} />
            <CopyText text={how.code} label="Copy the code" appearance="secondary" />
          </>
        )}
        {how.kind === "ask" && (
          <CopyText text={how.text} label={how.label} appearance="secondary" />
        )}
        {how.kind === "guide" && (
          <OutLink url={how.url} className="kg-next-guide"><Open20Regular aria-hidden /> {how.label}</OutLink>
        )}
      </div>
      {how.kind === "starter" && (
        <details className="kg-next-code">
          <summary><Caption1>Show the code</Caption1></summary>
          <pre>{how.code}</pre>
        </details>
      )}
      {how.kind === "ask" && <Caption1 className="kg-next-ask">{how.text}</Caption1>}
    </li>
  );
}

/** W13: what the check proved, as tiles a person can read at a glance: rows counted, keys unique, links holding,
 * orphans, duplicate keys; and the doubled total the proven grain prevents (Onto's sentence). */
export function ProofStrip(props: { review: NextInput["review"] }) {
  const p = proofOf(props.review);
  if (!p.keysChecked && !p.linksChecked) return null;
  const tiles: [string, string][] = [
    [p.rows.toLocaleString("en-US"), "rows counted"],
    [`${p.keysPassed} of ${p.keysChecked}`, "keys unique"],
    [`${p.linksPassed} of ${p.linksChecked}`, "links holding"],
    [p.orphans.toLocaleString("en-US"), p.orphans === 1 ? "orphan" : "orphans"],
    [p.duplicates.toLocaleString("en-US"), p.duplicates === 1 ? "duplicate key" : "duplicate keys"],
  ];
  const grain = grainLine(p.grains[0]);
  return (
    <section aria-label="What the check proved">
      <ul className="kg-proof">
        {tiles.map(([n, what]) => (
          <li key={what}><strong>{n}</strong><Caption1>{what}</Caption1></li>
        ))}
      </ul>
      {grain && <Body1 data-say="onto"><strong>Onto:</strong> {grain}</Body1>}
    </section>
  );
}

export function NextStepsPanel(props: NextInput & { onBuild: (outputs: OutputKind[]) => void; onAnalytics?: () => void; now?: Date }) {
  const { proof, steps, waiting } = nextSteps(props);
  const proven = proofLine(proof);
  const grain = grainLine(proof.grains[0]);
  // ED3: the notebook this item's starter made (the newest), for Open in Fabric and Run now on its card
  const made = ([...(props.created ?? [])] as Partial<CreatedItem>[]).reverse()
    .find((c) => c.output === "ds_features" && c.type === "Notebook" && c.id && c.workspace) as CreatedItem | undefined;
  return (
    <section className="kg-next" aria-labelledby="kg-next-title">
      <Subtitle2 as="h2" id="kg-next-title">Next, with other Fabric workloads</Subtitle2>
      {waiting ? (
        <Body1>{waiting}</Body1>
      ) : (
        <>
          <Body1 data-say="thinker"><strong>Thinker:</strong> {proven}</Body1>
          {props.now && staleCheckLine(proof.checkedAt, props.now) && <Caption1 data-ed3="stale-check">{staleCheckLine(proof.checkedAt, props.now)}</Caption1>}
          {grain && <Body1 data-say="onto"><strong>Onto:</strong> {grain}</Body1>}
          <Caption1>Suggestions by rules from what was proven; no AI. A dry run comes before anything is created.</Caption1>
          <ul className="kg-next-list">
            {steps.map((s) => <StepCard key={s.id} step={s} onBuild={props.onBuild} made={s.id === "ds-features" ? made : undefined} />)}
          </ul>
          {/* ED3: Advanced analytics is one section on the Data product step; here, the way there */}
          {props.onAnalytics ? (
            <section className="kg-analysis" aria-labelledby="kg-analysis-link-title">
              <Subtitle2 as="h3" id="kg-analysis-link-title">Advanced analytics</Subtitle2>
              <Caption1>Forecasts, segments and the order-to-cash analyses the rules recommend for this data product, each with Dry run, Create, Open in Fabric and Run now.</Caption1>
              <div className="kg-next-actions">
                <Button appearance="secondary" onClick={props.onAnalytics}>Go to Advanced analytics on the Data product step</Button>
              </div>
            </section>
          ) : (
            <RecommendedAnalyses review={props.review} source={props.source} created={props.created as CreatedItem[]} />
          )}
        </>
      )}
    </section>
  );
}

/** ED3: "Advanced analytics", one section on the Data product step (Gustav: "vart är advanced analytics-spåret?"). */
export function AdvancedAnalytics(props: { review: NextInput["review"]; source: NextInput["source"]; created?: CreatedItem[] }) {
  if (!proofOf(props.review).keysPassed) return null;
  // AA1: the Data Science card's grain, in three stages (feature table, model, predictions in gold)
  const stages = nextSteps({ review: props.review, created: props.created ?? [], source: props.source }).steps.find((s) => s.id === "ds-features");
  return (
    <section className="kg-advanced" id="kg-advanced-analytics" aria-labelledby="kg-advanced-title">
      <Subtitle2 as="h2" id="kg-advanced-title">Advanced analytics</Subtitle2>
      <Caption1>
        Notebooks Krusgraph writes by rules on this data product's proven keys and links, created in this item's workspace
        on the data product's lakehouse. No AI, and Krusgraph trains no model: the notebooks are yours to run.
      </Caption1>
      {stages?.advanced && stages.how.kind === "starter" && (
        <ThreeStages plan={stages.advanced} featureCells={stages.how.cells} created={props.created} />
      )}
      <RecommendedAnalyses review={props.review} source={props.source} created={props.created} />
    </section>
  );
}
