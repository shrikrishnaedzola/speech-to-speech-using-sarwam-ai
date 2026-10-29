// Column 2: live form cards, tester review (Correct / Wrong + expected value), export.

import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Button, Panel, formatValue } from "./ui";

const BADGES = {
  pending: { label: "Pending", cls: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200" },
  filled: { label: "Filled", cls: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200" },
  needs_confirmation: { label: "Needs confirmation", cls: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200" },
  skipped: { label: "Skipped", cls: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400" },
};

const pct = (v) => (v === null || v === undefined ? "-" : `${Math.round(v * 100)}%`);

export default function FormPanel({ callId, formState, report }) {
  const fields = formState?.fields ?? [];
  const visible = fields.filter((f) => f.visible);
  const hiddenCount = fields.length - visible.length;
  const m = report?.metrics;

  const exportLinks = callId && (
    <div className="flex flex-wrap gap-1">
      <a href={api.exportUrl(callId, "json")}><Button>Export JSON</Button></a>
      <a href={api.exportUrl(callId, "csv")}><Button>Export CSV</Button></a>
      <a href={api.exportUrl(callId, "csv", "turns")} title="One row per turn with STT/LLM/TTS timings">
        <Button>Turns CSV</Button>
      </a>
    </div>
  );

  return (
    <Panel title="2 · Form Data (live)" actions={exportLinks}>
      {!formState ? (
        <p className="text-sm text-slate-500">Start a call or a simulation to see the form fill up.</p>
      ) : (
        <>
          <div className="mb-3 grid grid-cols-2 gap-2 text-sm">
            <Score label="Accuracy" value={pct(m?.accuracy)}
              detail={m ? `${m.correct_fields}/${m.reviewed_fields} reviewed fields correct` : ""} />
            <Score label="Completion" value={pct(m?.completion)}
              detail={m ? `${m.required_filled}/${m.required_total} required fields filled` : ""} />
          </div>
          {formState.completed && (
            <p className="mb-2 rounded-md bg-emerald-50 p-2 text-sm text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">
              complete_form succeeded - all required answers saved.
            </p>
          )}
          <div className="flex flex-col gap-2">
            {visible.map((f) => (
              <FieldCard key={f.id} field={f} callId={callId} />
            ))}
          </div>
          {hiddenCount > 0 && (
            <p className="mt-2 text-xs text-slate-500">
              {hiddenCount} follow-up question(s) hidden - their condition is not met (yet).
            </p>
          )}
        </>
      )}
    </Panel>
  );
}

function Score({ label, value, detail }) {
  return (
    <div className="rounded-lg bg-slate-50 p-2 dark:bg-slate-950">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-xl font-semibold">{value}</div>
      <div className="text-[11px] text-slate-500">{detail}</div>
    </div>
  );
}

function FieldCard({ field, callId }) {
  const badge = BADGES[field.status] ?? BADGES.pending;
  const hasValue = field.status === "filled" || field.status === "needs_confirmation";
  const verdict = field.review?.verdict ?? null;
  const [expected, setExpected] = useState(field.review?.expected_value ?? "");
  useEffect(() => {
    setExpected(field.review?.expected_value ?? "");
  }, [field.review?.expected_value]);

  async function saveReview(newVerdict, newExpected = expected) {
    await api.review(callId, [{ field_id: field.id, verdict: newVerdict, expected_value: newExpected || null }]);
  }

  // Save the expected value shortly after typing stops. Typing one implies "Wrong".
  const saveTimer = useRef(null);
  function onExpectedChange(text) {
    setExpected(text);
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => saveReview(verdict ?? "wrong", text), 600);
  }

  return (
    <div className={`rounded-lg border p-3 transition-colors ${hasValue ? "border-emerald-300 dark:border-emerald-800" : "border-slate-200 dark:border-slate-800"}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-medium">
            {field.label}
            {field.required && <span className="text-red-600" title="Required"> *</span>}
            {field.conditional && <span className="ml-1 text-[11px] text-slate-500">(follow-up)</span>}
          </div>
          <div className="font-mono text-[11px] text-slate-500">{field.id}</div>
        </div>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${badge.cls}`}>{badge.label}</span>
      </div>

      {hasValue && <div className="mt-1 text-base font-semibold break-words">{formatValue(field.value)}</div>}
      <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-slate-500">
        {field.confidence === "low" && <span className="text-amber-700 dark:text-amber-400">low confidence</span>}
        {field.attempts > 1 && <span>{field.attempts} save attempts</span>}
      </div>
      {field.note && <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">{field.note}</p>}

      {hasValue && callId && (
        <div className="mt-2 flex flex-wrap items-center gap-1">
          <button
            onClick={() => saveReview(verdict === "correct" ? null : "correct")}
            className={`rounded px-2 py-0.5 text-xs font-medium ${verdict === "correct" ? "bg-emerald-600 text-white" : "border border-slate-300 dark:border-slate-700"}`}
            aria-pressed={verdict === "correct"}
          >
            ✓ Correct
          </button>
          <button
            onClick={() => saveReview(verdict === "wrong" ? null : "wrong")}
            className={`rounded px-2 py-0.5 text-xs font-medium ${verdict === "wrong" ? "bg-red-600 text-white" : "border border-slate-300 dark:border-slate-700"}`}
            aria-pressed={verdict === "wrong"}
          >
            ✗ Wrong
          </button>
          <input
            className="min-w-0 flex-1 rounded border border-slate-300 bg-white px-2 py-0.5 text-xs dark:border-slate-700 dark:bg-slate-800"
            placeholder="Expected value"
            value={expected}
            onChange={(e) => onExpectedChange(e.target.value)}
          />
        </div>
      )}
    </div>
  );
}
