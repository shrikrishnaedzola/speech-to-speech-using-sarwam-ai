// Listens to the backend's live event WebSocket for one call and keeps all
// UI state in one place: status, transcript, form cards, turns, tool calls,
// counters, errors and the raw log. Also refreshes the full report (scores,
// averages, cost) from the backend shortly after anything changes.

import { useEffect, useReducer, useRef } from "react";
import { api, eventsSocketUrl } from "../api";

const initialState = {
  status: "idle",
  transcript: [],
  partial: { caller: "", agent: "" },
  formState: null,
  turns: {}, // turn_index -> timings
  toolCalls: [],
  counters: { interruptions: 0, json_parse_failures: 0 },
  errors: [],
  log: [],
  report: null,
  ended: false,
  reportReady: null, // {url, score, verdict} once the post-call report exists
};

function reducer(state, action) {
  if (action.type === "reset") return initialState;
  if (action.type === "report") return { ...state, report: action.report };

  const event = action.event;
  const log = [...state.log, event].slice(-1000);
  const d = event.data;
  switch (event.type) {
    case "status":
      return { ...state, log, status: d.status };
    case "transcript":
      return {
        ...state,
        log,
        transcript: [...state.transcript, { ...d, ts: event.ts }],
        partial: { ...state.partial, [d.role]: "" },
      };
    case "transcript_partial":
      return { ...state, partial: { ...state.partial, [d.role]: d.text } };
    case "form_state":
      return { ...state, log, formState: d };
    case "turn_metrics":
      return { ...state, log, turns: { ...state.turns, [d.turn_index]: d } };
    case "tool_call":
      return { ...state, log, toolCalls: [...state.toolCalls, { ...d, ts: event.ts }] };
    case "counters":
      return { ...state, log, counters: { ...state.counters, ...d } };
    case "error":
      return { ...state, log, errors: [...state.errors, { ...d, ts: event.ts }] };
    case "call_ended":
      return { ...state, log, ended: true, status: "ended" };
    case "report_ready":
      return { ...state, log, reportReady: d };
    case "ping":
      return state;
    default:
      return { ...state, log };
  }
}

// Events after which the scores/averages/cost may have changed.
const REPORT_TRIGGERS = new Set(["form_state", "turn_metrics", "usage", "counters", "tool_call", "call_ended"]);

export function useCallEvents(callId) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const timer = useRef(null);

  useEffect(() => {
    dispatch({ type: "reset" });
    if (!callId) return undefined;

    const refreshReport = () => {
      clearTimeout(timer.current);
      timer.current = setTimeout(async () => {
        try {
          dispatch({ type: "report", report: await api.report(callId) });
        } catch {
          /* the next event will retry */
        }
      }, 400);
    };

    const ws = new WebSocket(eventsSocketUrl(callId));
    ws.onmessage = (msg) => {
      const event = JSON.parse(msg.data);
      dispatch({ type: "event", event });
      if (REPORT_TRIGGERS.has(event.type)) refreshReport();
    };
    ws.onerror = () =>
      dispatch({
        type: "event",
        event: { type: "error", ts: new Date().toISOString(), data: { message: "Live events connection failed" } },
      });
    refreshReport();
    return () => {
      clearTimeout(timer.current);
      ws.close();
    };
  }, [callId]);

  const refresh = async () => {
    if (callId) dispatch({ type: "report", report: await api.report(callId) });
  };
  return { ...state, refresh };
}
