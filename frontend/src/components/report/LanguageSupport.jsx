// Section 6: selected vs detected languages, correct-language replies, code-mixing.

import { Empty, Section, Stat, Table } from "./ui";

export default function LanguageSupport({ report }) {
  const l = report.language;
  const byLang = Object.entries(l.mishearings_by_language);
  return (
    <Section number={6} title="Language support" note={l.method_note}>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Language selected" value={l.selected} />
        <Stat label="Replies in correct language" value={l.agent_correct_language_pct != null ? `${l.agent_correct_language_pct.toFixed(0)}%` : "-"}
          sub={`${l.agent_turns_checked} agent turns checked`} />
        <Stat label="Code-mixing (tester)" value={l.code_mixing_rating != null ? `${l.code_mixing_rating} / 5` : "not rated"} />
        <Stat label="Language-specific mishearings" value={byLang.reduce((s, [, n]) => s + n, 0)}
          sub={byLang.map(([k, n]) => `${k}: ${n}`).join(", ") || "none"} />
      </div>
      <h3 className="mt-3 text-sm font-semibold">Languages detected in caller turns</h3>
      <p className="text-sm">{l.detected.map((d) => `${d.language} (${d.caller_turns} turns)`).join(", ") || "-"}</p>
      <h3 className="mt-3 text-sm font-semibold">Replies in the wrong language</h3>
      {l.wrong_language_turns.length === 0 ? (
        <Empty>None.</Empty>
      ) : (
        <Table head={["Time", "Agent said", "Expected", "Got"]}
          rows={l.wrong_language_turns.map((w) => [w.time, w.text, w.expected, w.got])} />
      )}
    </Section>
  );
}
