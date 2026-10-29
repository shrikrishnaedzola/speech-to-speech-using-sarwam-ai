import React, { Suspense, lazy } from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./index.css";

// The report page (with its charts) is only downloaded when a report is opened.
const ReportPage = lazy(() => import("./components/report/ReportPage.jsx"));

// Two pages, no router library needed:
//   /                  the tester (3 columns)
//   /report/<call_id>  the post-call report (opened in a new tab)
const reportMatch = window.location.pathname.match(/^\/report\/([\w-]+)\/?$/);

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {reportMatch ? (
      <Suspense fallback={<p className="p-4 text-sm">Loading report…</p>}>
        <ReportPage callId={reportMatch[1]} />
      </Suspense>
    ) : (
      <App />
    )}
  </React.StrictMode>
);
