// API calls for the report page. Same endpoints in every tester app
// (they come from the shared report_module router).

const BACKEND_BASE = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/+$/, "");

function toUrl(path) {
  if (!BACKEND_BASE) return path;
  return `${BACKEND_BASE}${path.startsWith("/") ? "" : "/"}${path}`;
}

async function call(path, options = {}) {
  const url = toUrl(path);
  const res = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export const reportApi = {
  get: (id) => call(`/api/calls/${id}/report`),
  generate: (id) => call(`/api/calls/${id}/report`, { method: "POST" }),
  ratings: (id) => call(`/api/calls/${id}/ratings`),
  saveRatings: (id, ratings) => call(`/api/calls/${id}/ratings`, { method: "POST", body: JSON.stringify(ratings) }),
  settings: () => call("/api/report/settings"),
  saveSettings: (s) => call("/api/report/settings", { method: "PUT", body: JSON.stringify(s) }),
  exportUrl: (id, format) => toUrl(`/api/calls/${id}/report/export?format=${format}`),
};
