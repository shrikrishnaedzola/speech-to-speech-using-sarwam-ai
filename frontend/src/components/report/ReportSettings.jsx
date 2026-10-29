// Report settings: score weights, exchange rate, cost target, optional features.
// Saved on the backend (shared by all reports of this tester), then the report is regenerated.

import { useEffect, useState } from "react";
import { reportApi } from "./reportApi";

const WEIGHTS = [
  ["accuracy", "Accuracy"], ["mishearings", "Mishearings"], ["latency", "Latency"],
  ["voice_quality", "Voice quality"], ["language", "Language support"], ["cost", "Cost"],
];

function NumberField({ label, value, onChange, step = 1 }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-600 dark:text-slate-400">
      {label}
      <input type="number" step={step} value={value}
        onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))}
        className="rounded border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100" />
    </label>
  );
}

export default function ReportSettings({ onSaved }) {
  const [settings, setSettings] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    reportApi.settings().then(setSettings).catch(() => {});
  }, []);
  if (!settings) return null;

  const setWeight = (k, v) => setSettings((s) => ({ ...s, weights: { ...s.weights, [k]: v } }));
  const total = Object.values(settings.weights).reduce((a, b) => a + b, 0);

  async function save() {
    setSaving(true);
    try {
      await reportApi.saveSettings(settings);
      await onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <details className="no-print rounded-xl border border-slate-200 bg-white p-3 text-sm dark:border-slate-800 dark:bg-slate-900">
      <summary className="cursor-pointer font-medium">Report settings (weights, rates, options)</summary>
      <p className="mt-2 text-xs font-medium text-slate-600 dark:text-slate-400">
        Score weights (%) - total {total}{total !== 100 && " (re-scaled to 100 automatically)"}
      </p>
      <div className="mt-1 grid grid-cols-3 gap-2 sm:grid-cols-6">
        {WEIGHTS.map(([k, label]) => (
          <NumberField key={k} label={label} value={settings.weights[k]} onChange={(v) => setWeight(k, v)} />
        ))}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <NumberField label="1 USD in INR" step={0.1} value={settings.usd_to_inr}
          onChange={(v) => setSettings((s) => ({ ...s, usd_to_inr: v }))} />
        <NumberField label="Cost target (₹ per minute)" step={0.1} value={settings.cost_target_inr_per_min}
          onChange={(v) => setSettings((s) => ({ ...s, cost_target_inr_per_min: v }))} />
        <label className="flex flex-col gap-1 text-xs text-slate-600 dark:text-slate-400">
          Rates last updated
          <input value={settings.rates_last_updated}
            onChange={(e) => setSettings((s) => ({ ...s, rates_last_updated: e.target.value }))}
            className="rounded border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100" />
        </label>
      </div>
      <div className="mt-3 flex flex-wrap gap-4">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={settings.mos_enabled}
            onChange={(e) => setSettings((s) => ({ ...s, mos_enabled: e.target.checked }))} />
          Automatic MOS score (DNSMOS, runs locally)
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={settings.ai_summary_enabled}
            onChange={(e) => setSettings((s) => ({ ...s, ai_summary_enabled: e.target.checked }))} />
          AI-written summary (Claude)
        </label>
      </div>
      <p className="mt-2 text-xs text-slate-500">Provider price tables are edited in the backend settings file (data/report_settings.json).</p>
      <button onClick={save} disabled={saving}
        className="mt-3 rounded-md bg-emerald-600 px-3 py-1.5 font-medium text-white disabled:opacity-50">
        {saving ? "Saving…" : "Save settings & regenerate"}
      </button>
    </details>
  );
}
