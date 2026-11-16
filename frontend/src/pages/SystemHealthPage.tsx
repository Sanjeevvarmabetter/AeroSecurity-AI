import { StatusBadge } from "../components/StatusBadge";
import { useHealth } from "../hooks/useHealth";

export function SystemHealthPage() {
  const { data, isLoading, isError } = useHealth();

  return (
    <section>
      <h1 className="mb-4 text-lg font-semibold">System Health</h1>
      {isLoading && <p className="text-muted">Checking…</p>}
      {isError && (
        <p role="alert" className="text-sev-critical">
          Backend unreachable. No health data is available.
        </p>
      )}
      {data && (
        <div className="max-w-xl rounded border border-line bg-panel">
          <div className="flex items-center justify-between border-b border-line p-3">
            <span>
              API <span className="text-muted">v{data.version} · {data.environment}</span>
            </span>
            <StatusBadge status={data.status} />
          </div>
          {Object.entries(data.components).map(([name, c]) => (
            <div key={name} className="flex items-center justify-between border-b border-line p-3 last:border-0">
              <span className="capitalize">
                {name} {c.detail && <span className="text-xs text-muted">{c.detail}</span>}
              </span>
              <StatusBadge status={c.status} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
