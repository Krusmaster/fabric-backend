/**
 * The five views of the Krusgraph Model editor: empty state, review, choose outputs, preview (dry run), result.
 * Copy follows the site: plain words, numbers only from the engine's answers, no claims about speed or compliance.
 * n173: the review shows the map (the MCP Apps cards' drawing, cardMap.ts) or the list, each row's check state
 * (green passed, red failed with its orphans or duplicates, grey not checked), Onto, Thinker and Builder in their own
 * colours with the site's figures, Thinker's questions with their choices inline, and Accept all. Words: modelWords.ts.
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Badge,
  Body1,
  Button,
  Caption1,
  Checkbox,
  Field,
  Input,
  MessageBar,
  MessageBarBody,
  Spinner,
  Subtitle2,
  Switch,
  Tab,
  TabList,
  Title3,
  Tooltip,
} from "@fluentui/react-components";
import { CheckmarkStarburst24Regular } from "@fluentui/react-icons";
import { ItemEditorEmptyView } from "../../components/ItemEditor";
import { BuildAnswer, EngineError } from "./engineClient";
import { ReviewFile, ReviewItem, ReviewStatus, SourceDefinition, sortForReview } from "./ModelItemDefinition";
import { MapData, drawPlanMap, overlay } from "./cardMap";
import { MAP_CSS, MASCOT_COLOURS, MASCOT_CSS, MASCOT_GLAD, MASCOT_NAMES, MASCOT_SVG } from "./cardMap.generated";
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

export function EmptyView(props: {
  source?: SourceDefinition;
  schema: string;
  onSchemaChange: (schema: string) => void;
  onChooseLakehouse: () => void;
  onReview: () => void;
}) {
  const { source } = props;
  return (
    <ItemEditorEmptyView
      title="Choose a lakehouse"
      description={
        "Krusgraph reads the table and column names of a lakehouse in this workspace and proposes keys and " +
        "relationships, each with the rule that found it. Nothing is created until you choose Create."
      }
      imageSrc="/assets/items/ModelItem/EditorEmpty.svg"
      imageAlt=""
      customContent={
        <div className="krusgraph-empty-form">
          <Button appearance={source ? "secondary" : "primary"} onClick={props.onChooseLakehouse}>
            {source ? `Lakehouse: ${source.displayName}` : "Choose lakehouse"}
          </Button>
          <Field label="Schema" hint="dbo unless the lakehouse was created with schemas">
            <Input value={props.schema} onChange={(_, d) => props.onSchemaChange(d.value)} />
          </Field>
          <Button appearance="primary" disabled={!source || !props.schema.trim()} onClick={props.onReview}>
            Find keys and relationships
          </Button>
        </div>
      }
    />
  );
}

// ------------------------------------------------------------------ the mascots (n173) -----------------------------

/** One mascot with its bubble. The figure is the site's (cardMap.generated.ts, from fabric_backend/mcp_apps_mascots.py),
 * decorative (aria-hidden); the sentence is the bubble's text. Glad poses only when a check passed (MASCOT_GLAD). */
