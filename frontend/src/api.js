// Small wrappers around the backend API. All calls go to our own backend (/api),
// never to Sarvam directly.

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

export const api = {
  options: () => request("/api/options"),
  forms: () => request("/api/forms"),
  startSession: (form_id, settings) =>
    request("/api/session", { method: "POST", body: JSON.stringify({ form_id, settings }) }),
  endSession: (callId) => request(`/api/session/${callId}/end`, { method: "POST" }),
  simulate: (form_id, settings, speed = 1) =>
    request("/api/simulate", { method: "POST", body: JSON.stringify({ form_id, settings, speed }) }),
  sendOffer: (url, offer) => request(url, { method: "POST", body: JSON.stringify(offer) }),
  report: (callId) => request(`/api/calls/${callId}`),
  review: (callId, reviews) =>
    request(`/api/calls/${callId}/review`, { method: "POST", body: JSON.stringify({ reviews }) }),
  exportUrl: (callId, format, section = "fields") =>
    `/api/calls/${callId}/export?format=${format}&section=${section}`,
};

export function eventsSocketUrl(callId) {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/api/calls/${callId}/events`;
}
