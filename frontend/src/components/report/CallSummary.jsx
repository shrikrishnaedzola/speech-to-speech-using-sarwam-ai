// Section 1: who/what/when, overall score, verdict, strengths and problems.

import { Badge, Section, verdictTone } from "./ui";

const SECTION_LABELS = {
  accuracy: "Accuracy",
  mishearings: "Mishearings",
  latency: "Latency",
  voice_quality: "Voice quality",
  language: "Language support",
  cost: "Cost",
};

export default function CallSummary({ report }) {
  const { call, summary } = report;
  const started = new Date(call.started_at);
  return (
    <Section number={1} title="Call summary">
      <div className="flex flex-wrap items-start gap-6">
        <div className="text-center">
          <div className="text-5xl font-bold tabular-nums">{Math.round(summary.overall_score)}</div>
          <div className="text-xs text-slate-500">out of 100</div>
          <div className="mt-1">
            <Badge tone={verdictTone(summary.verdict)}>{summary.verdict}</Badge>
          </div>
        </div>
        <dl className="grid flex-1 grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
          {[
            ["Provider", call.provider],
            ["Model", call.model],
            ["Voice", call.voice ?? "-"],
            ["Language", call.language_selected],
            ["Audio", call.audio_mode === "phone_8khz" ? "Phone 8 kHz" : "Normal"],
            ["Duration", `${Math.round(call.duration_s)} s`],
            ["Date", started.toLocaleString()],
            ["Mode", call.mode],
            ["Form", call.form_name ?? "-"],
          ].map(([k, v]) => (
            <div key={k}>
              <dt className="text-[11px] text-slate-500">{k}</dt>
              <dd className="font-medium break-words">{v}</dd>
            </div>
          ))}
        </dl>
      </div>

      {/* Section scores as small meters (number always shown next to the bar) */}
      <div className="mt-4 grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
        {Object.entries(summary.section_scores).map(([key, score]) => (
          <div key={key} className="flex items-center gap-2 text-sm">
            <span className="w-32 shrink-0">{SECTION_LABELS[key]}</span>
            <div className="h-2 flex-1 rounded bg-slate-100 dark:bg-slate-800">
              {score != null && <div className="h-2 rounded" style={{ width: `${score}%`, background: "var(--rep-stt)" }} />}
            </div>
            <span className="w-24 text-right tabular-nums text-xs">
              {score == null ? "no data" : `${Math.round(score)}`}
              {summary.weights_used[key] != null && <span className="text-slate-500"> · {summary.weights_used[key]}%</span>}
            </span>
          </div>
        ))}
      </div>
      {summary.missing_sections.length > 0 && (
        <p className="mt-2 text-xs text-slate-500">
          Not in the score (no data yet): {summary.missing_sections.map((k) => SECTION_LABELS[k]).join(", ")}. Their weight
          was shared among the other sections.
        </p>
      )}

      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <h3 className="text-sm font-semibold text-emerald-700 dark:text-emerald-400">Key strengths</h3>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
            {summary.strengths.length ? summary.strengths.map((s) => <li key={s}>{s}</li>) : <li>None found.</li>}
          </ul>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-red-700 dark:text-red-400">Key problems</h3>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
            {summary.problems.length ? summary.problems.map((s) => <li key={s}>{s}</li>) : <li>None found.</li>}
          </ul>
        </div>
      </div>
    </Section>
  );
}
