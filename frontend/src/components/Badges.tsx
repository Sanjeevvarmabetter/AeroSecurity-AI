import type { Severity, WorkflowStatus } from "../types/anomaly";
import type { CaseStatus } from "../types/investigation";

const SEV: Record<Severity, string> = {
  CRITICAL: "border-sev-critical/60 bg-sev-critical/15 text-sev-critical",
  HIGH: "border-sev-high/60 bg-sev-high/15 text-sev-high",
  MEDIUM: "border-sev-medium/60 bg-sev-medium/15 text-sev-medium",
  LOW: "border-sev-low/60 bg-sev-low/15 text-sev-low",
};

const ST: Record<string, string> = {
  OPEN: "border-accent/50 text-accent",
  NEW: "border-accent/50 text-accent",
  INVESTIGATING: "border-sev-medium/50 text-sev-medium",
  IN_PROGRESS: "border-sky-400/50 text-sky-400",
  UNDER_REVIEW: "border-amber-400/50 text-amber-400",
  ESCALATED: "border-rose-400/50 text-rose-400",
  FALSE_POSITIVE: "border-line text-muted",
  RESOLVED: "border-ok/50 text-ok",
  CLOSED: "border-ok/50 text-ok",
};

export const SeverityBadge = ({ severity }: { severity: Severity }) => (
  <span className={`inline-block rounded border px-1.5 py-0.5 text-[11px] font-semibold ${SEV[severity] ?? "border-line text-muted"}`}>
    {severity}
  </span>
);

export const WorkflowBadge = ({ status }: { status: WorkflowStatus | CaseStatus | string }) => (
  <span className={`inline-block whitespace-nowrap rounded border px-1.5 py-0.5 text-[11px] font-medium ${ST[status] ?? "border-line text-muted"}`}>
    {status.replace(/_/g, " ")}
  </span>
);

export const QualityBadge = ({ quality }: { quality: string }) => (
  <span className={`text-[11px] ${quality === "GOOD" ? "text-ok" : quality === "PARTIAL" ? "text-sev-medium" : "text-sev-high"}`} title="Quality of the data the finding relied on">
    {quality}
  </span>
);
