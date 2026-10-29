import { useEffect, useState } from "react";
import { api } from "./api";
import { useCallEvents } from "./hooks/useCallEvents";
import { useVoiceCall } from "./hooks/useVoiceCall";
import TestModeBanner from "./components/TestModeBanner";
import CallPanel from "./components/CallPanel";
import FormPanel from "./components/FormPanel";
import MetricsPanel from "./components/MetricsPanel";

export default function App() {
  const [options, setOptions] = useState(null);
  const [forms, setForms] = useState([]);
  const [formId, setFormId] = useState("");
  const [settings, setSettings] = useState(null);
  const [simSpeed, setSimSpeed] = useState(1);
  const [callId, setCallId] = useState(null);
  const [mode, setMode] = useState(null); // "live" | "simulate"
  const [localError, setLocalError] = useState(null);
  const [starting, setStarting] = useState(false);

  const events = useCallEvents(callId);
  const voice = useVoiceCall();

  // Load dropdown options and forms once.
  useEffect(() => {
    Promise.all([api.options(), api.forms()])
      .then(([opts, formList]) => {
        setOptions(opts);
        setSettings(opts.defaults);
        setForms(formList);
        setFormId(formList[0]?.id ?? "");
      })
      .catch((e) => setLocalError(`Cannot reach the backend: ${e.message}`));
  }, []);

  // When the backend ends the call, release the microphone.
  useEffect(() => {
    if (events.ended && mode === "live") voice.disconnect();
  }, [events.ended]); // eslint-disable-line react-hooks/exhaustive-deps

  const active = Boolean(callId) && !events.ended && events.status !== "ended";

  async function startCall() {
    setLocalError(null);
    setStarting(true);
    try {
      const session = await api.startSession(formId, settings);
      setMode("live");
      setCallId(session.call_id);
      await voice.connect(session);
    } catch (e) {
      setLocalError(e.message);
      voice.disconnect();
    } finally {
      setStarting(false);
    }
  }

  async function startSimulation() {
    setLocalError(null);
    try {
      const sim = await api.simulate(formId, settings, simSpeed);
      setMode("simulate");
      setCallId(sim.call_id);
    } catch (e) {
      setLocalError(e.message);
    }
  }

  async function endCall() {
    if (mode === "live" && callId) await api.endSession(callId).catch(() => {});
    voice.disconnect();
  }

  if (!options || !settings) {
    return (
      <div className="min-h-screen">
        <TestModeBanner />
        <p className="p-6 text-sm text-slate-600 dark:text-slate-400">{localError ?? "Loading…"}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <TestModeBanner apiKeyConfigured={options.api_key_configured} />
      <header className="px-4 pt-4">
        <h1 className="text-lg font-semibold">Zolabs Voice Form Tester · Sarvam pipeline</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Saaras STT → Sarvam-105B → Bulbul TTS. Internal evaluation tool.
        </p>
      </header>
      <main className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-3">
        <CallPanel
          options={options}
          forms={forms}
          formId={formId}
          setFormId={setFormId}
          settings={settings}
          setSettings={setSettings}
          simSpeed={simSpeed}
          setSimSpeed={setSimSpeed}
          status={starting ? "connecting" : callId ? events.status : "idle"}
          active={active || starting}
          mode={mode}
          muted={voice.muted}
          onStart={startCall}
          onSimulate={startSimulation}
          onEnd={endCall}
          onMute={voice.toggleMute}
          transcript={events.transcript}
          partial={events.partial}
          localError={localError}
          reportReady={events.reportReady}
        />
        <FormPanel callId={callId} formState={events.formState} report={events.report} />
        <MetricsPanel events={events} report={events.report} settings={settings} active={active} />
      </main>
    </div>
  );
}
