// Column 3: per-turn timing split, call stats, tool calls, cost, errors, raw log.

import { useEffect, useState } from "react";
import { Panel, formatMs } from "./ui";
import TurnBar, { Legend } from "./TurnBar";

function Stat({ label, value, sub }) {
  return (
    <div className="rounded-lg bg-slate-50 p-2 dark:bg-slate-950">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      {sub && <div className="text-[11px] text-slate-500">{sub}</div>}
    </div>
  );
}

function useElapsed(startIso, running) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!running) return undefined;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [running]);
  if (!startIso) return null;
  const start = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(startIso) ? startIso : `${startIso}Z`).getTime();
  return Math.max(0, (now - start) / 1000);
}

export default function MetricsPanel({ events, report, settings, active }) {
  const m = report?.metrics;
  const turns = Object.values(events.turns).sort((a, b) => a.turn_index - b.turn_index);
  const scaleMs = Math.max(0, ...turns.map((t) => t.total_ms ?? 0));
  const elapsed = useElapsed(report?.call?.started_at, active);
  const duration = active ? elapsed : m?.duration_s;
  const interruptions = Math.max(events.counters.interruptions ?? 0, m?.interruptions ?? 0);
  const parseFailures = Math.max(events.counters.json_parse_failures ?? 0, m?.json_parse_failures ?? 0);

  if (!report && turns.length === 0) {
    return (
      <Panel title="3 · Test Metrics & Logs">
        <p className="text-sm text-slate-500">Metrics appear once a call starts.</p>
      </Panel>
    );
  }

  return (
    <Panel title="3 · Test Metrics & Logs">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Stat label="Avg response" value={formatMs(m?.avg_response_ms)} sub="caller stops → agent audio" />
        <Stat label="Max response" value={formatMs(m?.max_response_ms)} />
        <Stat label="Turns" value={m?.turns ?? turns.length} />
        <Stat label="Interruptions" value={interruptions} sub="barge-ins" />
        <Stat label="Call duration" value={duration != null ? `${Math.round(duration)} s` : "-"} />
        <Stat label="JSON parse failures" value={parseFailures} sub="bad tool args → retried" />
        <Stat label="Avg STT" value={formatMs(m?.avg_stt_ms)} />
        <Stat label="Avg LLM TTFT" value={formatMs(m?.avg_llm_ttft_ms)} />
        <Stat label="Avg TTS first audio" value={formatMs(m?.avg_tts_ttfb_ms)} />
      </div>

      <h3 className="mt-4 mb-1 text-sm font-semibold">Response time per turn</h3>
      <Legend />
      <p className="mt-1 text-[11px] text-slate-500">
        Measured from Sarvam's speech_end. Add the VAD silence window ({settings.vad_silence_ms} ms) for time since
        the caller actually went quiet.
      </p>
      <div className="mt-1 max-h-72 overflow-y-auto pr-1">
        {turns.length === 0 && <p className="text-sm text-slate-500">No turns yet.</p>}
        {turns.map((t) => (
          <TurnBar key={t.turn_index} turn={t} scaleMs={scaleMs} />
        ))}
      </div>

      {m && (
        <>
          <h3 className="mt-4 mb-1 text-sm font-semibold">Estimated cost</h3>
          <div className="grid grid-cols-4 gap-2 text-sm tabular-nums">
            <Stat label="STT" value={`₹${m.cost.stt.toFixed(2)}`} />
            <Stat label="LLM" value={`₹${m.cost.llm.toFixed(2)}`} sub={`${m.llm_input_tokens}/${m.llm_output_tokens} tok`} />
            <Stat label="TTS" value={`₹${m.cost.tts.toFixed(2)}`} sub={`${m.tts_characters} chars`} />
            <Stat label="Total" value={`₹${m.cost.total.toFixed(2)}`} />
          </div>
        </>
      )}

      <h3 className="mt-4 mb-1 text-sm font-semibold">
        Tool calls ({events.toolCalls.length}
        {m ? `, ${m.tool_calls_failed} failed` : ""})
      </h3>
      <ul className="max-h-60 space-y-1 overflow-y-auto pr-1 text-xs">
        {events.toolCalls.map((tc, i) => (
          <li key={i} className="rounded border border-slate-200 p-1.5 dark:border-slate-800">
            <div className="flex justify-between gap-2">
              <span className="font-mono font-medium">
                <span className={tc.success ? "text-emerald-600" : "text-red-600"}>{tc.success ? "✓" : "✗"}</span>{" "}
                {tc.name}
              </span>
              <span className="tabular-nums text-slate-500">{formatMs(tc.duration_ms)}</span>
            </div>
            <div className="truncate font-mono text-slate-500" title={JSON.stringify(tc.arguments)}>
              {typeof tc.arguments === "string" ? tc.arguments : JSON.stringify(tc.arguments)}
            </div>
            {!tc.success && tc.result?.error && <div className="text-red-600">{tc.result.error}</div>}
          </li>
        ))}
      </ul>

      {events.errors.length > 0 && (
        <>
          <h3 className="mt-4 mb-1 text-sm font-semibold text-red-600">Errors</h3>
          <ul className="space-y-1 text-xs text-red-600">
            {events.errors.map((e, i) => (
              <li key={i} className="rounded bg-red-50 p-1.5 dark:bg-red-950">{e.message}</li>
            ))}
          </ul>
        </>
      )}

      <details className="mt-4 text-xs">
        <summary className="cursor-pointer font-semibold">Raw event log ({events.log.length})</summary>
        <pre className="mt-1 max-h-72 overflow-auto rounded bg-slate-950 p-2 text-[11px] leading-snug text-slate-200">
          {events.log
            .map((e) => `${e.ts?.slice(11, 23) ?? ""} ${e.type} ${JSON.stringify(e.data)}`)
            .join("\n")}
        </pre>
      </details>
    </Panel>
  );
}
