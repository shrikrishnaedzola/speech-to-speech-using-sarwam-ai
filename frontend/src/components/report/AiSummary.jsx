// Section 10: optional AI-written summary, clearly labelled.

import { Section } from "./ui";

export default function AiSummary({ report }) {
  const s = report.ai_summary;
  return (
    <Section number={10} title="AI-written summary">
      {s.status === "off" && <p className="text-sm text-slate-500">Off. Turn it on in report settings (needs ANTHROPIC_API_KEY on the backend).</p>}
      {s.status === "error" && <p className="text-sm text-red-600">Could not write the summary: {s.text}</p>}
      {(s.status === "ok" || s.status === "flagged") && (
        <div className="rounded-lg border border-dashed border-slate-300 p-3 dark:border-slate-700">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">{s.label}</p>
          {s.status === "flagged" && (
            <p className="mb-2 rounded bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950 dark:text-red-300">
              Warning: these numbers in the summary were not found in the report data: {s.unverified_numbers.join(", ")}.
              Do not use this summary without checking it.
            </p>
          )}
          <p className="whitespace-pre-line text-sm">{s.text}</p>
          {s.model && <p className="mt-2 text-[11px] text-slate-500">Model: {s.model}</p>}
        </div>
      )}
    </Section>
  );
}
