/**
 * The five views of the Krusgraph Model editor: empty state, review, choose outputs, preview (dry run), result.
 * n174: every output the MCP tools build (KINDS in buildWords.ts), one dry-run card each, the data product, the data flow
 * (FlowView.tsx), and the result with Open in Fabric and the portal steps left per item.
 * Copy follows the site: plain words, numbers only from the engine's answers, no claims about speed or compliance.
 * n173: the review shows the map (the MCP Apps cards' drawing, cardMap.ts) or the list, each row's check state
 * (green passed, red failed with its orphans or duplicates, grey not checked), Onto, Thinker and Builder in their own
 * colours with the site's figures, Thinker's questions with their choices inline, and Accept all. Words: modelWords.ts.
 */
import { RunNow } from "./RunNowView";
import { CsnChooser, SapDemo, SapDemoAnswer, SapFields } from "./SapViews";
import { CsnUpload } from "./csnUpload";
import { ReadOnlySource, SapOffer, isReadOnly, restType, sapMark, schemaProblem, sourceButton, sourceNotes, targetButton, targetLine } from "./sourceWords";
import React, { useState } from "react";
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
  MessageBarActions,
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
import { ArrowRight24Regular, CheckmarkCircle20Filled, CheckmarkStarburst24Regular, ErrorCircle20Filled, Open24Regular, Warning20Filled } from "@fluentui/react-icons";
import { ItemEditorEmptyView } from "../../components/ItemEditor";
import { SelfCheck, SelfCheckAnswer } from "./SelfCheck";
import { AppChoices, BuildCard, DataProduct, EngineError, JobsCard, ManyAnswer, OutputKind, SchemasAnswer } from "./engineClient";
import {
  AppApi, AppDesign, AppPackageRecord, AppPreflight, APP_BEFORE_CREATE, BUILT_APP_NOTE, BUILT_APP_UNKNOWN, CHART_TYPE_WORDS, EDIT_NOTE, EDIT_TITLE, GROUPS, PREVIEW_NOTE, apiLines, builtChoices,
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
  KindInfo,
  OpenLink,
  cardFacts,
  cardProblem,
  cardTitle,
  choiceProblems,
  nameAction,
  nameLabel,
  needsChoice,
  refreshWords,
  openLinks,
  previewLine,
  resultLine,
  validName,
} from "./buildWords";
import { FlowView, PlanMap } from "./lazyParts";   // n223: loaded when first shown
import { BUILD_IN_WORDS, BuildIn, buildIn, buildInLine, crossWorkspace, defaultLakehouseName, placeLine, targetRequest, validLakehouseName } from "./buildPlace";
import { builtOn, defaultsLine, notCheckedLine } from "./ed1Words";
import { ChosenProductsView } from "./SuggestedProductsView";
import { progressLabel } from "./createRun";
import { AgentChoices, AgentPanel, JobsPanel, PipelineChoices } from "./JobsViews";
import { agentOf, jobsOf, scheduleProblems } from "./jobsWords";
import { ICON_SIZE, KIND_TYPE, NOTICES, altBeside, itemIcon } from "./fabricIcons";
import { TypeIcon, TypeName } from "./itemIcons";
import { ONTO_EMPTY, DEFAULT_BUILD, FIRST_LINE, PIPELINE_PARTS } from "./stepWords";
import { ProofStrip } from "./NextStepsView";
import {
  APP_STEPS_TITLE, CardState, FINISH_CSS, LastCreate, STATE_MARK, banner, cardState, itemTypeLabel, keepUpToDate, nextSteps,
  readLastCreate, running, stepsTitle,
} from "./createWords";
import { MapData } from "./cardMap";
import { MASCOT_COLOURS, MASCOT_CSS, MASCOT_GLAD, MASCOT_NAMES } from "./cardMap.generated";
import { MascotFigure } from "./mascotFigure";
import { OntoWait } from "./OntoWait";
import { VerifyButton } from "./verifyBuilt";
import {
  Blocker, SharedError, createBlocker, earlierLabel, finishLabel, isWaiting, itemStatus, ownerLine, planLine, retryState, sameErrorLine,
  sharedErrors, splitBuilds, toFinish,
} from "./ed2Create";
import { FileActions } from "./fileOffer";   // WB10: downloads that work inside Fabric's frame
import { Wait, newWait } from "./waitWords";
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

