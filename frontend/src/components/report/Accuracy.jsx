// Section 7: form-data accuracy, completion, follow-ups, error recovery, tool calls, field table.

import { Badge, Section, Stat, Table, pct } from "./ui";

export default function Accuracy({ report }) {
  const a = report.accuracy;
  return (
    <Section number={7} title="Accuracy (form data)">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Field accuracy" value={pct(a.field_accuracy)} sub={`${a.correct} of ${a.reviewed} checked fields`} />
        <Stat label="Completion" value={pct(a.completion)} sub={`${a.required_filled} of ${a.required_total} required`} />
        <Stat label="Follow-ups correct" value={a.followups_total ? `${a.followups_correct} / ${a.followups_total}` : "-"} />
        <Stat label="Invalid answers fixed" value={`${a.invalid_answers_fixed} / ${a.invalid_answers}`} sub={`${a.corrections_saved} correction(s) saved`} />
        <Stat label="Tool calls" value={a.tool_calls_total} sub={`success ${pct(a.tool_success_rate)}`} />
        <Stat label="Invalid tool calls" value={a.invalid_tool_calls} sub="bad JSON arguments" />
        <Stat label="Validation errors" value={a.validation_errors} sub="answers rejected by backend" />
      </div>
      {a.followup_issues.length > 0 && (
        <ul className="mt-3 list-disc pl-5 text-sm text-red-700 dark:text-red-400">
          {a.followup_issues.map((t) => <li key={t}>{t}</li>)}
        </ul>
      )}
      <div className="mt-3">
        <Table
          head={["Field", "Expected", "Saved", "Correct?", "Notes"]}
          rows={a.table.map((r) => [
            r.label, r.expected ?? "-", r.saved ?? "-",
            r.correct == null ? <Badge>not checked</Badge> : r.correct ? <Badge tone="good">Correct</Badge> : <Badge tone="bad">Wrong</Badge>,
            <span className="text-xs text-slate-500">{r.notes}</span>,
          ])}
        />
      </div>
    </Section>
  );
}
