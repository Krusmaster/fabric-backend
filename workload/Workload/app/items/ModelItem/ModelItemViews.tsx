/**
 * The five views of the Krusgraph Model editor: empty state, review, choose outputs, preview (dry run), result.
 * Copy follows the site: plain words, numbers only from the engine's answers, no claims about speed or compliance.
 */
import React from "react";
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
  Title3,
} from "@fluentui/react-components";
import { ItemEditorEmptyView } from "../../components/ItemEditor";
import { BuildAnswer, EngineError } from "./engineClient";
import {
  ReviewFile,
  ReviewItem,
  ReviewStatus,
  SourceDefinition,
  counts,
  describe,
  rulePill,
  sortForReview,
} from "./ModelItemDefinition";
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

// ------------------------------------------------------------------ 2. review ---------------------------------------

const STATUS_LABEL: Record<ReviewStatus, string> = {
  open: "Open",
  proposed: "Proposed",
  accepted: "Accepted",
  rejected: "Rejected",
};

function ReviewRow(props: { item: ReviewItem; onDecide: (id: string, status: ReviewStatus) => void }) {
  const { item } = props;
  const pill = rulePill(item);
  return (
    <li className={`krusgraph-row krusgraph-row-${item.review}`}>
      <Badge appearance="tint" color={pill === "K" ? "brand" : "informative"} title={`Rule ${item.rule}`}>
        {pill} {item.rule}
      </Badge>
      <Body1 className="krusgraph-row-what">{describe(item)}</Body1>
      <Caption1 className="krusgraph-row-status">{STATUS_LABEL[item.review]}</Caption1>
      <Button size="small" appearance={item.review === "accepted" ? "primary" : "secondary"}
        onClick={() => props.onDecide(item.id, "accepted")}>
        Accept
      </Button>
      <Button size="small" appearance={item.review === "rejected" ? "primary" : "secondary"}
        onClick={() => props.onDecide(item.id, "rejected")}>
        Reject
      </Button>
    </li>
  );
}

export function ReviewView(props: {
  source: SourceDefinition;
  review: ReviewFile;
  summary?: string;
  attention?: string[];
  onDecide: (id: string, status: ReviewStatus) => void;
}) {
  const c = counts(props.review);
  const items = sortForReview(props.review.items);
  const questions = props.review.open_questions ?? [];
  return (
    <div className="krusgraph-view">
      <Title3>
        {props.source.displayName} / {props.source.schema}
      </Title3>
      <Body1>
        {c.keys} keys and {c.relationships} relationships: {c.open} open, {c.proposed} proposed, {c.accepted} accepted,{" "}
        {c.rejected} rejected. K pills are key rules, R pills relationship rules. A rejected item is left out of what
        you build.
      </Body1>
      {questions.length > 0 && (
        <section>
          <Subtitle2>Open questions ({questions.length})</Subtitle2>
          <ul className="krusgraph-list">
            {questions.map((q) => (
              <li key={q.about} className="krusgraph-question">
                <Body1>{q.question}</Body1>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section>
        <Subtitle2>Keys and relationships</Subtitle2>
        <ul className="krusgraph-list">
          {items.map((it) => (
            <ReviewRow key={it.id} item={it} onDecide={props.onDecide} />
          ))}
        </ul>
      </section>
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

export function PreviewView(props: { answer: BuildAnswer; onCreate: () => void }) {
  const a = props.answer;
  const changes = Object.entries(a.changes ?? {}).filter(([, v]) => Array.isArray(v) && v.length > 0);
  return (
    <div className="krusgraph-view">
      <Title3>
        Dry run: {a.would === "update" ? "update" : "create"} {a.name}
      </Title3>
      <Body1>{a.note}</Body1>
      {changes.length > 0 && (
        <section>
          <Subtitle2>What changes</Subtitle2>
          <ul className="krusgraph-list">
            {changes.map(([k, v]) => (
              <li key={k}>
                <Body1>
                  {k.replace(/_/g, " ")}: {v.length}
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
      {a.not_checked && <Caption1>Not checked: {a.not_checked}</Caption1>}
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

export function ResultView(props: { answer: BuildAnswer; onOpen: () => void }) {
  const a = props.answer;
  return (
    <div className="krusgraph-view">
      <Title3>API for GraphQL: {a.created?.[0]?.name}</Title3>
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
                {c.type} {c.name}: {c.id}
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
