import { orDash } from "../utils/format";

export function Field({ label, value, hint }: { label: string; value: string | number | null | undefined; hint?: string }) {
  return (
    <div title={hint}>
      <dt className="text-[11px] uppercase tracking-wide text-muted">{label}</dt>
      <dd className="font-mono text-sm">{orDash(value)}</dd>
    </div>
  );
}

export function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-line bg-panel px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className="font-mono text-sm">{value}</div>
    </div>
  );
}
