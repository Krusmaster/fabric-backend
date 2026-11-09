/**
 * n185: the pipeline's Run once and Schedule, and the data agent's layer, Publish and Microsoft 365 Copilot: the ticks
 * under "Choose what to build", and what the dry run and Create say on the cards. Words come from jobsWords.ts and the
 * engine's answers; nothing here calls Fabric.
 */
import React from "react";
import { Body1, Caption1, Checkbox, Dropdown, Field, Input, Link, MessageBar, MessageBarBody, Option, Radio, RadioGroup, Subtitle2 } from "@fluentui/react-components";
import { AgentOptions, BuildCard, JobsCard, PipelineJobs } from "./engineClient";
import {
  LAYER_LABEL, TIME_ZONES, activityLines, defaultSchedule, runHeadline, scheduleProblems, scheduleWords, withPublish,
} from "./jobsWords";

function Steps(props: { items?: string[]; label: string }) {
  if (!props.items?.length) return null;
  return (
    <ol className="krusgraph-steps" aria-label={props.label}>
      {props.items.map((s) => (
        <li key={s}>{s}</li>
      ))}
    </ol>
  );
}

/** Without DataPipeline.Execute.All: why, the Entra steps, the Cloud Shell line, the consent note and the manual steps. */
export function JobsBlocked(props: { permission: JobsCard["permission"] }) {
  const p = props.permission;
  return (
    <MessageBar intent="warning" layout="multiline" aria-label="Run and schedule need a permission">
      <MessageBarBody>
        {p.why}
        <Steps items={p.entra_steps} label="Steps in Entra" />
        {p.az && <code className="krusgraph-code">{p.az}</code>}
        {p.consent_note && <div>{p.consent_note}</div>}
        <div>Until then, in Fabric:</div>
        <Steps items={p.manual} label="In Fabric" />
      </MessageBarBody>
    </MessageBar>
  );
}

/** Under the pipeline in "Choose what to build": Run once and Schedule, both off; disabled without the permission. */
export function PipelineChoices(props: { jobs: PipelineJobs; onChange: (j: PipelineJobs) => void; blocked?: JobsCard["permission"] }) {
  const j = props.jobs;
  const s = j.schedule;
  const off = !!props.blocked;
  const setS = (patch: Partial<NonNullable<PipelineJobs["schedule"]>>) => props.onChange({ ...j, schedule: { ...(s ?? defaultSchedule()), ...patch } });
  return (
    <fieldset className="krusgraph-output" aria-label="Run and schedule">
      <legend>Run and schedule (both off: Krusgraph runs and schedules nothing)</legend>
      {off && props.blocked && <JobsBlocked permission={props.blocked} />}
      <Checkbox label="Run once after Create (silver, then gold, then the check)" checked={j.run_once} disabled={off}
        onChange={(_, d) => props.onChange({ ...j, run_once: !!d.checked })} />
      <Checkbox label="Schedule" checked={!!s} disabled={off} onChange={(_, d) => props.onChange({ ...j, schedule: d.checked ? defaultSchedule() : null })} />
      {s && !off && (
        <div className="krusgraph-schedule">
          <RadioGroup layout="horizontal" value={s.every} onChange={(_, d) => setS({ every: d.value as "day" | "hours", ...(d.value === "hours" && !s.hours ? { hours: 4 } : {}) })}>
            <Radio value="day" label="Daily" />
            <Radio value="hours" label="Every N hours" />
          </RadioGroup>
          {s.every === "hours" && (
            <Field label="Every (hours)">
              <Input type="number" min={1} max={24} value={String(s.hours ?? 4)} onChange={(_, d) => setS({ hours: Number(d.value) })} />
            </Field>
          )}
          <Field label={s.every === "day" ? "At" : "From"}>
            <Input type="time" value={s.at} onChange={(_, d) => setS({ at: d.value })} />
          </Field>
          <Field label="Time zone">
            <Dropdown value={s.time_zone} selectedOptions={[s.time_zone]} onOptionSelect={(_, d) => setS({ time_zone: d.optionValue ?? s.time_zone })}>
              {TIME_ZONES.map((z) => (
                <Option key={z} value={z}>{z}</Option>
              ))}
            </Dropdown>
          </Field>
          <Field label="Start date" hint="Empty: tomorrow">
            <Input type="date" value={s.start ?? ""} onChange={(_, d) => setS({ start: d.value || undefined })} />
          </Field>
          <Caption1>{`The pipeline runs ${scheduleWords(s)}. A schedule this item made is updated; others are left alone.`}</Caption1>
          {scheduleProblems(s).map((p) => (
            <MessageBar key={p} intent="warning"><MessageBarBody>{p}</MessageBarBody></MessageBar>
          ))}
        </div>
      )}
    </fieldset>
  );
}

