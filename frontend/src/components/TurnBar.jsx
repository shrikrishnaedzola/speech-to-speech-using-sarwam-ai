// One turn's response time, split into steps, as a small stacked bar.
// All bars share one scale (the slowest turn = full width) so they compare.
// Exact numbers are always printed under the bar (colors are never the only cue).

import { formatMs } from "./ui";

export const STEPS = [
  { key: "stt_ms", label: "STT", color: "var(--step-stt)" },
  { key: "turn_wait_ms", label: "Turn wait", color: "var(--step-wait)" },
  { key: "llm_ttft_ms", label: "LLM TTFT", color: "var(--step-llm)" },
  { key: "tts_ttfb_ms", label: "TTS first audio", color: "var(--step-tts)" },
  { key: "other_ms", label: "Other", color: "var(--step-other)" },
];

export function withOther(turn) {
  const known = ["stt_ms", "turn_wait_ms", "llm_ttft_ms", "tts_ttfb_ms"].reduce((s, k) => s + (turn[k] ?? 0), 0);
  const other = turn.total_ms != null ? Math.max(0, turn.total_ms - known) : null;
  return { ...turn, other_ms: other };
}

export function Legend() {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-600 dark:text-slate-400">
      {STEPS.map((s) => (
        <span key={s.key} className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />
          {s.label}
        </span>
      ))}
    </div>
  );
}

export default function TurnBar({ turn, scaleMs }) {
  const t = withOther(turn);
  const total = t.total_ms ?? 0;
  const widthPct = scaleMs > 0 ? Math.max(2, (total / scaleMs) * 100) : 0;
  const parts = STEPS.filter((s) => (t[s.key] ?? 0) > 0);

  return (
    <div className="py-1.5">
      <div className="flex items-baseline justify-between text-xs">
        <span className="font-medium">
          {t.turn_index === 0 ? "Greeting" : `Turn ${t.turn_index}`}
          {t.interrupted && <span className="ml-1 text-amber-600">· barge-in</span>}
        </span>
        <span className="font-semibold tabular-nums">{formatMs(t.total_ms)}</span>
      </div>
      {/* the bar: 2px gaps between segments, rounded ends */}
      <div className="mt-1 h-3 w-full">
        <div className="flex h-3 gap-[2px]" style={{ width: `${widthPct}%` }}>
          {parts.map((s, i) => (
            <div
              key={s.key}
              title={`${s.label}: ${formatMs(t[s.key])}`}
              className={`h-full ${i === 0 ? "rounded-l" : ""} ${i === parts.length - 1 ? "rounded-r" : ""}`}
              style={{ background: s.color, flexGrow: t[s.key], flexBasis: 0, minWidth: 2 }}
            />
          ))}
        </div>
      </div>
      <div className="mt-0.5 flex flex-wrap gap-x-2 text-[11px] tabular-nums text-slate-500">
        <span>STT {formatMs(t.stt_ms)}</span>
        <span>wait {formatMs(t.turn_wait_ms)}</span>
        <span>LLM {formatMs(t.llm_ttft_ms)}</span>
        <span>TTS {formatMs(t.tts_ttfb_ms)}</span>
        {t.tool_ms ? <span>(tools {formatMs(t.tool_ms)} inside LLM)</span> : null}
      </div>
    </div>
  );
}
