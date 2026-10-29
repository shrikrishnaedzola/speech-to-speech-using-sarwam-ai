// Section 3: what the caller said vs what the AI heard.

import { Badge, Empty, Section, Stat, Table, pct } from "./ui";

const KIND = {
  transcription: "Transcription error",
  caller_correction: "Caller corrected it",
  value_changed: "Answer changed",
  wrong_value: "Wrong saved value",
  number_misheard: "Number misheard",
};

export default function Mishearings({ report }) {
  const m = report.mishearings;
  return (
    <Section number={3} title="Mishearings (understanding errors)"
      note={m.script_available ? `Compared with the expected caller script (${m.aligned_turns} turns, in order).`
        : "No expected caller script for this call, so WER/CER are not available."}>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Mishearings" value={m.total} />
        <Stat label="Fixed during call" value={m.fixed} />
        <Stat label="Word error rate (WER)" value={pct(m.wer, 1)} />
        <Stat label="Character error rate (CER)" value={pct(m.cer, 1)} sub="counts visible letters" />
      </div>
      <div className="mt-3">
        {m.items.length === 0 ? (
          <Empty>No mishearings found.</Empty>
        ) : (
          <Table
            head={["Time", "Type", "Caller said", "AI heard / saved", "Field", "Fixed?"]}
            rows={m.items.map((i) => [
              <span className="tabular-nums">{i.time ?? "-"}</span>,
              <span>{KIND[i.kind]}{i.language ? <span className="block text-[11px] text-slate-500">{i.language}</span> : null}</span>,
              i.said,
              <span>{i.heard}{i.detail ? <span className="block text-[11px] text-slate-500">{i.detail}</span> : null}</span>,
              <span className="font-mono text-xs">{i.field_id ?? "-"}</span>,
              i.fixed == null ? <Badge>unknown</Badge> : i.fixed ? <Badge tone="good">Fixed</Badge> : <Badge tone="bad">Not fixed</Badge>,
            ])}
          />
        )}
      </div>
    </Section>
  );
}
