// Section 5: reply-time stats, a per-turn chart (stacked STT/LLM/TTS for cascaded
// pipelines like Sarvam), and the 3 slowest turns.

import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Section, Stat, Table, ms, ratingTone } from "./ui";

const STEPS = [
  ["stt_ms", "STT", "var(--rep-stt)"],
  ["turn_wait_ms", "Turn wait", "var(--rep-wait)"],
  ["llm_ttft_ms", "LLM first token", "var(--rep-llm)"],
  ["tts_ttfb_ms", "TTS first audio", "var(--rep-tts)"],
  ["other_ms", "Other", "var(--rep-other)"],
];

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const turn = payload[0].payload;
  return (
    <div className="rounded border border-slate-200 bg-white p-2 text-xs shadow dark:border-slate-700 dark:bg-slate-900">
      <div className="font-semibold">Turn {label} · {ms(turn.total_ms)} {turn.rating && `(${turn.rating})`}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex justify-between gap-3">
          <span>{p.name}</span>
          <span className="tabular-nums">{ms(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

export default function Latency({ report }) {
  const l = report.latency;
  const data = l.per_turn.filter((t) => t.turn_index > 0 && t.total_ms != null);
  const axis = { fontSize: 11, fill: "var(--rep-axis)" };
  return (
    <Section number={5} title="Latency" note="Reply time = caller stops speaking → first agent audio. Good < 1 s, OK 1–1.5 s, Poor > 1.5 s.">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        <Stat label="Average" value={ms(l.average_ms)} />
        <Stat label="Median" value={ms(l.median_ms)} />
        <Stat label="p90" value={ms(l.p90_ms)} />
        <Stat label="Max" value={ms(l.max_ms)} />
        <div className="rounded-lg bg-slate-50 p-2 dark:bg-slate-950">
          <div className="text-[11px] text-slate-500">Rating (average)</div>
          <div className="mt-1">{l.rating ? <Badge tone={ratingTone(l.rating)}>{l.rating}</Badge> : "-"}</div>
        </div>
      </div>

      {data.length > 0 && (
        <div className="mt-4 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap={4}>
              <CartesianGrid vertical={false} stroke="var(--rep-grid)" />
              <XAxis dataKey="turn_index" tick={axis} tickLine={false} axisLine={{ stroke: "var(--rep-grid)" }} />
              <YAxis tick={axis} tickLine={false} axisLine={false} width={44}
                tickFormatter={(v) => (v >= 1000 ? `${v / 1000}s` : v)} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--rep-grid)", opacity: 0.4 }} />
              <ReferenceLine y={1000} stroke="var(--rep-axis)" strokeDasharray="4 4" label={{ value: "1 s", ...axis, position: "right" }} />
              <ReferenceLine y={1500} stroke="var(--rep-axis)" strokeDasharray="4 4" label={{ value: "1.5 s", ...axis, position: "right" }} />
              {l.has_step_split ? (
                <>
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {STEPS.map(([key, name, color], i) => (
                    <Bar key={key} dataKey={key} name={name} stackId="t" fill={color}
                      stroke="var(--rep-surface, transparent)" radius={i === STEPS.length - 1 ? [4, 4, 0, 0] : 0} />
                  ))}
                </>
              ) : (
                <Bar dataKey="total_ms" name="Reply time" fill="var(--rep-stt)" radius={[4, 4, 0, 0]} />
              )}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <h3 className="mt-4 text-sm font-semibold">Slowest 3 turns</h3>
      <Table
        head={["Turn", "Reply time", "What was happening"]}
        rows={l.slowest.map((s) => [s.turn_index, <span className="tabular-nums">{ms(s.total_ms)}</span>, s.reason])}
      />
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-slate-600 dark:text-slate-400">Table: every turn</summary>
        <Table
          head={["Turn", "Total", "Rating", ...(l.has_step_split ? ["STT", "Wait", "LLM", "TTS"] : [])]}
          rows={l.per_turn.map((t) => [
            t.turn_index === 0 ? "Greeting" : t.turn_index, ms(t.total_ms), t.rating ?? "-",
            ...(l.has_step_split ? [ms(t.stt_ms), ms(t.turn_wait_ms), ms(t.llm_ttft_ms), ms(t.tts_ttfb_ms)] : []),
          ])}
        />
      </details>
    </Section>
  );
}
