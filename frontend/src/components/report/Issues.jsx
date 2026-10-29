// Section 9: problems found, sorted by severity, each with a suggestion.

import { Badge, Empty, Section, severityTone } from "./ui";

export default function Issues({ report }) {
  return (
    <Section number={9} title="Issues and recommendations">
      {report.issues.length === 0 ? (
        <Empty>No issues found.</Empty>
      ) : (
        <ul className="space-y-2">
          {report.issues.map((i, n) => (
            <li key={n} className="rounded-lg border border-slate-200 p-2 text-sm dark:border-slate-800">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={severityTone(i.severity)}>{i.severity}</Badge>
                <span className="font-medium">{i.title}</span>
              </div>
              <p className="mt-1 text-slate-600 dark:text-slate-400">{i.detail}</p>
              <p className="mt-1">→ {i.suggestion}</p>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
