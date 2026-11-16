import type { Status } from "../types/health";

const STYLE: Record<Status, string> = {
  ok: "text-ok border-ok/40",
  degraded: "text-sev-medium border-sev-medium/40",
  down: "text-sev-critical border-sev-critical/40",
};

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={`rounded border px-2 py-0.5 text-xs font-medium uppercase ${STYLE[status]}`}>{status}</span>
  );
}
