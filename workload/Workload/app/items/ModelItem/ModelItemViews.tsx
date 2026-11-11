/**
 * The five views of the Krusgraph Model editor: empty state, review, choose outputs, preview (dry run), result.
 * n174: every output the MCP tools build (KINDS in buildWords.ts), one dry-run card each, the data product, the data flow
 * (FlowView.tsx), and the result with Open in Fabric and the portal steps left per item.
 * Copy follows the site: plain words, numbers only from the engine's answers, no claims about speed or compliance.
 * n173: the review shows the map (the MCP Apps cards' drawing, cardMap.ts) or the list, each row's check state
 * (green passed, red failed with its orphans or duplicates, grey not checked), Onto, Thinker and Builder in their own
 * colours with the site's figures, Thinker's questions with their choices inline, and Accept all. Words: modelWords.ts.
 */
import { ReadOnlySource, SapOffer, isReadOnly, sapMark, sourceButton, sourceNotes, targetButton, targetLine } from "./sourceWords";
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Badge,
  Body1,
  Button,
  Caption1,
  Checkbox,
  Field,
  Input,
  Link,
  MessageBar,
  MessageBarBody,
  Radio,
  RadioGroup,
  Spinner,
  Subtitle2,
  Switch,
  Tab,
  TabList,
  Title3,
  Tooltip,
} from "@fluentui/react-components";
import { CheckmarkCircle20Filled, CheckmarkStarburst24Regular, ErrorCircle20Filled, Open24Regular, Warning20Filled } from "@fluentui/react-icons";
import { ItemEditorEmptyView } from "../../components/ItemEditor";
import { AppChoices, BuildCard, DataProduct, EngineError, JobsCard, ManyAnswer, SchemasAnswer } from "./engineClient";
import {
  AppApi, AppDesign, AppPackageRecord, AppPreflight, BUILT_APP_NOTE, BUILT_APP_UNKNOWN, CHART_TYPE_WORDS, EDIT_NOTE, EDIT_TITLE, GROUPS, PREVIEW_NOTE, apiLines, builtChoices,
  builtWithoutPackage, chartTypes, choiceLines, designLines, editHref, featureOff, isApp, movePage, optionsOf, packageHref,
  pagesInOrder, preflightWords, readAppRecord, setAccent, setChartType, tickWarning, ticked, toggle,
} from "./appWords";
import {
  CreatedItem,
  OutputChoice,
  OutputsDefinition,
  ProductDefinition,
  ReviewFile,
  ReviewItem,
  ReviewStatus,
  SourceDefinition,
  sortForReview,
} from "./ModelItemDefinition";
import {
  KINDS,
  OpenLink,
  cardFacts,
  cardProblem,
  cardTitle,
  choiceProblems,
  nameAction,
  needsChoice,
  refreshWords,
  openLinks,
  previewLine,
  resultLine,
  validName,
} from "./buildWords";
import { FlowView } from "./FlowView";
import { canRetry, progressLabel, toRetry } from "./createRun";
import { AgentChoices, AgentPanel, JobsPanel, PipelineChoices } from "./JobsViews";
import { agentOf, jobsOf, scheduleProblems } from "./jobsWords";
import { ICON_SIZE, NOTICES, itemIcon } from "./fabricIcons";
import {
  APP_STEPS_TITLE, CardState, FINISH_CSS, LastCreate, STATE_MARK, banner, cardState, itemTypeLabel, keepUpToDate, nextSteps,
  readLastCreate, running, stepsTitle,
} from "./createWords";
import { MapData, drawPlanMap, overlay } from "./cardMap";
import { MAP_CSS, MASCOT_COLOURS, MASCOT_CSS, MASCOT_GLAD, MASCOT_NAMES } from "./cardMap.generated";
import { MascotFigure } from "./mascotFigure";
import {
  CheckState,
  Choice,
  acceptAllTargets,
  checkLines,
  checkState,
  checkText,
  dryRunCheckLine,
  itemText,
  questions,
  ruleMeaning,
  sayings,
  summaryLines,
  totalsOf,
  holdsText,
  rejectedHoldingText,
  rejectedRowText,
} from "./modelWords";

export type MascotKind = "onto" | "thinker" | "builder";
import "./ModelItem.scss";

export function Busy({ label }: { label: string }) {
  return (
    <div className="krusgraph-view">
      <Spinner label={label} />
    </div>
  );
}

export function ErrorBar({ error }: { error?: EngineError }) {
  if (!error) return null;
  return (
    <MessageBar intent="error">
      <MessageBarBody>
        {error.error}
        {error.hint ? ` ${error.hint}` : ""}
      </MessageBarBody>
    </MessageBar>
  );
}

// ------------------------------------------------------------------ 1. empty state ----------------------------------

/** n179: the schema, chosen from the lakehouse's own list (exact names, with their tables); a text field only when the
 * list could not be read, with the reason. */
export function SchemaChoice(props: {
  schema: string;
  schemas: { loading: boolean; list?: SchemasAnswer; error?: EngineError };
  onSchemaChange: (schema: string) => void;
}) {
  const { loading, list, error } = props.schemas;
  if (loading) return <Spinner size="tiny" label="Reading the lakehouse's schemas…" />;
  if (error || !list) {
    return (
      <Field label="Schema" hint={error ? `The schemas could not be listed: ${error.error} Type the schema as the lakehouse spells it.` : "Choose a lakehouse first"}>
        <Input value={props.schema} disabled={!error} onChange={(_, d) => props.onSchemaChange(d.value)} />
      </Field>
    );
  }
  if (!list.schemas.length) return <Caption1>{list.note}</Caption1>;
  return (
    <Field label="Schema" hint={list.preselect ? "The only schema with tables is selected." : "Choose the schema to plan."}>
      <RadioGroup value={props.schema} onChange={(_, d) => props.onSchemaChange(d.value)} aria-label="Schema">
        {list.schemas.map((x) => (
          <Radio key={x.schema} value={x.schema} disabled={x.tables === 0}
            label={`${x.schema} (${x.tables === 0 ? "no tables" : x.tables === 1 ? "1 table" : `${x.tables} tables`})`} />
        ))}
      </RadioGroup>
    </Field>
  );
}

/** n179: the delegated permissions an output needs, folded: the text is kept for whoever sets up Entra. */
export function PermissionsNote({ needs, extra }: { needs: string[]; extra?: string }) {
  if (!needs.length) return null;
  return (
    <details className="krusgraph-permissions">
      <summary>
        <Caption1>Permissions</Caption1>
      </summary>
      <Caption1>
        Needs the delegated permission {needs.join(", and ")}.{extra ? ` ${extra}` : ""}
      </Caption1>
    </details>
  );
}

