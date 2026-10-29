// Small building blocks shared by the report sections (no tester-specific code here).

export function Section({ number, title, children, note }) {
  return (
    <section className="break-inside-avoid rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <h2 className="text-base font-semibold">
        <span className="mr-2 text-slate-400">{number}.</span>
        {title}
      </h2>
      {note && <p className="mt-0.5 text-xs text-slate-500">{note}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

export function Stat({ label, value, sub }) {
  return (
    <div className="rounded-lg bg-slate-50 p-2 dark:bg-slate-950">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{value ?? "-"}</div>
      {sub && <div className="text-[11px] text-slate-500">{sub}</div>}
    </div>
  );
}

// Status colours always come with a text label, never colour alone.
const TONES = {
  good: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200",
  warn: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  bad: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  info: "bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-200",
  neutral: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200",
};

export function Badge({ tone = "neutral", children }) {
  return <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${TONES[tone]}`}>{children}</span>;
}

export const verdictTone = (v) => ({ Good: "good", "Needs improvement": "warn", Poor: "bad" })[v] ?? "neutral";
export const ratingTone = (r) => ({ Good: "good", OK: "warn", Poor: "bad" })[r] ?? "neutral";
export const severityTone = (s) => ({ High: "bad", Medium: "warn", Low: "info" })[s] ?? "neutral";

export const ms = (v) => (v == null ? "-" : v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${Math.round(v)} ms`);
export const pct = (v, digits = 0) => (v == null ? "-" : `${(v * 100).toFixed(digits)}%`);
export const inr = (v) => (v == null ? "-" : `₹${v.toFixed(2)}`);
export const usd = (v) => (v == null ? "-" : `$${v < 0.01 && v > 0 ? v.toFixed(4) : v.toFixed(2)}`);

export function Empty({ children }) {
  return <p className="text-sm text-slate-500">{children}</p>;
}

export function Table({ head, rows }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-700">
            {head.map((h) => (
              <th key={h} className="py-1.5 pr-3 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((cells, i) => (
            <tr key={i} className="border-b border-slate-100 align-top dark:border-slate-800">
              {cells.map((c, j) => (
                <td key={j} className="py-1.5 pr-3">{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
