// Column 1: call setup, buttons, live status and the transcript.

import { useEffect, useRef } from "react";
import { Button, Panel, Select, timeOf } from "./ui";
import SettingsDrawer from "./SettingsDrawer";

const STATUS = {
  idle: { label: "Ready", color: "bg-slate-400" },
  connecting: { label: "Connecting", color: "bg-amber-500 animate-pulse" },
  listening: { label: "Listening", color: "bg-emerald-500" },
  thinking: { label: "Thinking", color: "bg-sky-500 animate-pulse" },
  speaking: { label: "Agent speaking", color: "bg-violet-500 animate-pulse" },
  ended: { label: "Ended", color: "bg-slate-500" },
};

export default function CallPanel(props) {
  const { options, forms, formId, setFormId, settings, setSettings, status, active, mode, muted } = props;
  const set = (key) => (value) => setSettings((s) => ({ ...s, [key]: value }));
  const st = STATUS[status] ?? STATUS.idle;

  // Switching TTS model resets the voice to that model's first voice.
  function setTtsModel(model) {
    setSettings((s) => ({ ...s, tts_model: model, tts_voice: options.tts_voices[model][0] }));
  }
  const v4Fallback = settings.tts_model === "bulbul:v4-flash" && options.v4_unsupported_languages.includes(settings.language);

  return (
    <Panel title="1 · Call & Conversation">
      <div className="grid grid-cols-2 gap-2">
        <div className="col-span-2">
          <Select label="Form to test" value={formId} onChange={setFormId} disabled={active}
            options={forms.map((f) => ({ value: f.id, label: f.name }))} />
        </div>
        <Select label="STT model" value={settings.stt_model} onChange={set("stt_model")} disabled={active}
          options={options.stt_models.map((m) => ({ value: m.id, label: m.label }))} />
        <Select label="LLM model" value={settings.llm_model} onChange={set("llm_model")} disabled={active}
          options={options.llm_models.map((m) => ({ value: m.id, label: m.label }))} />
        <Select label="TTS model" value={settings.tts_model} onChange={setTtsModel} disabled={active}
          options={options.tts_models.map((m) => ({ value: m.id, label: m.label }))} />
        <Select label="TTS voice" value={settings.tts_voice} onChange={set("tts_voice")} disabled={active}
          options={options.tts_voices[settings.tts_model].map((v) => ({ value: v, label: v }))} />
        <Select label="Language" value={settings.language} onChange={set("language")} disabled={active}
          options={options.languages.map((l) => ({ value: l.code, label: l.label }))} />
        <Select label="Audio quality" value={settings.audio_quality} onChange={set("audio_quality")} disabled={active}
          options={[{ value: "normal", label: "Normal (16 kHz)" }, { value: "phone", label: "Phone (8 kHz)" }]} />
      </div>
      {v4Fallback && (
        <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
          Bulbul v4 Flash has no Malayalam/Odia yet - this call will use Bulbul v3.
        </p>
      )}

      <SettingsDrawer settings={settings} setSettings={setSettings} disabled={active}
        simSpeed={props.simSpeed} setSimSpeed={props.setSimSpeed} />

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={props.onStart} disabled={active || !formId}>Start Call</Button>
        <Button variant="danger" onClick={props.onEnd} disabled={!active || mode !== "live"}>End Call</Button>
        <Button onClick={props.onMute} disabled={!active || mode !== "live"}>{muted ? "Unmute" : "Mute"}</Button>
        <Button onClick={props.onSimulate} disabled={active || !formId} title="Replay a saved dummy call. No mic, no cost.">
          Simulate
        </Button>
        <span className="ml-auto flex items-center gap-2 text-sm" aria-live="polite">
          <span className={`inline-block h-2.5 w-2.5 rounded-full ${st.color}`} />
          {st.label}
          {mode === "simulate" && status !== "idle" && <span className="text-xs text-slate-500">(simulated)</span>}
        </span>
      </div>
      {props.reportReady && (
        <a href={props.reportReady.url} target="_blank" rel="noreferrer"
          className="mt-2 flex items-center justify-between rounded-md bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-700">
          <span>📄 Report ready - open in new tab</span>
          <span className="tabular-nums">{Math.round(props.reportReady.score)}/100 · {props.reportReady.verdict}</span>
        </a>
      )}
      {props.localError && (
        <p className="mt-2 rounded-md bg-red-50 p-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
          {props.localError}
        </p>
      )}

      <Transcript transcript={props.transcript} partial={props.partial} />
    </Panel>
  );
}

function Transcript({ transcript, partial }) {
  const endRef = useRef(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [transcript.length, partial.agent, partial.caller]);

  return (
    <div className="mt-4 flex max-h-[60vh] min-h-48 flex-col gap-2 overflow-y-auto rounded-lg bg-slate-50 p-3 dark:bg-slate-950">
      {transcript.length === 0 && !partial.agent && !partial.caller && (
        <p className="text-sm text-slate-500">The live transcript appears here.</p>
      )}
      {transcript.map((m, i) => (
        <Bubble key={i} role={m.role} text={m.text} time={timeOf(m.ts)} language={m.language} interrupted={m.interrupted} />
      ))}
      {partial.caller && <Bubble role="caller" text={partial.caller} partial />}
      {partial.agent && <Bubble role="agent" text={partial.agent} partial />}
      <div ref={endRef} />
    </div>
  );
}

function Bubble({ role, text, time, language, interrupted, partial }) {
  const isAgent = role === "agent";
  return (
    <div className={`flex flex-col ${isAgent ? "items-start" : "items-end"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
          isAgent
            ? "rounded-tl-sm bg-white text-slate-900 shadow-sm dark:bg-slate-800 dark:text-slate-100"
            : "rounded-tr-sm bg-emerald-600 text-white"
        } ${partial ? "opacity-60" : ""}`}
      >
        {text}
      </div>
      <div className="mt-0.5 flex gap-2 text-[11px] text-slate-500">
        <span>{isAgent ? "Agent" : "Caller"}</span>
        {time && <span>{time}</span>}
        {language && <span className="rounded bg-slate-200 px-1 dark:bg-slate-700">{language}</span>}
        {interrupted && <span className="text-amber-600">interrupted</span>}
        {partial && <span>…</span>}
      </div>
    </div>
  );
}