export function EmptyView(props: {
  source?: SourceDefinition;
  schema: string;
  schemas: { loading: boolean; list?: SchemasAnswer; error?: EngineError };
  onSchemaChange: (schema: string) => void;
  onChooseLakehouse: () => void;
  /** n201: a read-only source's target lakehouse */
  onChooseTarget?: () => void;
  onReview: () => void;
}) {
  const { source } = props;
  const readOnly = !!source && isReadOnly(source.itemType);
  return (
    <ItemEditorEmptyView
      title="Choose a source"
      description={
        "Krusgraph reads the table and column names of a lakehouse, a warehouse, a SQL database or a mirrored database " +
        "(data mirrored into Fabric, SAP via SAP Datasphere among it) and proposes keys and relationships, each with the " +
        "rule that found it. Nothing is created until you choose Create."
      }
      imageSrc="/assets/items/ModelItem/EditorEmpty.svg"
      imageAlt=""
      customContent={
        <div className="krusgraph-empty-form">
          <Button appearance={source ? "secondary" : "primary"} onClick={props.onChooseLakehouse}>
            {sourceButton(source)}
          </Button>
          {source && <SchemaChoice schema={props.schema} schemas={props.schemas} onSchemaChange={props.onSchemaChange} />}
          {readOnly && (
            <>
              <Body1>{targetLine(source, source.target)}</Body1>
              <Button appearance="secondary" onClick={props.onChooseTarget}>{targetButton(source.target)}</Button>
            </>
          )}
          <Button appearance="primary" disabled={!source || !props.schema.trim() || props.schemas.loading} onClick={props.onReview}>
            Find keys and relationships
          </Button>
        </div>
      }
    />
  );
}

// ------------------------------------------------------------------ the mascots (n173) -----------------------------

/** One mascot with its bubble. n216: the figure is the 3D one from the film and the site (mascotFigure.tsx),
 * decorative (aria-hidden); the sentence is the bubble's text. Glad poses only when a check passed (MASCOT_GLAD). */
export function MascotSays(props: { kind: MascotKind; text?: string; pose?: string; glad?: boolean; children?: React.ReactNode }) {
  if (!props.text && !props.children) return null;
  let pose = props.pose ?? "rest";
  if (!props.glad && MASCOT_GLAD.includes(pose)) pose = "explain";
  return (
    <li className={`krusgraph-say krusgraph-say-${props.kind}${props.glad ? " glad" : ""}`} data-mascot={props.kind}
      style={{ ["--kg-mascot" as string]: MASCOT_COLOURS[props.kind].fill }}>
      <MascotFigure kind={props.kind} pose={pose} />
      <div className="krusgraph-bubble">
        <Caption1 className="krusgraph-who">{MASCOT_NAMES[props.kind]}</Caption1>
        {props.text && <Body1>{props.text}</Body1>}
        {props.children}
      </div>
    </li>
  );
}

export function Mascots(props: { on: boolean; onToggle: () => void; children: React.ReactNode; plain: string[] }) {
  return (
    <section className="krusgraph-mascots-wrap" aria-label="What Onto, Thinker and Builder say">
      <style>{MASCOT_CSS}</style>
      <Switch checked={props.on} onChange={props.onToggle} label={props.on ? "Mascots: on" : "Mascots: off"} />
      {props.on ? (
        <ul className="krusgraph-mascots">{props.children}</ul>
      ) : (
        props.plain.filter(Boolean).map((line) => <Body1 key={line}>{line}</Body1>)
      )}
    </section>
  );
}

// ------------------------------------------------------------------ 2. review ---------------------------------------

const STATUS_LABEL: Record<ReviewStatus, string> = {
  open: "Waiting for you",
  proposed: "Suggested",
  accepted: "Accepted",
  rejected: "Rejected",
};

const CHECK_BADGE: Record<CheckState, { color: "success" | "danger" | "warning" | "informative"; label: string }> = {
  passed: { color: "success", label: "Passed" },
  failed: { color: "danger", label: "Failed" },
  stale: { color: "warning", label: "Check again" },
  not_checked: { color: "informative", label: "Not checked" },
};

export function RulePill({ rule }: { rule: string }) {
  return (
    <Tooltip content={ruleMeaning(rule)} relationship="description" withArrow>
      <Badge appearance="tint" color={rule.startsWith("K") ? "brand" : "informative"} tabIndex={0} className="krusgraph-pill">
        {rule}
      </Badge>
    </Tooltip>
  );
}

function ReviewRow(props: { item: ReviewItem; onDecide: (id: string, status: ReviewStatus) => void; sap?: SapOffer }) {
  const { item } = props;
  const st = checkState(item);
  const pack = sapMark(props.sap, item.id);                      // n201: "from the SAP pack", with the pack's sources
  const holds = holdsText(item);                                 // n209: a link the rows hold says so next to Reject
  const lost = rejectedRowText(item);
  return (
    <li className={`krusgraph-row krusgraph-row-${item.review} krusgraph-check-${st}`} data-id={item.id} data-check={st}>
      <RulePill rule={item.rule} />
      <div className="krusgraph-row-what">
        <Body1>{itemText(item)}</Body1>
        <Caption1 className="krusgraph-row-check">{checkText(item)}</Caption1>
        {pack && (
          <Caption1 className="krusgraph-row-pack" data-from="sap-pack">
            {pack.text}{" "}
            {pack.sources.map((src, i) => (
              <React.Fragment key={src.url + i}>
                {i > 0 && "; "}
                <a href={src.url} target="_blank" rel="noreferrer">{src.title}</a>
              </React.Fragment>
            ))}
          </Caption1>
        )}
      </div>
      <Badge appearance="filled" color={CHECK_BADGE[st].color} className="krusgraph-check-badge">
        {CHECK_BADGE[st].label}
      </Badge>
      <Caption1 className="krusgraph-row-status">{STATUS_LABEL[item.review]}</Caption1>
      <Button size="small" appearance={item.review === "accepted" ? "primary" : "secondary"}
        aria-pressed={item.review === "accepted"} onClick={() => props.onDecide(item.id, "accepted")}>
        Accept
      </Button>
      <Button size="small" appearance={item.review === "rejected" ? "primary" : "secondary"}
        aria-pressed={item.review === "rejected"} onClick={() => props.onDecide(item.id, "rejected")}>
        Reject
      </Button>
      {holds && <Caption1 className="krusgraph-row-holds" data-holds="true">{holds}</Caption1>}
      {lost && (
        <MessageBar intent="warning" className="krusgraph-row-lost"><MessageBarBody>{lost}</MessageBarBody></MessageBar>
      )}
    </li>
  );
}