/** F1: the empty view's sentence ("SAP via SAP Datasphere among it" read as a slip). */
export const CHOOSE_SOURCE_WORDS =
  "Krusgraph reads the table and column names of a lakehouse, a warehouse, a SQL database or a mirrored database " +
  "(data mirrored into Fabric, for example SAP through SAP Datasphere) and proposes keys and relationships, each with the " +
  "rule that found it. Nothing is created until you choose Create.";

export type MascotKind = "onto" | "thinker" | "builder";
import "./ModelItem.scss";

/** n223: a wait in a view, drawn by the one loading component (OntoWait.tsx): Onto, the step, the slow line after 10 s
 * and the offer after 30 s. A plain label still works (a wait that started now, nothing known yet). */
export function Busy(props: { label?: string; wait?: Wait; mascotsOn?: boolean; onCancel?: () => void; skeleton?: number | false }) {
  const [since] = useState(() => Date.now());   // a label alone: its wait started when it was first shown
  const wait = props.wait ?? newWait(props.label ?? "Working…", since, { steps: [] });
  return (
    <div className="krusgraph-view">
      <OntoWait wait={wait} mascotsOn={props.mascotsOn} onCancel={props.onCancel} skeleton={props.skeleton} />
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
  schemas: { loading: boolean; list?: SchemasAnswer; error?: EngineError; wait?: Wait };
  onSchemaChange: (schema: string) => void;
  mascotsOn?: boolean;
  /** W13: the source's name, for the no-access sentence */
  sourceName?: string;
}) {
  const { loading, list, error } = props.schemas;
  // n223: a list kept in the item shows at once while it is read again; without one, the wait is Onto's line
  if (loading && !list) return <Busy wait={props.schemas.wait} label="Reading the lakehouse's schemas…" skeleton={2} mascotsOn={props.mascotsOn} />;
  if (error && !schemaProblem(error, props.sourceName ?? "").typeIt) {
    // W13: no access is not fixed by typing a schema: say what to ask for (the field would only lead to the same 403)
    return (
      <MessageBar intent="warning" role="alert">
        <MessageBarBody>{schemaProblem(error, props.sourceName ?? "").line}</MessageBarBody>
      </MessageBar>
    );
  }
  if (error || !list) {
    return (
      <Field label="Schema" hint={error ? schemaProblem(error, props.sourceName ?? "").line : "Choose a lakehouse first"}>
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
  schemas: { loading: boolean; list?: SchemasAnswer; error?: EngineError; wait?: Wait };
  onSchemaChange: (schema: string) => void;
  onChooseLakehouse: () => void;
  mascotsOn?: boolean;
  /** n201: a read-only source's target lakehouse */
  onChooseTarget?: () => void;
  onReview: () => void;
  /** WB9: the pilot's self-check, when the item's workspace is known */
  onSelfCheck?: () => Promise<SelfCheckAnswer>;
}) {
  const { source } = props;
  const readOnly = !!source && isReadOnly(source.itemType);
  return (
    <ItemEditorEmptyView
      title="Choose a source"
      description={FIRST_LINE}
      customContent={
        <div className="krusgraph-empty-form">
          {props.mascotsOn !== false && (
            // WB6 (F7): Onto and one plain sentence instead of the kit's check-mark picture; the figure is decorative,
            // the sentence is text. With the mascots off, the title and first line above say the same.
            <section className="kg-empty-onto" aria-label="Onto">
              <style>{MASCOT_CSS}</style>
              <ul className="krusgraph-mascots"><MascotSays kind="onto" pose="explain" text={ONTO_EMPTY} /></ul>
            </section>
          )}
          <details className="kg-how">
            <summary><Caption1>What Krusgraph reads, and what it changes</Caption1></summary>
            <Caption1 as="p">{CHOOSE_SOURCE_WORDS}</Caption1>
          </details>
          <Button appearance={source ? "secondary" : "primary"} onClick={props.onChooseLakehouse}
            icon={source ? <TypeIcon type={restType(source.itemType)} beside={sourceButton(source)} /> : undefined}>
            {sourceButton(source)}
          </Button>
          {source && <SchemaChoice schema={props.schema} schemas={props.schemas} onSchemaChange={props.onSchemaChange} mascotsOn={props.mascotsOn}
            sourceName={source.displayName} />}
          {source && props.schemas.loading && props.schemas.list && (
            <Caption1 role="status">The schemas kept in this item are shown; reading them again…</Caption1>
          )}
          {readOnly && (
            <>
              <Body1>{targetLine(source, source.target)}</Body1>
              <Button appearance="secondary" onClick={props.onChooseTarget}
                icon={<TypeIcon type="Lakehouse" beside={targetButton(source.target)} />}>{targetButton(source.target)}</Button>
            </>
          )}
          <Button appearance={source ? "primary" : "secondary"} disabled={!source || !props.schema.trim() || (props.schemas.loading && !props.schemas.list) ||
            (!!props.schemas.error && !schemaProblem(props.schemas.error, source.displayName).typeIt)} onClick={props.onReview}>
            Find keys and relationships
          </Button>
          <SelfCheck send={props.onSelfCheck} />
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

// n223: the map (planMapView.tsx) loads when a review first shows it: lazyParts.PlanMap

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
  /** W13: the step after the review, shown on the page (it was only the ribbon's arrow) */
  onNext?: () => void;
  /** WB5: the CSN file chosen in the editor, and choosing or removing one */
  csn?: CsnUpload;
  onCsn?: (v: CsnUpload | null) => void;
  /** WB5: Load SAP demo data (shown when the review found no SAP tables) */
  onSapDemo?: (dryRun: boolean, confirm?: string) => Promise<SapDemoAnswer>;
}) {
  const [tab, setTab] = useState<"map" | "list">("map");
  const notes = sourceNotes(props.readOnly, props.sap);
  const items = sortForReview(props.review.items);
  const say = sayings(props.review, props.answered);
  const qs = questions(props.review, props.answered);
  const totals = totalsOf(props.review);
  const passed = acceptAllTargets(props.review, true).length;
  const failedCount = totals.keys.failed + totals.relationships.failed;
  const notChecked = notCheckedLine(props.review?.items as never, totals.checked);
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
      <SapFields sap={props.sap} />
      {props.onCsn && <CsnChooser csn={props.csn} disabled={props.checking} onCsn={props.onCsn} />}
      {!props.sap && props.onSapDemo && <SapDemo send={props.onSapDemo} />}

      <div className="krusgraph-actions">
        <Button appearance={totals.checked ? "secondary" : "primary"} icon={<CheckmarkStarburst24Regular />}
          disabled={props.checking} onClick={props.onCheck}>
          {totals.checked ? "Check against the rows again" : "Check against the rows"}
        </Button>
        {/* SM3: "Accept all that passed" is the only accept-all; each link is still accepted or rejected on its own.
            ED1: shown only when there is something to accept */}
        {passed > 0 && (
          <Button onClick={() => props.onAcceptAll(true)}>
            Accept all that passed the check ({passed})
          </Button>
        )}
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

      {/* ED1: which items the check did not count, and why, in one line */}
      {notChecked && <Caption1 as="p" data-ed1="not-checked">{notChecked.text}{notChecked.again ? " Krusgraph checks them again on its own." : ""}</Caption1>}
      {totals.checked > 0 && <ProofStrip review={props.review} />}
      {props.onNext && (
        <div className="kg-primary-row">
          <Button appearance={totals.checked ? "primary" : "secondary"} icon={<ArrowRight24Regular />} onClick={props.onNext}>
            Next: Decide what to build
          </Button>
          <Caption1>{totals.checked ? "A dry run comes before anything is created." : "You can check against the rows first, or go on without it."}</Caption1>
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

/** n221: where the outputs are built. This item's workspace is the default, so a Model in a new workspace builds its
 * own data product there; the source's workspace builds beside the source, as before n221. ED1 (Gustav, 21 November
 * 2026): one line says where silver and gold go (placeLine, the same targetRequest the dry run sends); the workspace, the
 * lakehouse and its name are under Change. In another workspace with no lakehouse chosen, Create makes one named after
 * the source (or uses it when it is there): no checkbox. */
export function BuildInChoice(props: {
  source: SourceDefinition;
  itemWorkspaceId?: string;
  onBuildIn: (patch: { buildIn?: BuildIn; createLakehouse?: string | null }) => void;
  onChooseTarget?: () => void;
  /** ED1: Change is open */
  open?: boolean;
  /** ED2: the data product's or the item's name, which the default lakehouse is named after */
  named?: string;
}) {
  const { source } = props;
  const cross = crossWorkspace(source, props.itemWorkspaceId);
  const t = targetRequest(source, props.itemWorkspaceId, props.named);
  const make = source.createLakehouse ?? (cross ? defaultLakehouseName(source.displayName, props.named) : undefined);
  return (
    <section className="krusgraph-build-in" aria-label="Build in">
      <Body1 data-ed1="place">{placeLine(source, props.itemWorkspaceId, props.named)}</Body1>
      {props.open && (
        <div className="kg-change" aria-label="Where it is built">
          <Field label="Build in">
            <RadioGroup layout="horizontal" value={buildIn(source)} onChange={(_, d) => props.onBuildIn({ buildIn: d.value as BuildIn })}>
              {(["item", "source"] as BuildIn[]).map((w) => <Radio key={w} value={w} label={BUILD_IN_WORDS[w]} />)}
            </RadioGroup>
          </Field>
          <Caption1 as="p">{buildInLine(source, props.itemWorkspaceId)}</Caption1>
          {cross && props.onChooseTarget && (
            <Button size="small" appearance="secondary" onClick={props.onChooseTarget}>
              {source.target ? `Lakehouse for silver and gold: ${source.target.displayName}` : "Choose another lakehouse for silver and gold"}
            </Button>
          )}
          {cross && !t.lakehouse && make !== undefined && (
            <Field label="Name of the lakehouse Create makes" validationState={validLakehouseName(make) ? "none" : "error"}
              validationMessage={validLakehouseName(make) ? undefined : "Letters, digits and underscores, starting with a letter"}>
              <Input value={make} onChange={(_, d) => props.onBuildIn({ createLakehouse: d.value })} />
            </Field>
          )}
        </div>
      )}
    </section>
  );
}

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
  /** n221: Build in (this item's workspace by default) and the lakehouse for silver and gold there */
  source?: SourceDefinition;
  itemWorkspaceId?: string;
  onBuildIn?: (patch: { buildIn?: BuildIn; createLakehouse?: string | null }) => void;
  onChooseTarget?: () => void;
  /** n222: the suggested data products panel, shown before Preview */
  extra?: React.ReactNode;
  /** ED1: Change on the report's "Built on": a picker of the semantic models in the workspace (no free text) */
  onPickModel?: () => void;
  /** ED1: Change open from the start (tests) */
  changeOpen?: boolean;
  /** ED2: the data product's owner: the one chosen, else the signed-in person (the same line as the dry run's) */
  owner?: string | null;
}) {
  const [changing, setChanging] = React.useState(!!props.changeOpen);
  const pipe = props.choices.find((c) => c.type === "pipeline" && c.enabled);
  const problems = [...choiceProblems(props.choices, props.created), ...(pipe ? scheduleProblems(jobsOf(pipe).schedule) : [])];
  const productOk = !props.product.on || /^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$/.test(props.product.name.trim());
  // SM3: ticking or unticking the pipeline ticks its silver and gold notebooks with it, as the chat's pipeline has them
  const set = (kind: string, patch: Partial<OutputChoice>) =>
    props.onChange(props.choices.map((c) => (c.type === kind ? { ...c, ...patch }
      : kind === "pipeline" && patch.enabled !== undefined && (PIPELINE_PARTS as readonly string[]).includes(c.type) ? { ...c, enabled: patch.enabled } : c)));
  // SM3: the three defaults first (stepWords.DEFAULT_BUILD), the other six under "More outputs"
  const isMain = (k: OutputKind) => (DEFAULT_BUILD as readonly string[]).includes(k);
  const main = DEFAULT_BUILD.map((d) => KINDS.find((k) => k.kind === d)!).filter(Boolean);
  const more = KINDS.filter((k) => !isMain(k.kind));
  const moreTicked = more.filter((k) => props.choices.find((x) => x.type === k.kind)?.enabled).length;
  // the fold opens when something other than the defaults (and the pipeline's own notebooks) is ticked, e.g. by a next step
  const pipeOn = !!props.choices.find((x) => x.type === "pipeline")?.enabled;
  const openMore = more.some((k) => props.choices.find((x) => x.type === k.kind)?.enabled && !(pipeOn && (PIPELINE_PARTS as readonly string[]).includes(k.kind)));
  const card = (k: KindInfo) => {
          const c = props.choices.find((x) => x.type === k.kind);
          if (!c) return null;
          const act = nameAction(k.kind, c.name, props.created);
          const valid = validName(c.name);
          return (
            <section key={k.kind} className="krusgraph-output" aria-label={k.label}>
              <Checkbox checked={c.enabled} label={<ItemTitle kind={k.kind}>{k.label}</ItemTitle>}
                onChange={(_, d) => set(k.kind, { enabled: !!d.checked })} />
              <Caption1 as="p">{k.what}</Caption1>
              {k.kind === "rayfin_app" && (
                <Body1 className="krusgraph-app-before" data-say="builder"><strong>Builder:</strong> {APP_BEFORE_CREATE}</Body1>
              )}
              {c.enabled && (
                <>
                  {/* ED1: the name comes from the rule (<source>_<suffix>) and is shown; Change makes it a text box */}
                  {changing ? (
                    <Field label={nameLabel(k.label)} validationState={valid ? "none" : "error"}
                      validationMessage={valid ? undefined : "Letters, digits and underscores only"}>
                      <Input value={c.name} onChange={(_, d) => set(k.kind, { name: d.value })} />
                    </Field>
                  ) : (
                    <Caption1 as="p" data-ed1="name">Name: {c.name}{valid ? "" : " (letters, digits and underscores only: change it under Change)"}</Caption1>
                  )}
                  {act.action === "update" && <Badge appearance="tint" color="brand">Update: {act.reason}</Badge>}
                  {act.action === "new_name" && (
                    <div>
                      <Caption1>{act.reason} </Caption1>
                      <Button size="small" onClick={() => set(k.kind, { name: act.suggestion })}>
                        Use {act.suggestion}
                      </Button>
                    </div>
                  )}
                  {/* ED1: what it is built on, as a visible default (the report on the model above) */}
                  {(() => {
                    const b = builtOn(k.kind, props.choices, props.created, props.source?.displayName);
                    return b ? <Caption1 as="p" data-ed1="built-on" className={b.missing ? "kg-missing" : undefined}>{b.text}</Caption1> : null;
                  })()}
                  {!changing && defaultsLine(k.kind, c) && <Caption1 as="p" data-ed1="defaults">{defaultsLine(k.kind, c)}</Caption1>}
                  {changing && k.kind === "report" && (
                    <div className="krusgraph-choices">
                      {props.onPickModel && <Button size="small" onClick={props.onPickModel}>Choose a semantic model in this workspace</Button>}
                      {c.model && <Button size="small" onClick={() => set(k.kind, { model: "" })}>Use the semantic model above</Button>}
                    </div>
                  )}
                  {changing && k.kind === "pipeline" && (
                    <PipelineChoices jobs={jobsOf(c)} blocked={props.jobsBlocked} onChange={(j) => set(k.kind, { jobs: j })} />
                  )}
                  {changing && k.kind === "data_agent" && <AgentChoices agent={agentOf(c)} onChange={(a) => set(k.kind, { agent: a })} />}
                  {changing && <PermissionsNote needs={k.needs} />}
                </>
              )}
            </section>
          );
  };
  return (
    <div className="krusgraph-view">
      <Title3>Choose what to build</Title3>
      <Body1>
        The pipeline, a semantic model and a data agent, as in Claude. Dry run shows each; nothing is created until you choose Create.
      </Body1>
      {props.source && props.onBuildIn && (
        <BuildInChoice source={props.source} itemWorkspaceId={props.itemWorkspaceId} onBuildIn={props.onBuildIn}
          onChooseTarget={props.onChooseTarget} open={changing} named={props.product.name.trim() || undefined} />
      )}
      {/* ED1: one Change for every default on this step: where it is built, the names, the report's model, the
          pipeline's runs, the agent's layer and publishing, the permissions */}
      <div>
        <Button appearance="transparent" aria-expanded={changing} onClick={() => setChanging(!changing)}>
          {changing ? "Done changing" : "Change"}
        </Button>
      </div>
      {props.stored && <ProductView product={props.stored} onOpen={props.onOpen} title="Data product built so far" />}
      <div className="krusgraph-outputs">
        {main.map(card)}
      </div>
      {/* SM3: the other six outputs, the data product and the suggested products under one fold */}
      <details className="kg-more-outputs" open={openMore || undefined}>
        <summary>More outputs{moreTicked ? ` (${moreTicked} ticked)` : ""}</summary>
      <div className="krusgraph-outputs">
        {more.map(card)}
      </div>
      <section className="krusgraph-output" aria-label="Data product">
        <Checkbox checked={props.product.on} label="Bundle them as one data product"
          onChange={(_, d) => props.onProduct({ ...props.product, on: !!d.checked })} />
        <Caption1>
          One name over what this build makes, with the data products Krusgraph proposes for these tables. It is kept in
          this item; Fabric domains themselves need a Fabric administrator. <span data-ed2="owner">{ownerLine(props.owner)}</span>
        </Caption1>
        {props.product.on && (
          <Field label="Name of the data product" validationState={productOk ? "none" : "error"}
            validationMessage={productOk ? undefined : "Letters, digits, spaces, '.', '_' or '-', at most 80"}>
            <Input value={props.product.name} onChange={(_, d) => props.onProduct({ ...props.product, name: d.value })} />
          </Field>
        )}
      </section>
      {props.extra}
      </details>
      {problems.map((p) => (
        <MessageBar key={p} intent="warning">
          <MessageBarBody>{p}</MessageBarBody>
        </MessageBar>
      ))}
      <div>
        <Button appearance="primary" disabled={problems.length > 0 || !productOk} onClick={props.onPreview}>
          Dry run
        </Button>
      </div>
      <AboutNotices />
    </div>
  );
}

// ------------------------------------------------------------------ the cards, the product -------------------------

function Problem({ card, shared }: { card: BuildCard; shared?: SharedError[] }) {
  const p = cardProblem(card);
  if (!p || featureOff(card)) return null;                  // n181: the App's admin card says it in full
  const same = shared ? sameErrorLine(card, shared) : undefined;   // ED2: the same error is said once, above the cards
  if (same) return <Body1 data-ed2="same-error">{same}</Body1>;
  if (isWaiting(card)) return <Body1 data-ed2="waiting">{p.error}</Body1>;   // ED2: "Waiting for silver", one line, not red
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
  /** ED2: errors several cards share, said once above them */
  shared?: SharedError[];
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
          <FileActions file={{ filename: a.package.filename, mime: "application/zip", base64: a.package.zip_base64 }}
            label={`Download the package (${a.package.filename})`} copy={false} />
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
          <FileActions file={{ filename: a.edit_yourself.file ?? "EDIT-WITH-AI.md", mime: "text/markdown", text: a.edit_yourself.markdown }}
            label={EDIT_TITLE} copyLabel="Copy the text" appearance="subtle" />
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
          <FileActions file={{ filename: r.package.filename, mime: "application/zip", base64: r.package.zip_base64 }}
            label={`Download the package (${r.package.filename})`} copy={false} />
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
export function ItemTitle(props: { kind?: string; children: React.ReactNode; label?: string }) {
  const icon = itemIcon(props.kind);
  // W13: the label's own words, when it is text, decide whether the icon's alt would repeat them (altBeside)
  const label = props.label ?? (typeof props.children === "string" ? props.children : undefined);
  return (
    <span className="krusgraph-item-title">
      {icon && <img className="krusgraph-item-icon" src={icon.src} alt={altBeside(icon.alt, label)} width={ICON_SIZE} height={ICON_SIZE} />}
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
  const refused = !!(c.refusal || c.answer?.error) && !isWaiting(c);
  const retry = retryState(c);                                  // ED2: Try again only where a retry can work
  return (
    <section className={`krusgraph-output${refused ? " refused" : ""}`} aria-label={cardTitle(c)} data-output={c.output}>
      <ItemTitle kind={c.output} label={cardTitle(c)}><Subtitle2>{cardTitle(c)}</Subtitle2><StateMark state={cardState(c)} /></ItemTitle>
      {facts.length > 0 && (
        <ul className="krusgraph-list">
          {facts.map((f) => (
            <li key={f}>
              <Body1>{f}</Body1>
            </li>
          ))}
        </ul>
      )}
      <Problem card={c} shared={props.shared} />
      {c.reads && <Body1 data-ed2="reads">{c.reads}</Body1>}
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
            <React.Fragment key={l.item.id}>
              {/* ED3: primary, a new tab; Run now beside a notebook or pipeline this Create made */}
              <Button appearance="primary" icon={<Open24Regular />} onClick={() => props.onOpen?.(l.item)}>
                Open in Fabric: {l.label}
              </Button>
              <RunNow item={l.item} />
            </React.Fragment>
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
      {!c.dry_run && props.onRetry && retry.can && (
        <div className="krusgraph-actions">
          <Button appearance="primary" disabled={props.busy} onClick={() => props.onRetry?.(c)}>
            Try again
          </Button>
        </div>
      )}
      {!c.dry_run && !retry.can && retry.why && !isWaiting(c) && <Caption1 data-ed2="no-retry">{retry.why}</Caption1>}
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
  /** ED2: the cards of this build, for each item's status; earlier builds come under one collapsed line */
  cards?: BuildCard[];
  /** ED2: Clean up earlier builds: the delete dry run of exactly these items (nothing is deleted without a confirm) */
  onCleanUp?: (ids: string[]) => void;
  busy?: boolean;
}) {
  const p = props.product;
  const items = p.items as (CreatedItem & { would?: string; output?: string; decision?: string; earlier?: boolean })[];
  const { now, earlier } = splitBuilds(items);
  const status = (x: (typeof items)[number]) => {
    if (x.would) return productWould(x);
    const c = props.cards?.find((k) => k.output === x.output);
    return c ? itemStatus(c) : "built";
  };
  const line = (x: (typeof items)[number]) => (
    <li key={x.id || `${x.output}:${x.name}`}>
      <Body1>
        <TypeName type={x.type || KIND_TYPE[x.output ?? ""]} text={itemTypeLabel(x.type, x.output)} /> {x.name}: {status(x)}
        {x.id && props.onOpen && (
          <>
            {" "}
            <Link as="button" onClick={() => props.onOpen?.(openLinks([x])[0].item)}>Open</Link>
          </>
        )}
      </Body1>
    </li>
  );
  const ids = earlier.map((x) => x.id).filter(Boolean) as string[];
  const plan = planLine(p.plan);
  return (
    <section className="krusgraph-product" aria-label={`Data product ${p.name}`}>
      <Caption1>{props.title ?? "Data product"}</Caption1>
      <Subtitle2>{p.name}</Subtitle2>
      <Body1>{ownerLine(p.owner)}{plan ? ` ${plan}` : ""}</Body1>
      <ul className="krusgraph-list" data-ed2="this-build">{now.map(line)}</ul>
      {earlier.length > 0 && (
        <details data-ed2="earlier">
          <summary>{earlierLabel(earlier.length)}</summary>
          <ul className="krusgraph-list">{earlier.map((x) => (
            <li key={x.id || `${x.output}:${x.name}`}><Body1><TypeName type={x.type || KIND_TYPE[x.output ?? ""]} text={itemTypeLabel(x.type, x.output)} /> {x.name}</Body1></li>
          ))}</ul>
          {props.onCleanUp && ids.length > 0 && (
            <div className="krusgraph-actions">
              <Button size="small" disabled={props.busy} onClick={() => props.onCleanUp?.(ids)}>Clean up earlier builds: see what would be deleted</Button>
            </div>
          )}
        </details>
      )}
      {p.domains.length > 0 && (
        <Caption1>
          {PRODUCTS_LINE}{p.domains.map((d) => `${d.name} (${d.tables.join(", ")})`).join("; ")}.
        </Caption1>
      )}
    </section>
  );
}

/** ED2: one name for the grouping everywhere (domains.data_products): the suggestions, the dry run and the result. */
export const PRODUCTS_LINE = "Data products Krusgraph proposes: ";

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
  /** n222: a Create is starting or running (or the editor is busy): the button says so instead of doing nothing */
  creating?: boolean;
  /** ED2: one line when the item's saved review was older than the one this dry run used */
  stale?: string;
  /** ED2: the one button that fixes what keeps Create off */
  onFixBlocker?: (b: Blocker) => void;
}) {
  const a = props.answer;
  const checkLine = dryRunCheckLine(a.row_check);
  const builder = previewLine(a);
  const checked = !!a.row_check?.checked;
  const failed = checked ? a.row_check.keys.failed + a.row_check.relationships.failed : 0;
  const blocker = createBlocker(a);                            // ED2: Create stays off while a known blocker remains
  const canCreate = a.outputs.length > 0 && !blocker;
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
      {props.stale && <Caption1 data-ed2="stale">{props.stale}</Caption1>}
      {a.lakehouse && <Body1 data-ed2="lakehouse">{a.lakehouse.words}</Body1>}
      <Body1>{a.note}</Body1>
      {a.product && <ProductView product={a.product} title="Data product (dry run)" />}
      <ChosenProductsView products={a.products} />
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
      {blocker && (
        <MessageBar intent="warning" layout="multiline" aria-label="Create is off" data-ed2="blocker">
          <MessageBarBody>{blocker.line}</MessageBarBody>
          {props.onFixBlocker && (
            <MessageBarActions>
              <Button size="small" appearance="primary" disabled={!!props.creating} onClick={() => props.onFixBlocker?.(blocker)}>{blocker.button}</Button>
            </MessageBarActions>
          )}
        </MessageBar>
      )}
      <div>
        <Button appearance="primary" disabled={!canCreate || !!props.creating} onClick={props.onCreate}>
          {props.creating ? "Creating…" : props.createLabel}
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
  /** ED2: Clean up earlier builds (the delete dry run first; nothing is deleted without the person's confirm) */
  onCleanUp?: (ids: string[]) => void;
} & CardActions) {
  const a = props.answer;
  const rest = a && !running(a.outputs) ? toFinish(a.outputs) : [];   // ED2: Fix and finish builds only what is missing
  const shared = a ? sharedErrors(a.outputs) : [];
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
        <div className="krusgraph-actions" data-ed2="finish">
          <Button appearance="primary" disabled={props.busy} onClick={() => props.onCreateRest?.()}>
            {finishLabel(rest.length)}
          </Button>
        </div>
      )}
      {a?.error && <MessageBar intent="error" layout="multiline"><MessageBarBody>{a.error}{a.hint ? ` ${a.hint}` : ""}</MessageBarBody></MessageBar>}
      {shared.map((e) => (
        <MessageBar key={e.error} intent="error" layout="multiline" data-ed2="shared-error">
          <MessageBarBody>{`${e.labels.join(", ")}: ${e.error}${e.hint ? ` ${e.hint}` : ""}`}</MessageBarBody>
        </MessageBar>
      ))}
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
      {/* n229: after every Create, and on reopening: read back what was built and compare it with the dry run, by rules */}
      {!live && <VerifyButton built={props.outputs.created.length} busy={props.busy} />}
      {stored && <ProductView product={stored} onOpen={props.onOpen} cards={a?.outputs} onCleanUp={props.onCleanUp} busy={props.busy} />}
      {a?.flow && <FlowView flow={a.flow} mascotsOn={false} idPrefix="kg-flow-result" />}
      {a ? (
        a.outputs.map((c) => (
          <OutputCard key={c.output} card={c} onOpen={props.onOpen} onUpdate={props.onUpdate} onNewName={props.onNewName} busy={props.busy}
            onRetry={props.onRetry} shared={shared} {...appOf(props.outputs, c)} />
        ))
      ) : (
        <section>
          <Subtitle2>Created items</Subtitle2>
          <div className="krusgraph-actions">
            {earlier.map((l) => (
              <React.Fragment key={l.item.id}>
                <Button appearance="primary" icon={<Open24Regular />} onClick={() => props.onOpen(l.item)}>
                  Open in Fabric: {l.label}
                </Button>
                <RunNow item={l.item} />
              </React.Fragment>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
