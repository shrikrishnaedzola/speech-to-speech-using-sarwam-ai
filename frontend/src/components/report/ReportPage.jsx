// The post-call report page (/report/<call_id>). Same layout in every tester app.

import { useCallback, useEffect, useState } from "react";
import "./report.css";
import { reportApi } from "./reportApi";
import CallSummary from "./CallSummary";
import Transcript from "./Transcript";
import Mishearings from "./Mishearings";
import VoiceQuality from "./VoiceQuality";
import Latency from "./Latency";
import LanguageSupport from "./LanguageSupport";
import Accuracy from "./Accuracy";
import Cost from "./Cost";
import Issues from "./Issues";
import AiSummary from "./AiSummary";
import ReportSettings from "./ReportSettings";

const BTN = "rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700";

export default function ReportPage({ callId }) {
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const regenerate = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setReport(await reportApi.generate(callId));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, [callId]);

  // Load the stored report; if there is none yet, generate it.
  useEffect(() => {
    reportApi.get(callId).then(setReport).catch((e) => (e.status === 404 ? regenerate() : setError(e.message)));
  }, [callId, regenerate]);

  useEffect(() => {
    if (report) document.title = `Report · ${report.call.provider} · ${report.call.call_id}`;
  }, [report]);

  async function saveRatings(ratings) {
    setBusy(true);
    try {
      await reportApi.saveRatings(callId, ratings);
      setReport(await reportApi.generate(callId));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <div role="alert" className="bg-amber-400 px-4 py-2 text-center text-sm font-semibold text-amber-950">
        TEST MODE - dummy data only
      </div>
      <div className="mx-auto max-w-5xl space-y-4 p-4">
        <header className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-lg font-semibold">Post-call report</h1>
            <p className="font-mono text-xs text-slate-500">
              call {callId}
              {report && ` · generated ${new Date(report.generated_at).toLocaleString()}`}
            </p>
          </div>
          <div className="no-print flex flex-wrap gap-2">
            <button className={BTN} onClick={regenerate} disabled={busy}>{busy ? "Working…" : "Regenerate"}</button>
            {report && ["pdf", "md", "json"].map((f) => (
              <a key={f} className={BTN} href={reportApi.exportUrl(callId, f)}>
                Download {f === "md" ? "Markdown" : f.toUpperCase()}
              </a>
            ))}
          </div>
        </header>

        {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>}
        {!report && !error && <p className="text-sm text-slate-500">Building the report…</p>}

        {report && (
          <>
            {report.pii.warnings.map((w) => (
              <p key={w} className="rounded-md border border-red-300 bg-red-50 p-2 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
                ⚠ {w}
              </p>
            ))}
            <ReportSettings onSaved={regenerate} />
            <CallSummary report={report} />
            <Transcript report={report} />
            <Mishearings report={report} />
            <VoiceQuality report={report} onSaveRatings={saveRatings} saving={busy} />
            <Latency report={report} />
            <LanguageSupport report={report} />
            <Accuracy report={report} />
            <Cost report={report} />
            <Issues report={report} />
            <AiSummary report={report} />
            <footer className="pb-6 text-center text-xs text-slate-500">
              {report.test_mode_notice} · {report.review_notice}
            </footer>
          </>
        )}
      </div>
    </div>
  );
}