/** The map, drawn by the MCP Apps cards' own code (cardMap.ts); redrawn when the map or a decision changes. */
export function PlanMap(props: { map?: MapData; review?: ReviewFile }) {
  const box = useRef<HTMLDivElement>(null);
  const shown = useMemo(() => (props.map ? overlay(props.map, props.review) : undefined), [props.map, props.review]);
  useEffect(() => {
    if (!box.current) return;
    try {
      drawPlanMap(box.current, shown);
    } catch {
      box.current.textContent = "The map could not be drawn here; the list shows the same keys and links.";
    }
  }, [shown]);
  if (!shown) return <Body1>The map appears after the next review. The list has every key and link.</Body1>;
  return (
    <div className="krusgraph-map">
      <style>{MAP_CSS}</style>
      <div ref={box} />
    </div>
  );
}

export function ReviewView(props: {
  source: SourceDefinition;
  review: ReviewFile;
  map?: MapData;
  answered: Record<string, string>;
  checking: boolean;
  mascotsOn: boolean;
  onToggleMascots: () => void;
  onDecide: (id: string, status: ReviewStatus) => void;
  onAcceptAll: (onlyPassed: boolean) => void;
  onCheck: () => void;
  onChoice: (choice: Choice) => void;
  /** n201: a read-only source, and the SAP pack's items with their sources */
  readOnly?: ReadOnlySource;
  sap?: SapOffer;
}) {
  const [tab, setTab] = useState<"map" | "list">("map");
  const notes = sourceNotes(props.readOnly, props.sap);
  const items = sortForReview(props.review.items);
  const say = sayings(props.review, props.answered);
  const qs = questions(props.review, props.answered);
  const totals = totalsOf(props.review);
  const all = acceptAllTargets(props.review).length;
  const passed = acceptAllTargets(props.review, true).length;
  const failedCount = totals.keys.failed + totals.relationships.failed;
  return (
    <div className="krusgraph-view">
      <Title3>
        {props.source.displayName} / {props.source.schema}
      </Title3>
      <Mascots on={props.mascotsOn} onToggle={props.onToggleMascots}
        plain={[...summaryLines(props.review), ...checkLines(props.review), say.thinker ?? ""]}>
        <MascotSays kind="onto" text={say.onto} pose={say.glad ? "celebrate" : "explain"} glad={say.glad} />
        <MascotSays kind="thinker" text={say.thinker} pose={failedCount ? "notice" : totals.checked ? "calm" : "think"} />
        <MascotSays kind="builder" text={say.builder} pose="point" />
      </Mascots>
      {notes.length > 0 && (
        <section className="krusgraph-source-notes" aria-label="About this source">
          {notes.map((line) => <Body1 key={line}>{line}</Body1>)}
        </section>
      )}

      <div className="krusgraph-actions">
        <Button appearance={totals.checked ? "secondary" : "primary"} icon={<CheckmarkStarburst24Regular />}
          disabled={props.checking} onClick={props.onCheck}>
          {totals.checked ? "Check against the rows again" : "Check against the rows"}
        </Button>
        <Button disabled={!all} onClick={() => props.onAcceptAll(false)}>
          Accept all ({all})
        </Button>
        <Button disabled={!passed} onClick={() => props.onAcceptAll(true)}
          title={totals.checked ? undefined : "Check against the rows first"}>
          Accept all that passed the check ({passed})
        </Button>
      </div>
      {totals.checked > 0 && (
        <div className="krusgraph-legend" aria-label="What the check found">
          <Badge appearance="filled" color={totals.keys.passed + totals.relationships.passed ? "success" : "informative"}>
            {totals.keys.passed + totals.relationships.passed} passed
          </Badge>
          <Badge appearance="filled" color={failedCount ? "danger" : "informative"}>{failedCount} failed</Badge>
          <Badge appearance="filled" color="informative">
            {totals.keys.not_checked + totals.relationships.not_checked + totals.keys.stale + totals.relationships.stale} not checked
          </Badge>
        </div>
      )}

      {qs.length > 0 && (
        <section aria-label="Thinker's questions">
          <ul className="krusgraph-mascots">
            {qs.map((q) => (
              <MascotSays key={q.about} kind="thinker" text={props.mascotsOn ? q.text : undefined} pose="think">
                {!props.mascotsOn && <Body1>{q.text}</Body1>}
                <div className="krusgraph-choices">
                  {q.choices.slice(0, 8).map((c) => (
                    <Button key={c.label} size="small" onClick={() => props.onChoice(c)}>
                      {c.label}
                    </Button>
                  ))}
                </div>
              </MascotSays>
            ))}
          </ul>
        </section>
      )}

      <TabList selectedValue={tab} onTabSelect={(_, d) => setTab(d.value as "map" | "list")} aria-label="Map or list">
        <Tab value="map">Map</Tab>
        <Tab value="list">List</Tab>
      </TabList>
      {rejectedHoldingText(props.review) && (
        <MessageBar intent="warning" data-lost="relationships">
          <MessageBarBody>{rejectedHoldingText(props.review)}</MessageBarBody>
        </MessageBar>
      )}
      {tab === "map" ? (
        <PlanMap map={props.map} review={props.review} />
      ) : (
        <section aria-label="Keys and links">
          <ul className="krusgraph-list">
            {items.map((it) => (
              <ReviewRow key={it.id} item={it} onDecide={props.onDecide} sap={props.sap} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ 3. choose outputs (n174: every output) ----------

export function OutputsView(props: {
  choices: OutputChoice[];
  onChange: (choices: OutputChoice[]) => void;
  created: CreatedItem[];
  product: { on: boolean; name: string };
  onProduct: (p: { on: boolean; name: string }) => void;
  stored?: ProductDefinition;
  onOpen: (item: OpenLink["item"]) => void;
  onPreview: () => void;
  /** n185: the last dry run said the sign-in cannot run or schedule pipelines: the two choices are shown disabled */
  jobsBlocked?: JobsCard["permission"];
}) {
  const pipe = props.choices.find((c) => c.type === "pipeline" && c.enabled);
  const problems = [...choiceProblems(props.choices), ...(pipe ? scheduleProblems(jobsOf(pipe).schedule) : [])];
  const productOk = !props.product.on || /^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$/.test(props.product.name.trim());
  const set = (kind: string, patch: Partial<OutputChoice>) =>
    props.onChange(props.choices.map((c) => (c.type === kind ? { ...c, ...patch } : c)));
  return (
    <div className="krusgraph-view">
      <Title3>Choose what to build</Title3>
      <Body1>
        Each output is made by the same engine as the Krusgraph tools in Claude, from the keys and links you reviewed. Preview shows a
        dry run of each; nothing is created until you choose Create. Nothing is run, scheduled or published unless you tick it.
      </Body1>
      {props.stored && <ProductView product={props.stored} onOpen={props.onOpen} title="Data product built so far" />}
      <div className="krusgraph-outputs">
        {KINDS.map((k) => {
          const c = props.choices.find((x) => x.type === k.kind);
          if (!c) return null;
          const act = nameAction(k.kind, c.name, props.created);
          const valid = validName(c.name);
          return (
            <section key={k.kind} className="krusgraph-output" aria-label={k.label}>
              <Checkbox checked={c.enabled} label={<ItemTitle kind={k.kind}>{k.label}</ItemTitle>}
                onChange={(_, d) => set(k.kind, { enabled: !!d.checked })} />
              <Caption1>{k.what}</Caption1>
              {c.enabled && (
                <>
                  <Field label={`Name of the ${k.label.toLowerCase()}`} validationState={valid ? "none" : "error"}
                    validationMessage={valid ? undefined : "Letters, digits and underscores only"}>
                    <Input value={c.name} onChange={(_, d) => set(k.kind, { name: d.value })} />
                  </Field>
                  {act.action === "update" && <Badge appearance="tint" color="brand">Update: {act.reason}</Badge>}
                  {act.action === "new_name" && (
                    <div>
                      <Caption1>{act.reason} </Caption1>
                      <Button size="small" onClick={() => set(k.kind, { name: act.suggestion })}>
                        Use {act.suggestion}
                      </Button>
                    </div>
                  )}
                  {k.kind === "report" && (
                    <Field label="Built on" hint="Empty: the semantic model chosen above. Or the name of a semantic model already in this workspace.">
                      <Input value={c.model ?? ""} onChange={(_, d) => set(k.kind, { model: d.value })} />
                    </Field>
                  )}
                  {k.kind === "pipeline" && (
                    <PipelineChoices jobs={jobsOf(c)} blocked={props.jobsBlocked} onChange={(j) => set(k.kind, { jobs: j })} />
                  )}
                  {k.kind === "data_agent" && <AgentChoices agent={agentOf(c)} onChange={(a) => set(k.kind, { agent: a })} />}
                  <PermissionsNote needs={k.needs} />
                </>
              )}
            </section>
          );
        })}
      </div>
      <section className="krusgraph-output" aria-label="Data product">
        <Checkbox checked={props.product.on} label="Bundle them as one data product"
          onChange={(_, d) => props.onProduct({ ...props.product, on: !!d.checked })} />
        <Caption1>
          One name over what this build makes, with the domains Krusgraph proposes for these tables and an owner you choose later. It is kept in
          this item; Fabric domains themselves need a Fabric administrator.
        </Caption1>
        {props.product.on && (
          <Field label="Name of the data product" validationState={productOk ? "none" : "error"}
            validationMessage={productOk ? undefined : "Letters, digits, spaces, '.', '_' or '-', at most 80"}>
            <Input value={props.product.name} onChange={(_, d) => props.onProduct({ ...props.product, name: d.value })} />
          </Field>
        )}
      </section>
      {problems.map((p) => (
        <MessageBar key={p} intent="warning">
          <MessageBarBody>{p}</MessageBarBody>
        </MessageBar>
      ))}
      <div>
        <Button appearance="primary" disabled={problems.length > 0 || !productOk} onClick={props.onPreview}>
          Preview
        </Button>
      </div>
      <AboutNotices />
    </div>
  );
}

// ------------------------------------------------------------------ the cards, the product -------------------------

function Problem({ card }: { card: BuildCard }) {
  const p = cardProblem(card);
  if (!p || featureOff(card)) return null;                  // n181: the App's admin card says it in full
  const warn = !card.refusal && !card.answer?.error;
  return (
    <MessageBar intent={warn ? "warning" : "error"} layout="multiline">
      <MessageBarBody>
        {warn ? "Create would stop here: " : ""}
        {p.error}
        {p.hint ? ` ${p.hint}` : ""}
        {p.steps && p.steps.length > 0 && (
          <ol className="krusgraph-steps" aria-label="Steps in Entra">
            {p.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        )}
      </MessageBarBody>
    </MessageBar>
  );
}

/** n180: what the person can do with a card built from another plan: Update (a dry run first) or a new name; and on
 * the Update's dry run, the update itself. */
export interface CardActions {
  onUpdate?: (card: BuildCard) => void;
  /** n197: send this card's step again (a red card, no answer, or held back by a failed run) */
  onRetry?: (card: BuildCard) => void;
  onNewName?: (card: BuildCard) => void;
  busy?: boolean;
  /** n181: the App's ticks as stored in outputs.json, and how to change them */
  appChoices?: AppChoices;
  onAppChoices?: (choices: AppChoices) => void;
  /** n209: the App's last package as outputs.json keeps it (appWords.readAppRecord), for an App already built */
  appRecord?: AppPackageRecord;
}

/** n181: the App (Rayfin, preview): the preflight, the ticks, the pages, the read-only connector, the package. */
export function AppPanel(props: { card: BuildCard; saved?: AppChoices; onAppChoices?: (c: AppChoices) => void; record?: AppPackageRecord }) {
  const c = props.card;
  if (builtWithoutPackage(c)) return <BuiltAppPanel saved={props.saved} record={props.record} />;   // n209
  const off = featureOff(c);
  if (off) {
    return (
      <MessageBar intent="warning" layout="multiline" aria-label="Fabric App items are off">
        <MessageBarBody>
          {off.error} Setting: “{off.setting}”{off.where ? `, ${off.where}` : ""}.
          <ol className="krusgraph-steps" aria-label="Steps for a Fabric administrator">
            {off.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </MessageBarBody>
      </MessageBar>
    );
  }
  const a = c.answer as Record<string, any> | undefined;
  if (!a || a.error) return null;
  const opts = optionsOf(c);
  const now = ticked(c, props.saved);
  const changed = !!props.saved && JSON.stringify(props.saved) !== JSON.stringify(ticked(c));
  const api = a.api as AppApi | undefined;
  const href = packageHref(a.package);
  return (
    <div aria-label="App (Rayfin, preview)">
      <Badge appearance="tint" color="warning">Preview</Badge> <Caption1>{PREVIEW_NOTE}</Caption1>
      <Body1>{preflightWords(a.preflight as AppPreflight)}</Body1>
      {opts && GROUPS.filter((g) => opts[g.key]).map((g) => (
        <fieldset key={g.key} className="krusgraph-output">
          <legend>{g.title}</legend>
          {(opts[g.key] ?? []).map((o) => (
            <Checkbox key={o.id} label={`${o.label} (${o.why})`} checked={(now[g.key] ?? []).includes(o.id)} disabled={!props.onAppChoices}
              onChange={(_, d) => props.onAppChoices?.(toggle(now, g.key, o.id, !!d.checked))} />
          ))}
        </fieldset>
      ))}
      {opts && chartTypes(opts, now).length > 0 && (
        <fieldset className="krusgraph-output">
          <legend>Chart type</legend>
          {chartTypes(opts, now).map((ch) => (
            <Field key={ch.id} label={ch.label}>
              <RadioGroup layout="horizontal" value={ch.type} disabled={!props.onAppChoices}
                onChange={(_, d) => props.onAppChoices?.(setChartType(now, ch.id, d.value as "bar" | "line" | "table"))}>
                {ch.types.map((t) => <Radio key={t} value={t} label={CHART_TYPE_WORDS[t]} />)}
              </RadioGroup>
            </Field>
          ))}
        </fieldset>
      )}
      {opts && pagesInOrder(opts, now).length > 1 && (
        <fieldset className="krusgraph-output">
          <legend>Order of the pages</legend>
          <ol className="krusgraph-steps" aria-label="Pages, in order">
            {pagesInOrder(opts, now).map((pg, i, all) => (
              <li key={pg.id}>
                <Body1>{pg.label} </Body1>
                <Button size="small" appearance="subtle" aria-label={`Move ${pg.label} up`} disabled={!props.onAppChoices || i === 0}
                  onClick={() => props.onAppChoices?.(movePage(opts, now, pg.id, -1))}>Up</Button>
                <Button size="small" appearance="subtle" aria-label={`Move ${pg.label} down`} disabled={!props.onAppChoices || i === all.length - 1}
                  onClick={() => props.onAppChoices?.(movePage(opts, now, pg.id, 1))}>Down</Button>
              </li>
            ))}
          </ol>
        </fieldset>
      )}
      {opts?.accents && (
        <fieldset className="krusgraph-output">
          <legend>Colour accent</legend>
          <RadioGroup layout="horizontal" value={now.accent ?? "blue"} disabled={!props.onAppChoices} aria-label="Colour accent"
            onChange={(_, d) => props.onAppChoices?.(setAccent(now, d.value))}>
            {opts.accents.map((x) => (
              <Radio key={x.id} value={x.id} label={<span><span aria-hidden className="krusgraph-swatch" style={{ background: x.light }} /> {x.label}</span>} />
            ))}
          </RadioGroup>
        </fieldset>
      )}
      {tickWarning(c, props.saved) && <MessageBar intent="warning"><MessageBarBody>{tickWarning(c, props.saved)}</MessageBarBody></MessageBar>}
      {changed && <Caption1>Your choices are saved in this item; choose Preview again to see the pages with them.</Caption1>}
      <Subtitle2>Pages</Subtitle2>
      <ul className="krusgraph-list">
        {(a.pages ?? []).map((p: { id: string; title: string; shows: string[] }) => (
          <li key={p.id}><Body1>{p.title}: {p.shows.join(", ")}</Body1></li>
        ))}
      </ul>
      {a.design && (
        <>
          <Subtitle2>Look and layout</Subtitle2>
          <ul className="krusgraph-list" aria-label="Look and layout">
            {designLines(a.design as AppDesign).map((l) => (
              <li key={l}><Body1>{l}</Body1></li>
            ))}
          </ul>
        </>
      )}
      <Subtitle2>Connector and its GraphQL API</Subtitle2>
      <ul className="krusgraph-list">
        {apiLines(api).map((l) => (
          <li key={l}><Body1>{l}</Body1></li>
        ))}
      </ul>
      <Caption1>{a.why_not_published}</Caption1>
      <Subtitle2>{APP_STEPS_TITLE}</Subtitle2>
      {href && (
        <div className="krusgraph-actions">
          <a href={href} download={a.package.filename}>Download the package ({a.package.filename})</a>
        </div>
      )}
      {a.one_command ? (
        <>
          <OneCommand oc={a.one_command} />
          <details>
            <summary>The same, one command at a time</summary>
            <ol className="krusgraph-steps" aria-label="Commands">
              {(a.commands ?? []).map((x: { step: string; command: string }) => (
                <li key={x.command}><Body1>{x.step}: </Body1><code>{x.command}</code></li>
              ))}
            </ol>
          </details>
        </>
      ) : (
        <ol className="krusgraph-steps" aria-label="Commands">
          {(a.commands ?? []).map((x: { step: string; command: string }) => (
            <li key={x.command}><Body1>{x.step}: </Body1><code>{x.command}</code></li>
          ))}
        </ol>
      )}
      {editHref(a.edit_yourself) && (
        <div className="krusgraph-actions" aria-label={EDIT_TITLE}>
          <a href={editHref(a.edit_yourself)} download={a.edit_yourself.file ?? "EDIT-WITH-AI.md"}>{EDIT_TITLE}</a>
          <Caption1> {EDIT_NOTE}</Caption1>
        </div>
      )}
    </div>
  );
}

/** n209 (the founder's test of 10 November 2026): an App already built, reopened. The engine skips it (nothing written,
 * no package made again), so its card has no options: the choices it was built with, its pages, the package and the one
 * command come from outputs.json, read-only. Never "Tick at least one ..." for it. */
export function BuiltAppPanel(props: { saved?: AppChoices; record?: AppPackageRecord }) {
  const r = props.record;
  const chosen = builtChoices(props.saved, r);
  const href = packageHref(r?.package);
  if (!chosen) {
    return <Caption1>{BUILT_APP_UNKNOWN}</Caption1>;
  }
  return (
    <div aria-label="App (Rayfin, preview), built">
      <Badge appearance="tint" color="warning">Preview</Badge> <Caption1>{PREVIEW_NOTE}</Caption1>
      <Subtitle2>Built with these choices</Subtitle2>
      <ul className="krusgraph-list" aria-label="Choices">
        {choiceLines(chosen, r?.labels).map((l) => (
          <li key={l}><Body1>{l}</Body1></li>
        ))}
      </ul>
      {(r?.pages ?? []).length > 0 && (
        <>
          <Subtitle2>Pages</Subtitle2>
          <ul className="krusgraph-list">
            {(r?.pages ?? []).map((p) => (
              <li key={p.id}><Body1>{p.title}: {p.shows.join(", ")}</Body1></li>
            ))}
          </ul>
        </>
      )}
      {(href || r?.one_command) && <Subtitle2>{APP_STEPS_TITLE}</Subtitle2>}
      {href && r?.package && (
        <div className="krusgraph-actions">
          <a href={href} download={r.package.filename}>Download the package ({r.package.filename})</a>
        </div>
      )}
      {r?.one_command && <OneCommand oc={r.one_command} />}
      <Caption1>{BUILT_APP_NOTE}</Caption1>
    </div>
  );
}

/** n197 (the founder's item 4): the App is published with one command in Azure Cloud Shell, copied with one button.
 * Microsoft documents no API for an App's pages or connector, so Krusgraph runs none; the command runs the package's
 * script (create, sign in, connector, unzip, publish), and holds no secret. */
export function OneCommand(props: { oc: { command: string; steps: string[]; why?: string } }) {
  const [copied, setCopied] = useState(false);
  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(props.oc.command);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return (
    <section aria-label="Publish the App with one command">
      <ol className="krusgraph-steps">
        {props.oc.steps.map((x) => (
          <li key={x}><Body1>{x}</Body1></li>
        ))}
      </ol>
      <code className="krusgraph-one-command">{props.oc.command}</code>
      <div className="krusgraph-actions">
        <Button appearance="primary" onClick={(): void => void copy()}>{copied ? "Copied" : "Copy the command"}</Button>
      </div>
      {props.oc.why && <Caption1>{props.oc.why}</Caption1>}
    </section>
  );
}

/** n184 (addition 2): the mark on a card's title once Create answered for it: green created, amber created with a step
 * still to do (or waiting for a choice), red failed. The word is in the label for screen readers and in the tooltip. */
export function StateMark(props: { state?: CardState }) {
  if (!props.state || STATE_MARK[props.state].tone === "neutral") return null;
  const m = STATE_MARK[props.state];
  const Icon = m.tone === "success" ? CheckmarkCircle20Filled : m.tone === "danger" ? ErrorCircle20Filled : Warning20Filled;
  return (
    <span className={`krusgraph-mark krusgraph-mark-${m.tone}`} role="img" aria-label={m.label} title={m.label} data-state={props.state}>
      <Icon aria-hidden />
    </span>
  );
}

/** n184 (addition 2): the finish of a Create: the banner (with Onto and Builder celebrating, when the mascots are on and
 * every output is done), Next, and how to keep it up to date. From the live run, or from outputs.json when reopened. */
export function FinishView(props: { last: LastCreate; mascotsOn: boolean; timeZone?: string }) {
  const b = banner(props.last, props.timeZone);
  const next = nextSteps(props.last);
  const intent = b.tone === "success" ? "success" : b.tone === "danger" ? "error" : "warning";
  return (
    <section className={`krusgraph-finish krusgraph-finish-${b.tone}`} aria-label="Create is done" data-tone={b.tone}>
      <style>{FINISH_CSS}</style>
      {props.mascotsOn ? (
        <ul className={`krusgraph-mascots${b.glad ? " krusgraph-cheer" : ""}`}>
          <style>{MASCOT_CSS}</style>
          <MascotSays kind="onto" text={b.title} pose={b.glad ? "celebrate" : "notice"} glad={b.glad} />
          <MascotSays kind="builder" text={b.when} pose={b.glad ? "celebrate" : "point"} glad={b.glad} />
        </ul>
      ) : null}
      <MessageBar intent={intent} layout="multiline" className="krusgraph-banner">
        <MessageBarBody>
          <strong>{b.title}</strong> {b.when}
          {b.reasons.length > 0 && (
            <ul className="krusgraph-list" aria-label="What needs you">
              {b.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
        </MessageBarBody>
      </MessageBar>
      {next.length > 0 && (
        <>
          <Subtitle2>Next</Subtitle2>
          <ol className="krusgraph-steps" aria-label="Next">
            {next.map((n) => (
              <li key={n}><Body1>{n}</Body1></li>
            ))}
          </ol>
        </>
      )}
      <Subtitle2>Keep it up to date</Subtitle2>
      <ul className="krusgraph-list" aria-label="Keep it up to date">
        {keepUpToDate(props.last).map((n) => (
          <li key={n}><Body1>{n}</Body1></li>
        ))}
      </ul>
    </section>
  );
}

/** n184: an output's title with the Fabric icon of the item type it creates at its left (fabricIcons.ts). */
export function ItemTitle(props: { kind?: string; children: React.ReactNode }) {
  const icon = itemIcon(props.kind);
  return (
    <span className="krusgraph-item-title">
      {icon && <img className="krusgraph-item-icon" src={icon.src} alt={icon.alt} width={ICON_SIZE} height={ICON_SIZE} />}
      {props.children}
    </span>
  );
}

/** n184: the notices for Microsoft's icons and trademarks, under Choose what to build. */
export function AboutNotices() {
  return (
    <details className="krusgraph-notices">
      <summary>About and notices</summary>
      {NOTICES.map((n) => (
        <Caption1 key={n} as="p">{n}</Caption1>
      ))}
    </details>
  );
}

export function OutputCard(props: { card: BuildCard; onOpen?: (item: OpenLink["item"]) => void } & CardActions) {
  const c = props.card;
  const facts = cardFacts(c);
  const links = openLinks(c.created?.length ? c.created : c.existing_items ?? []);
  const choose = needsChoice(c);
  const confirm = c.dry_run && !!c.confirm_update && !c.refusal && !c.answer?.error;
  const refresh = refreshWords(c);
  const refused = !!(c.refusal || c.answer?.error);
  return (
    <section className={`krusgraph-output${refused ? " refused" : ""}`} aria-label={cardTitle(c)} data-output={c.output}>
      <ItemTitle kind={c.output}><Subtitle2>{cardTitle(c)}</Subtitle2><StateMark state={cardState(c)} /></ItemTitle>
      {facts.length > 0 && (
        <ul className="krusgraph-list">
          {facts.map((f) => (
            <li key={f}>
              <Body1>{f}</Body1>
            </li>
          ))}
        </ul>
      )}
      <Problem card={c} />
      {isApp(c) && <AppPanel card={c} saved={props.appChoices} onAppChoices={props.onAppChoices} record={props.appRecord} />}
      {c.output === "pipeline" && <JobsPanel card={c} />}
      {c.output === "data_agent" && <AgentPanel card={c} />}
      {refresh && (
        <MessageBar intent={c.refresh?.status === "refreshed" ? "success" : c.refresh?.status === "planned" || c.refresh?.status === "refreshing" ? "info" : "warning"} layout="multiline">
          <MessageBarBody>
            {refresh}
            {c.refresh?.entra_steps && c.refresh.entra_steps.length > 0 && (
              <ol className="krusgraph-steps" aria-label="Steps in Entra">
                {c.refresh.entra_steps.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ol>
            )}
          </MessageBarBody>
        </MessageBar>
      )}
      {links.length > 0 && (
        <div className="krusgraph-actions">
          {links.map((l) => (
            <Button key={l.item.id} icon={<Open24Regular />} onClick={() => props.onOpen?.(l.item)}>
              Open in Fabric: {l.label}
            </Button>
          ))}
        </div>
      )}
      {c.output !== "rayfin_app" && (c.portal_steps ?? []).filter(Boolean).length > 0 && (
        <>
          <Caption1>{stepsTitle(c.output)}</Caption1>
          <ul className="krusgraph-list">
            {(c.portal_steps ?? []).filter(Boolean).map((s) => (
              <li key={s}>
                <Body1>{s}</Body1>
              </li>
            ))}
          </ul>
        </>
      )}
      {c.status === "running" && <Spinner size="tiny" label={progressLabel(c)} />}
      {c.status === "running" && c.progress?.state === "waiting_capacity" && (
        <MessageBar intent="warning" layout="multiline" aria-label="Waiting for capacity">
          <MessageBarBody>
            {c.progress.words ?? "Waiting for capacity: Fabric is throttling the capacity; the step is tried again by itself."}{" "}
            {c.progress.capacity_app && <Link href={c.progress.capacity_app} target="_blank">The Capacity Metrics app</Link>}
          </MessageBarBody>
        </MessageBar>
      )}
      {c.status === "running" && c.progress?.state === "pending_fabric" && (
        <MessageBar intent="info" layout="multiline" aria-label="Still running in Fabric">
          <MessageBarBody>{c.progress.words ?? "Still running in Fabric; Krusgraph follows it."}</MessageBarBody>
        </MessageBar>
      )}
      {c.after_run_words && c.after_run === "waiting" && <Body1>{c.after_run_words}</Body1>}
      {c.already_built && <Body1>{c.dry_run ? "Already built from this plan; Create will skip it." :
        (c.answer?.note as string | undefined) ?? "Already in the workspace, built from this plan by an earlier Create; nothing was written again."}</Body1>}
      {!c.dry_run && props.onRetry && canRetry(c) && (
        <div className="krusgraph-actions">
          <Button appearance="primary" disabled={props.busy} onClick={() => props.onRetry?.(c)}>
            Try again
          </Button>
        </div>
      )}
      {choose && (
        <>
          <Body1>
            Nothing was written for it.{" "}
            {c.choices?.includes("update")
              ? "Update rebuilds it from this plan in place (you see a dry run first), or choose a new name to keep it as it is."
              : "A report is never updated in place: choose a new name to build one from this plan; this one stays as it is."}
          </Body1>
          <div className="krusgraph-actions">
            {c.choices?.includes("update") && props.onUpdate && (
              <Button appearance="primary" disabled={props.busy} onClick={() => props.onUpdate?.(c)}>
                Update
              </Button>
            )}
            {props.onNewName && (
              <Button disabled={props.busy} onClick={() => props.onNewName?.(c)}>
                Choose a new name
              </Button>
            )}
          </div>
        </>
      )}
      {confirm && (
        <>
          <Body1>
            This is the dry run of the update{c.built_from ? ` of an item ${c.built_from.words}` : ""}: nothing was written yet.
          </Body1>
          {props.onUpdate && (
            <div className="krusgraph-actions">
              <Button appearance="primary" disabled={props.busy} onClick={() => props.onUpdate?.(c)}>
                Update in Fabric
              </Button>
              {props.onNewName && (
                <Button disabled={props.busy} onClick={() => props.onNewName?.(c)}>
                  Choose a new name instead
                </Button>
              )}
            </div>
          )}
        </>
      )}
      <PermissionsNote
        needs={c.permissions.needs}
        extra={c.output === "semantic_model" ? "Create refreshes the model once (Dataset.ReadWrite.All); nothing else is run or scheduled." : c.output === "pipeline" && (c.jobs?.run_once || c.jobs?.schedule) ? `Run once and Schedule use ${c.jobs.permission.scope} (or ${c.jobs.permission.or}).` : c.output === "data_agent" && c.agent?.publish ? "Publishing uses the same permission as creating the agent." : "No run or schedule permission is used."}
      />
    </section>
  );
}

/** n209: a dry run's data product item in the words its card uses: skipped and "Create will ask" are not "would be updated". */
export function productWould(x: { would?: string; decision?: string }): string {
  if (x.decision === "skip") return "already built from this plan, will be skipped";
  if (x.decision === "choose") return "built from another plan: Create will ask";
  return x.would === "update" ? "would be updated" : "would be created";
}

export function ProductView(props: {
  product: ProductDefinition | DataProduct;
  onOpen?: (item: OpenLink["item"]) => void;
  title?: string;
}) {
  const p = props.product;
  const items = p.items as (CreatedItem & { would?: string; output?: string; decision?: string })[];
  const withIds = items.filter((x) => x.id);
  return (
    <section className="krusgraph-product" aria-label={`Data product ${p.name}`}>
      <Caption1>{props.title ?? "Data product"}</Caption1>
      <Subtitle2>{p.name}</Subtitle2>
      <Body1>Owner: {p.owner ?? "nobody has chosen one yet"}. Plan {p.plan.plan_id ?? "?"}{p.plan.schema_fingerprint ? `, schema ${p.plan.schema_fingerprint}` : ""}.</Body1>
      <ul className="krusgraph-list">
        {items.map((x) => (
          <li key={x.id || `${x.output}:${x.name}`}>
            <Body1>
              {itemTypeLabel(x.type, x.output)} {x.name}
              {x.would ? ` (${productWould(x)})` : ""}
              {(x as { earlier?: boolean }).earlier ? " (earlier Create)" : ""}
            </Body1>
          </li>
        ))}
      </ul>
      {withIds.length > 0 && props.onOpen && (
        <div className="krusgraph-actions">
          {openLinks(withIds).map((l) => (
            <Button key={l.item.id} size="small" icon={<Open24Regular />} onClick={() => props.onOpen?.(l.item)}>
              Open {l.label}
            </Button>
          ))}
        </div>
      )}
      {p.domains.length > 0 && (
        <Caption1>
          Domains Krusgraph proposes: {p.domains.map((d) => `${d.name} (${d.tables.join(", ")})`).join("; ")}.
        </Caption1>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ 4. preview (dry run) ----------------------------

export function PreviewView(props: {
  answer: ManyAnswer;
  onCreate: () => void;
  mascotsOn: boolean;
  createLabel: string;
  appChoices?: AppChoices;
  onAppChoices?: (choices: AppChoices) => void;
  /** n209: the App's last package (outputs.json) */
  appRecord?: AppPackageRecord;
}) {
  const a = props.answer;
  const checkLine = dryRunCheckLine(a.row_check);
  const builder = previewLine(a);
  const checked = !!a.row_check?.checked;
  const failed = checked ? a.row_check.keys.failed + a.row_check.relationships.failed : 0;
  const canCreate = a.outputs.length > a.refused;
  return (
    <div className="krusgraph-view">
      <Title3>Dry run</Title3>
      {props.mascotsOn ? (
        <ul className="krusgraph-mascots">
          <style>{MASCOT_CSS}</style>
          <MascotSays kind="thinker" text={checkLine} pose={!checked ? "think" : failed ? "notice" : "heart"} glad={checked && !failed} />
          <MascotSays kind="builder" text={builder} pose="point" />
        </ul>
      ) : (
        <>
          <Body1>{checkLine}</Body1>
          <Body1>{builder}</Body1>
        </>
      )}
      <Body1>{a.note}</Body1>
      {a.product && <ProductView product={a.product} title="Data product (dry run)" />}
      {a.flow && <FlowView flow={a.flow} mascotsOn={props.mascotsOn} idPrefix="kg-flow-preview" />}
      {a.outputs.map((c) => (
        <OutputCard key={c.output} card={c} appChoices={props.appChoices} onAppChoices={props.onAppChoices} appRecord={props.appRecord} />
      ))}
      {a.left_out_by_review.length > 0 && (
        <section>
          <Subtitle2>Left out because of your review</Subtitle2>
          <ul className="krusgraph-list">
            {a.left_out_by_review.map((x) => (
              <li key={x.id}>
                <Body1>
                  {x.what}: {x.because}
                </Body1>
              </li>
            ))}
          </ul>
        </section>
      )}
      <div>
        <Button appearance="primary" disabled={!canCreate} onClick={props.onCreate}>
          {props.createLabel}
        </Button>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ 5. result ----------------------------------------

/** n209: the saved ticks and the package record of the App this card is for (outputs.json), for the result view. */
function appOf(outputs: OutputsDefinition, c: BuildCard): { appChoices?: AppChoices; appRecord?: AppPackageRecord } {
  if (!isApp(c)) return {};
  const ch = outputs.outputs.find((x) => x.type === "rayfin_app" && x.name === c.name);
  return { appChoices: ch?.app, appRecord: readAppRecord(ch?.app_package, c.name) };
}

export function ResultView(props: {
  answer?: ManyAnswer;
  outputs: OutputsDefinition;
  onOpen: (item: OpenLink["item"]) => void;
  mascotsOn: boolean;
  timeZone?: string;
  /** n197: send every red, unanswered or stopped card again */
  onCreateRest?: () => void;
  /** n197: one line when the saved state or the engine could not be read on reopening (Fabric busy) */
  notice?: string;
} & CardActions) {
  const a = props.answer;
  const rest = a && !running(a.outputs) ? toRetry(a.outputs) : [];
  const live = !!a && (a.outputs.length === 0 || running(a.outputs));
  // n184: the finish, from outputs.json (the editor writes it as soon as every card has its answer, and reopening reads it)
  const last = live ? undefined : readLastCreate(props.outputs.last_create);
  const said = a ? resultLine(a) : "This item built these before. Open each in Fabric; choose outputs again to update them.";
  const stored = props.outputs.product;
  const earlier = openLinks(props.outputs.created);
  return (
    <div className="krusgraph-view">
      <Title3>Built in Fabric</Title3>
      {props.notice && (
        <MessageBar intent="warning" aria-label="Fabric is busy">
          <MessageBarBody>{props.notice}</MessageBarBody>
        </MessageBar>
      )}
      {rest.length > 0 && props.onCreateRest && (
        <div className="krusgraph-actions">
          <Button appearance="primary" disabled={props.busy} onClick={() => props.onCreateRest?.()}>
            {`Create the rest (${rest.length})`}
          </Button>
        </div>
      )}
      {last ? (
        <FinishView last={last} mascotsOn={props.mascotsOn} timeZone={props.timeZone} />
      ) : props.mascotsOn ? (
        <ul className="krusgraph-mascots">
          <style>{MASCOT_CSS}</style>
          <MascotSays kind="builder" text={said} pose="point" />
        </ul>
      ) : (
        <Body1>{said}</Body1>
      )}
      {stored && <ProductView product={stored} onOpen={props.onOpen} />}
      {a?.flow && <FlowView flow={a.flow} mascotsOn={false} idPrefix="kg-flow-result" />}
      {a ? (
        a.outputs.map((c) => (
          <OutputCard key={c.output} card={c} onOpen={props.onOpen} onUpdate={props.onUpdate} onNewName={props.onNewName} busy={props.busy}
            onRetry={props.onRetry} {...appOf(props.outputs, c)} />
        ))
      ) : (
        <section>
          <Subtitle2>Created items</Subtitle2>
          <div className="krusgraph-actions">
            {earlier.map((l) => (
              <Button key={l.item.id} icon={<Open24Regular />} onClick={() => props.onOpen(l.item)}>
                Open in Fabric: {l.label}
              </Button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