/** Under the data agent: the layer it reads, Publish in Fabric, and Microsoft 365 Copilot (only with Publish). */
export function AgentChoices(props: { agent: AgentOptions; onChange: (a: AgentOptions) => void }) {
  const a = props.agent;
  return (
    <fieldset className="krusgraph-output" aria-label="Data agent: layer and publishing">
      <legend>What the agent reads, and publishing (both off: a draft only you see)</legend>
      <RadioGroup value={a.layer} onChange={(_, d) => props.onChange({ ...a, layer: d.value as AgentOptions["layer"] })}>
        {(["silver", "gold", "source"] as const).map((l) => (
          <Radio key={l} value={l} label={LAYER_LABEL[l]} />
        ))}
      </RadioGroup>
      <Caption1>One layer only: silver or gold when they are in the lakehouse, otherwise the source tables; never two copies of a table.</Caption1>
      <Checkbox label="Publish the agent in Fabric" checked={a.publish} onChange={(_, d) => props.onChange(withPublish(a, !!d.checked))} />
      <Checkbox label="Also make it available in Microsoft 365 Copilot" checked={a.copilot} disabled={!a.publish}
        onChange={(_, d) => props.onChange({ ...a, copilot: !!d.checked })} />
      <Caption1>Microsoft 365 Copilot needs a paid capacity (F2 or higher), tenant settings and licences; the preview checks them.</Caption1>
    </fieldset>
  );
}

/** The pipeline card: what Create will do (dry run) or did, the run per step with durations and a link, the schedule. */
export function JobsPanel(props: { card: BuildCard }) {
  const j = props.card.jobs;
  if (!j) return null;
  const run = j.run;
  const sched = j.schedule_result;
  return (
    <div aria-label="Run and schedule">
      {j.permission.granted === false && (j.run_once || j.schedule) && <JobsBlocked permission={j.permission} />}
      <ul className="krusgraph-list">
        {j.words.map((w) => (
          <li key={w}><Body1>{w}</Body1></li>
        ))}
      </ul>
      {run && (() => {
        const h = runHeadline(run);
        const lines = activityLines(run);
        return (
          <MessageBar intent={h.tone === "danger" ? "error" : h.tone} layout="multiline" aria-label="The run">
            <MessageBarBody>
              {h.text}
              {lines.length > 0 && (
                <ul className="krusgraph-list" aria-label="Steps of the run">
                  {lines.map((l) => (
                    <li key={l}>{l}</li>
                  ))}
                </ul>
              )}
              {run.links?.run && <div><Link href={run.links.run} target="_blank">Open the run in Fabric</Link></div>}
              {run.manual && <Steps items={run.manual} label="In Fabric" />}
            </MessageBarBody>
          </MessageBar>
        );
      })()}
      {sched && (
        <MessageBar intent={sched.status === "Succeeded" ? "success" : "warning"} layout="multiline" aria-label="The schedule">
          <MessageBarBody>
            {sched.status === "Succeeded"
              ? `Schedule ${sched.mode}: next run ${sched.next_run_words ?? sched.next_run}. ${sched.note ?? ""}`
              : `The schedule was not set: ${sched.why ?? "Fabric refused it"}.`}
          </MessageBarBody>
        </MessageBar>
      )}
    </div>
  );
}

/** The data agent card: the layer it reads, its examples as Fabric holds them, publishing and the Copilot preflight. */
export function AgentPanel(props: { card: BuildCard }) {
  const a = props.card.agent;
  if (!a) return null;
  const pf = a.copilot_preflight;
  const ex = a.examples;
  return (
    <div aria-label="Data agent: layer and publishing">
      <Body1>{a.selection?.words ?? a.layer_words}</Body1>
      {ex && ex.status === "read" && (
        <Caption1>
          {`Examples in Fabric: ${ex.valid ?? 0} valid, ${ex.invalid ?? 0} invalid, ${ex.validating ?? 0} still being checked.`}
        </Caption1>
      )}
      {(ex?.invalid_examples ?? []).length > 0 && (
        <ul className="krusgraph-list" aria-label="Invalid examples">
          {(ex?.invalid_examples ?? []).map((x) => (
            <li key={x.question}>{`${x.question}: ${x.reason ?? "invalid"}`}</li>
          ))}
        </ul>
      )}
      <Caption1>{a.where_examples}</Caption1>
      <ul className="krusgraph-list">
        {(a.words ?? []).map((w) => (
          <li key={w}><Body1>{w}</Body1></li>
        ))}
      </ul>
      {pf && (
        <>
          <Subtitle2>Microsoft 365 Copilot</Subtitle2>
          <Body1>{pf.words}</Body1>
          <ul className="krusgraph-list" aria-label="Microsoft 365 Copilot requirements">
            {pf.requirements.map((r) => (
              <li key={r.requirement}>
                {`${r.status === "ok" ? "OK" : r.status === "missing" ? "Missing" : "Unverified"}: ${r.requirement} (${r.detail}). `}
                <Link href={r.doc} target="_blank">Microsoft's page</Link>
              </li>
            ))}
          </ul>
          <Caption1>{pf.step}</Caption1>
        </>
      )}
    </div>
  );
}
