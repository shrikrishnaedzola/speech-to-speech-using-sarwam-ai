// Section 4: tester ratings (editable here), optional automatic MOS, audio issues from the logs.

import { useEffect, useState } from "react";
import { Badge, Empty, Section, Stat } from "./ui";

export const RATING_FIELDS = [
  ["naturalness", "Naturalness"],
  ["clarity", "Clarity"],
  ["pronunciation", "Pronunciation"],
  ["accent_fit", "Accent fit for the language"],
  ["politeness", "Politeness / tone"],
  ["code_mixing", "Code-mixing handling (Hinglish etc.)"],
];

const ISSUE_LABEL = {
  long_silence: "Long silence",
  talk_over: "Talking over",
  cut_off: "Cut-off sentence",
  repeated_phrase: "Repeated phrase",
};

export default function VoiceQuality({ report, onSaveRatings, saving }) {
  const vq = report.voice_quality;
  const [ratings, setRatings] = useState(vq.ratings);
  useEffect(() => {
    setRatings(vq.ratings);
  }, [vq.ratings]);
  const set = (key, value) => setRatings((r) => ({ ...r, [key]: value }));

  return (
    <Section number={4} title="Voice quality">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Tester rating (avg)" value={vq.rating_average != null ? `${vq.rating_average.toFixed(1)} / 5` : "not rated"} />
        <Stat label="Auto MOS overall" value={vq.mos ? `${vq.mos.ovrl.toFixed(2)} / 5` : "-"} sub={vq.mos ? vq.mos.model : `MOS: ${vq.mos_status}`} />
        {vq.mos && <Stat label="MOS signal / noise" value={`${vq.mos.sig.toFixed(2)} / ${vq.mos.bak.toFixed(2)}`} sub="SIG / BAK" />}
        <Stat label="Audio issues" value={vq.issues.length} />
      </div>

      <form
        className="no-print mt-4 rounded-lg border border-slate-200 p-3 dark:border-slate-800"
        onSubmit={(e) => {
          e.preventDefault();
          onSaveRatings(ratings);
        }}
      >
        <p className="mb-2 text-sm font-medium">Tester ratings (1 = poor, 5 = excellent)</p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {RATING_FIELDS.map(([key, label]) => (
            <fieldset key={key} className="flex items-center justify-between gap-2 text-sm">
              <legend className="sr-only">{label}</legend>
              <span>{label}</span>
              <span className="flex gap-1">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    type="button"
                    aria-label={`${label}: ${n}`}
                    aria-pressed={ratings[key] === n}
                    onClick={() => set(key, ratings[key] === n ? null : n)}
                    className={`h-7 w-7 rounded text-xs font-semibold ${
                      ratings[key] === n
                        ? "bg-emerald-600 text-white"
                        : "border border-slate-300 dark:border-slate-700"
                    }`}
                  >
                    {n}
                  </button>
                ))}
              </span>
            </fieldset>
          ))}
        </div>
        <textarea
          className="mt-2 w-full rounded border border-slate-300 bg-white p-2 text-sm dark:border-slate-700 dark:bg-slate-800"
          rows={2}
          placeholder="Notes (optional, no personal data)"
          value={ratings.notes ?? ""}
          onChange={(e) => set("notes", e.target.value)}
        />
        <button type="submit" disabled={saving}
          className="mt-2 rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50">
          {saving ? "Saving…" : "Save ratings & regenerate report"}
        </button>
      </form>
      {vq.ratings.notes && <p className="mt-2 text-sm"><span className="text-slate-500">Tester notes:</span> {vq.ratings.notes}</p>}

      <h3 className="mt-4 text-sm font-semibold">Audio issues (from logs)</h3>
      {vq.issues.length === 0 ? (
        <Empty>No long silences, overlaps, cut-offs or repeated phrases found.</Empty>
      ) : (
        <ul className="mt-1 space-y-1 text-sm">
          {vq.issues.map((i, n) => (
            <li key={n} className="flex gap-2">
              <span className="w-12 shrink-0 tabular-nums text-slate-500">{i.time ?? "-"}</span>
              <Badge tone="warn">{ISSUE_LABEL[i.kind]}</Badge>
              <span>{i.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