export function MascotSays(props: { kind: MascotKind; text?: string; pose?: string; glad?: boolean; children?: React.ReactNode }) {
  if (!props.text && !props.children) return null;
  let pose = props.pose ?? "rest";
  if (!props.glad && MASCOT_GLAD.includes(pose)) pose = "explain";
  const figure = MASCOT_SVG[props.kind].replace('data-pose="rest"', `data-pose="${pose}"`);
  return (
    <li className={`krusgraph-say krusgraph-say-${props.kind}${props.glad ? " glad" : ""}`} data-mascot={props.kind}
      style={{ ["--kg-mascot" as string]: MASCOT_COLOURS[props.kind].fill }}>
      <span className="krusgraph-fig" dangerouslySetInnerHTML={{ __html: figure }} />
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

function ReviewRow(props: { item: ReviewItem; onDecide: (id: string, status: ReviewStatus) => void }) {
  const { item } = props;
  const st = checkState(item);
  return (
    <li className={`krusgraph-row krusgraph-row-${item.review} krusgraph-check-${st}`} data-id={item.id} data-check={st}>
      <RulePill rule={item.rule} />
      <div className="krusgraph-row-what">
        <Body1>{itemText(item)}</Body1>
        <Caption1 className="krusgraph-row-check">{checkText(item)}</Caption1>
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
}) {
  const [tab, setTab] = useState<"map" | "list">("map");
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
      {tab === "map" ? (
        <PlanMap map={props.map} review={props.review} />
      ) : (
        <section aria-label="Keys and links">
          <ul className="krusgraph-list">
            {items.map((it) => (
              <ReviewRow key={it.id} item={it} onDecide={props.onDecide} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ 3. choose outputs -------------------------------

export const LATER_OUTPUTS = ["Semantic model", "Report", "Pipeline", "Ontology", "Data agent"];

export function OutputsView(props: { name: string; onNameChange: (name: string) => void; onPreview: () => void }) {
  const valid = /^[A-Za-z0-9_]{1,123}$/.test(props.name);
  return (
    <div className="krusgraph-view">
      <Title3>Choose what to build</Title3>
      <Checkbox checked disabled label="API for GraphQL" />
      <Field label="Name of the API" validationMessage={valid ? undefined : "Letters, digits and underscores only"}
        validationState={valid ? "none" : "error"}>
        <Input value={props.name} onChange={(_, d) => props.onNameChange(d.value)} />
      </Field>
      {LATER_OUTPUTS.map((label) => (
        <Checkbox key={label} disabled label={`${label} (later)`} />
      ))}
      <div>
        <Button appearance="primary" disabled={!valid} onClick={props.onPreview}>
          Preview
        </Button>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ 4. preview (dry run) ----------------------------

export function PreviewView(props: { answer: BuildAnswer; onCreate: () => void; mascotsOn: boolean }) {
  const a = props.answer;
  const changes = Object.entries(a.changes ?? {}).filter(([, v]) => Array.isArray(v) && v.length > 0);
  const checkLine = dryRunCheckLine(a.row_check);
  const builder = `This is the dry run: nothing exists yet. Choose Create to ${a.would === "update" ? "update" : "make"} ${a.name} in Fabric.`;
  const checked = !!a.row_check?.checked;
  const failed = checked ? a.row_check.keys.failed + a.row_check.relationships.failed : 0;
  return (
    <div className="krusgraph-view">
      <Title3>
        Dry run: {a.would === "update" ? "update" : "create"} {a.name}
      </Title3>
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
      {changes.length > 0 && (
        <section>
          <Subtitle2>What changes</Subtitle2>
          <ul className="krusgraph-list">
            {changes.map(([k, v]) => (
              <li key={k}>
                <Body1>
                  {k.charAt(0).toUpperCase() + k.slice(1).replace(/_/g, " ")}: {v.length}
                </Body1>
              </li>
            ))}
          </ul>
        </section>
      )}
      {(a.checks_passed ?? []).length > 0 && (
        <section>
          <Subtitle2>Checks that passed</Subtitle2>
          <ul className="krusgraph-list">
            {a.checks_passed.map((c) => (
              <li key={c}>
                <Body1>{c}</Body1>
              </li>
            ))}
          </ul>
        </section>
      )}
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
        <Button appearance="primary" onClick={props.onCreate}>
          Create
        </Button>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ 5. result ----------------------------------------

export function ResultView(props: { answer: BuildAnswer; onOpen: () => void; mascotsOn: boolean }) {
  const a = props.answer;
  const said = `${a.created?.[0]?.name ?? "The API"} is in Fabric now. Open it there to run a query.`;
  return (
    <div className="krusgraph-view">
      <Title3>API for GraphQL: {a.created?.[0]?.name}</Title3>
      {props.mascotsOn ? (
        <ul className="krusgraph-mascots">
          <style>{MASCOT_CSS}</style>
          <MascotSays kind="builder" text={said} pose="point" />
        </ul>
      ) : (
        <Body1>{said}</Body1>
      )}
      {a.endpoint && (
        <Field label="GraphQL endpoint">
          <Input readOnly value={a.endpoint} />
        </Field>
      )}
      <section>
        <Subtitle2>Created items</Subtitle2>
        <ul className="krusgraph-list">
          {(a.created ?? []).map((c) => (
            <li key={c.id}>
              <Body1>
                {c.type === "GraphQLApi" ? "API for GraphQL" : c.type} {c.name}
              </Body1>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <Subtitle2>Still to do in the Fabric portal</Subtitle2>
        <ul className="krusgraph-list">
          {(a.portal_steps ?? []).map((s) => (
            <li key={s}>
              <Body1>{s}</Body1>
            </li>
          ))}
        </ul>
      </section>
      <div>
        <Button appearance="primary" onClick={props.onOpen}>
          Open item
        </Button>
      </div>
    </div>
  );
}
