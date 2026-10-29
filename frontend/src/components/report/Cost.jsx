// Section 8: cost of this call, breakdown, per minute / per form, 1,000-call projection.

import { Section, Stat, Table, inr, usd } from "./ui";

export default function Cost({ report }) {
  const c = report.cost;
  return (
    <Section number={8} title="Cost" note={`Rates last updated ${c.rates_last_updated} · 1 USD = ₹${c.usd_to_inr}. ${c.note}`}>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="This call" value={inr(c.total_inr)} sub={usd(c.total_usd)} />
        <Stat label="Per minute" value={inr(c.per_minute_inr)} sub={usd(c.per_minute_usd)} />
        <Stat label="Per completed form" value={inr(c.per_completed_form_inr)} sub={c.per_completed_form_usd != null ? usd(c.per_completed_form_usd) : "form not completed"} />
        <Stat label="1,000 similar calls" value={inr(c.projection_1000_inr)} sub={usd(c.projection_1000_usd)} />
      </div>
      <div className="mt-3">
        <Table
          head={["Item", "Quantity", "Rate", "USD", "INR"]}
          rows={c.items.map((i) => [
            i.label,
            <span className="tabular-nums">{i.quantity.toLocaleString()} {i.unit}</span>,
            <span className="tabular-nums">{i.rate_currency === "INR" ? "₹" : "$"}{i.rate}</span>,
            <span className="tabular-nums">{usd(i.cost_usd)}</span>,
            <span className="tabular-nums">{inr(i.cost_inr)}</span>,
          ])}
        />
      </div>
    </Section>
  );
}
