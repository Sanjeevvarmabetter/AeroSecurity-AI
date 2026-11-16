import { ErrorNote, NeedsToken } from "../components/QueryNotice";
import { useDataSources } from "../hooks/useAviation";
import { fmtTime } from "../utils/format";

export function DataSourcesPage() {
  const { data, error } = useDataSources();
  return (
    <section>
      <h1 className="mb-3 text-lg font-semibold">Data Sources</h1>
      <NeedsToken />
      <ErrorNote error={error} />
      {data && (
        <div className="overflow-x-auto rounded border border-line">
          <table className="w-full text-left text-sm">
            <thead className="bg-panel text-xs text-muted">
              <tr>{["Source", "Kind", "State", "Last success", "Last error", "Terms"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody>
              {data.map((s) => (
                <tr key={s.name} className="border-t border-line align-top">
                  <td className="px-3 py-2 font-mono">{s.name}</td>
                  <td className="px-3">{s.kind}</td>
                  <td className={`px-3 ${s.enabled ? "text-ok" : "text-muted"}`}>{s.enabled ? "enabled" : "disabled"}</td>
                  <td className="px-3 text-xs">{s.last_success_at ? fmtTime(s.last_success_at) : "never"}</td>
                  <td className="px-3 text-xs text-sev-medium">{s.last_error ? `${fmtTime(s.last_error_at)} — ${s.last_error}` : "—"}</td>
                  <td className="px-3 text-xs">{s.terms_url ? <a className="text-accent underline" href={s.terms_url} target="_blank" rel="noreferrer noopener">terms</a> : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
