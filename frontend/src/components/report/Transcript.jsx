// Section 2: the conversation, with colour highlights (each colour also has a text label).

import { Section } from "./ui";

const HIGHLIGHTS = {
  mishearing: { label: "Mishearing", ring: "ring-2 ring-red-500", chip: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200" },
  reasked: { label: "Re-asked", ring: "ring-2 ring-orange-400", chip: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200" },
  tool: { label: "Tool call", ring: "", chip: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200" },
  interruption: { label: "Interrupted", ring: "ring-2 ring-purple-500", chip: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200" },
};

export default function Transcript({ report }) {
  return (
    <Section number={2} title="Transcript">
      <div className="mb-3 flex flex-wrap gap-2 text-[11px]">
        {Object.entries(HIGHLIGHTS).map(([k, h]) => (
          <span key={k} className={`rounded px-1.5 py-0.5 ${h.chip}`}>{h.label}</span>
        ))}
      </div>
      <div className="flex max-h-[34rem] flex-col gap-2 overflow-y-auto rounded-lg bg-slate-50 p-3 dark:bg-slate-950">
        {report.transcript.map((item, i) =>
          item.role === "tool" ? <ToolRow key={i} item={item} /> : <Bubble key={i} item={item} />,
        )}
      </div>
    </Section>
  );
}

function Chips({ item }) {
  return item.highlights
    .filter((h) => h !== "tool")
    .map((h) => (
      <span key={h} className={`rounded px-1 ${HIGHLIGHTS[h].chip}`}>{HIGHLIGHTS[h].label}</span>
    ));
}

function Bubble({ item }) {
  const isAgent = item.role === "agent";
  const ring = item.highlights.map((h) => HIGHLIGHTS[h]?.ring).find(Boolean) ?? "";
  return (
    <div className={`flex flex-col ${isAgent ? "items-start" : "items-end"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${ring} ${
          isAgent ? "rounded-tl-sm bg-white shadow-sm dark:bg-slate-800" : "rounded-tr-sm bg-emerald-600 text-white"
        }`}
      >
        {item.text}
      </div>
      <div className="mt-0.5 flex flex-wrap gap-1.5 text-[11px] text-slate-500">
        <span>{isAgent ? "Agent" : "Caller"}</span>
        <span className="tabular-nums">{item.time}</span>
        {item.language && <span className="rounded bg-slate-200 px-1 dark:bg-slate-700">{item.language}</span>}
        <Chips item={item} />
      </div>
    </div>
  );
}

function ToolRow({ item }) {
  const failed = item.tool && !item.tool.success;
  return (
    <div className="flex justify-center">
      <div className={`max-w-[95%] rounded px-2 py-1 font-mono text-[11px] ${HIGHLIGHTS.tool.chip}`}>
        <span className="tabular-nums">{item.time}</span> · {failed ? "✗" : "✓"} {item.text}
        {failed && item.tool.error && <span className="block text-red-700 dark:text-red-300">{item.tool.error}</span>}
      </div>
    </div>
  );
}
