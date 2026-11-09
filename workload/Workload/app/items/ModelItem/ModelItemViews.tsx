/**
 * The five views of the Krusgraph Model editor: empty state, review, choose outputs, preview (dry run), result.
 * n174: every output the MCP tools build (KINDS in buildWords.ts), one dry-run card each, the data product, the data flow
 * (FlowView.tsx), and the result with Open in Fabric and the portal steps left per item.
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
import { CheckmarkStarburst24Regular, Open24Regular } from "@fluentui/react-icons";
import { ItemEditorEmptyView } from "../../components/ItemEditor";
import { BuildCard, DataProduct, EngineError, ManyAnswer, SchemasAnswer } from "./engineClient";
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
  kindInfo,
  nameAction,
  openLinks,
  previewLine,
  resultLine,
  validName,
} from "./buildWords";
import { FlowView } from "./FlowView";
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
          {source && <SchemaChoice schema={props.schema} schemas={props.schemas} onSchemaChange={props.onSchemaChange} />}
          <Button appearance="primary" disabled={!source || !props.schema.trim() || props.schemas.loading} onClick={props.onReview}>
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
}) {
  const problems = choiceProblems(props.choices);
  const productOk = !props.product.on || /^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$/.test(props.product.name.trim());
  const set = (kind: string, patch: Partial<OutputChoice>) =>
    props.onChange(props.choices.map((c) => (c.type === kind ? { ...c, ...patch } : c)));
  return (
    <div className="krusgraph-view">
      <Title3>Choose what to build</Title3>
      <Body1>
        Each output is made by the same engine as the Krusgraph tools in Claude, from the keys and links you reviewed. Preview shows a
        dry run of each; nothing is created until you choose Create, and nothing is run or scheduled.
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
              <Checkbox checked={c.enabled} label={k.label} onChange={(_, d) => set(k.kind, { enabled: !!d.checked })} />
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
    </div>
  );
}

// ------------------------------------------------------------------ the cards, the product -------------------------

function Problem({ card }: { card: BuildCard }) {
  const p = cardProblem(card);
  if (!p) return null;
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

export function OutputCard(props: { card: BuildCard; onOpen?: (item: OpenLink["item"]) => void }) {
  const c = props.card;
  const facts = cardFacts(c);
  const links = openLinks(c.created ?? []);
  const refused = !!(c.refusal || c.answer?.error);
  return (
    <section className={`krusgraph-output${refused ? " refused" : ""}`} aria-label={cardTitle(c)} data-output={c.output}>
      <Subtitle2>{cardTitle(c)}</Subtitle2>
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
      {links.length > 0 && (
        <div className="krusgraph-actions">
          {links.map((l) => (
            <Button key={l.item.id} icon={<Open24Regular />} onClick={() => props.onOpen?.(l.item)}>
              Open in Fabric: {l.label}
            </Button>
          ))}
        </div>
      )}
      {(c.portal_steps ?? []).filter(Boolean).length > 0 && (
        <>
          <Caption1>Still to do in the Fabric portal</Caption1>
          <ul className="krusgraph-list">
            {(c.portal_steps ?? []).filter(Boolean).map((s) => (
              <li key={s}>
                <Body1>{s}</Body1>
              </li>
            ))}
          </ul>
        </>
      )}
      {c.status === "running" && <Spinner size="tiny" label="Creating in Fabric…" />}
      {c.already_built && <Body1>Already in the workspace from an earlier Create; nothing was written again.</Body1>}
      <PermissionsNote needs={c.permissions.needs} extra="No run or schedule permission is used." />
    </section>
  );
}

export function ProductView(props: {
  product: ProductDefinition | DataProduct;
  onOpen?: (item: OpenLink["item"]) => void;
  title?: string;
}) {
  const p = props.product;
  const items = p.items as (CreatedItem & { would?: string; output?: string })[];
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
              {kindInfo(x.output ?? "")?.label ?? x.type} {x.name}
              {x.would ? ` (${x.would === "update" ? "would be updated" : "would be created"})` : ""}
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

export function PreviewView(props: { answer: ManyAnswer; onCreate: () => void; mascotsOn: boolean; createLabel: string }) {
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
        <OutputCard key={c.output} card={c} />
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

export function ResultView(props: {
  answer?: ManyAnswer;
  outputs: OutputsDefinition;
  onOpen: (item: OpenLink["item"]) => void;
  mascotsOn: boolean;
}) {
  const a = props.answer;
  const said = a ? resultLine(a) : "This item built these before. Open each in Fabric; choose outputs again to update them.";
  const stored = props.outputs.product;
  const earlier = openLinks(props.outputs.created);
  return (
    <div className="krusgraph-view">
      <Title3>Built in Fabric</Title3>
      {props.mascotsOn ? (
        <ul className="krusgraph-mascots">
          <style>{MASCOT_CSS}</style>
          <MascotSays kind="builder" text={said} pose="point" glad={!!a && !a.refused} />
        </ul>
      ) : (
        <Body1>{said}</Body1>
      )}
      {stored && <ProductView product={stored} onOpen={props.onOpen} />}
      {a?.flow && <FlowView flow={a.flow} mascotsOn={false} idPrefix="kg-flow-result" />}
      {a ? (
        a.outputs.map((c) => <OutputCard key={c.output} card={c} onOpen={props.onOpen} />)
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
