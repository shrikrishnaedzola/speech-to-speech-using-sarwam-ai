// Advanced settings: latency tuning, LLM options and cost rates.

import { NumberInput, Select } from "./ui";

export default function SettingsDrawer({ settings, setSettings, disabled, simSpeed, setSimSpeed }) {
  const set = (key) => (value) => setSettings((s) => ({ ...s, [key]: value }));
  return (
    <details className="mt-3 rounded-lg border border-slate-200 p-2 text-sm dark:border-slate-800">
      <summary className="cursor-pointer font-medium">Settings (latency, LLM, cost rates)</summary>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <Select label="STT stream type" value={settings.stt_stream_type} onChange={set("stt_stream_type")} disabled={disabled}
          options={[{ value: "fast", label: "fast (500 ms chunks)" }, { value: "balanced", label: "balanced (1000 ms)" }]} />
        <NumberInput label="Turn-stop timeout (ms)" value={settings.turn_stop_timeout_ms} onChange={set("turn_stop_timeout_ms")}
          disabled={disabled} hint="Wait after Sarvam's speech_end before calling the LLM. Docs: 70 (LiveKit) / 200 (Pipecat)." />
        <NumberInput label="VAD silence window (ms)" value={settings.vad_silence_ms} onChange={set("vad_silence_ms")}
          disabled={disabled} hint="Sarvam server VAD silence before speech_end. Default 500." />
        <Select label="Reasoning (sarvam-105b only)" value={settings.reasoning} onChange={set("reasoning")}
          disabled={disabled || settings.llm_model !== "sarvam-105b"}
          options={[{ value: "off", label: "off (fastest)" }, { value: "low", label: "low" }]} />
        <NumberInput label="LLM max tokens" value={settings.llm_max_tokens} onChange={set("llm_max_tokens")} disabled={disabled} />
        <NumberInput label="TTS pace" step={0.05} value={settings.tts_pace} onChange={set("tts_pace")} disabled={disabled} />
        <NumberInput label="TTS min buffer (chars)" value={settings.tts_min_buffer_size} onChange={set("tts_min_buffer_size")}
          disabled={disabled} hint="Characters collected before TTS starts. Lower = faster first audio." />
        <NumberInput label="Simulate speed (x)" step={0.5} value={simSpeed} onChange={setSimSpeed} disabled={disabled} />
      </div>
      <p className="mt-3 text-xs font-medium text-slate-600 dark:text-slate-400">Cost rates (INR, from Sarvam pricing page)</p>
      <div className="mt-1 grid grid-cols-2 gap-2">
        <NumberInput label="STT per minute" step={0.01} value={settings.rate_stt_per_min} onChange={set("rate_stt_per_min")} />
        <NumberInput label="TTS v3 per 10K chars" step={0.5} value={settings.rate_tts_v3_per_10k_chars} onChange={set("rate_tts_v3_per_10k_chars")} />
        <NumberInput label="TTS v4 per 10K chars" step={0.5} value={settings.rate_tts_v4_per_10k_chars} onChange={set("rate_tts_v4_per_10k_chars")} />
        <NumberInput label="LLM input per 1M tokens" value={settings.rate_llm_input_per_1m} onChange={set("rate_llm_input_per_1m")} />
        <NumberInput label="LLM output per 1M tokens" value={settings.rate_llm_output_per_1m} onChange={set("rate_llm_output_per_1m")} />
      </div>
      <p className="mt-2 text-xs text-slate-500">Rates are saved with each call when it starts.</p>
    </details>
  );
}
