import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { SeverityBadge, WorkflowBadge } from "../components/Badges";
import { ErrorNote, NeedsToken } from "../components/QueryNotice";
import { createCase, getCases } from "../services/api";
import type { CaseItem, CaseSeverity } from "../types/investigation";
import { fmtTime } from "../utils/format";

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All Statuses" },
  { value: "NEW", label: "New" },
  { value: "IN_PROGRESS", label: "In Progress" },
  { value: "UNDER_REVIEW", label: "Under Review" },
  { value: "ESCALATED", label: "Escalated" },
  { value: "CLOSED", label: "Closed" },
  { value: "FALSE_POSITIVE", label: "False Positive" },
];

const SEVERITY_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All Severities" },
  { value: "CRITICAL", label: "Critical" },
  { value: "HIGH", label: "High" },
  { value: "MEDIUM", label: "Medium" },
  { value: "LOW", label: "Low" },
];

export function InvestigationsPage() {
  const navigate = useNavigate();
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [severityFilter, setSeverityFilter] = useState<string>("");
  const [icaoSearch, setIcaoSearch] = useState<string>("");

  // Create Case Modal
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newIcao24, setNewIcao24] = useState("");
  const [newAnomalyId, setNewAnomalyId] = useState("");
  const [newSeverity, setNewSeverity] = useState<CaseSeverity>("MEDIUM");
  const [newInitialNote, setNewInitialNote] = useState("");
  const [newClaimedName, setNewClaimedName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const loadCases = async () => {
    setLoading(true);
    try {
      const res = await getCases({
        status: statusFilter ? [statusFilter] : undefined,
        severity: severityFilter ? [severityFilter] : undefined,
        icao24: icaoSearch.trim() || undefined,
        limit: 50,
      });
      setCases(res.items);
      setTotal(res.total);
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCases();
  }, [statusFilter, severityFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadCases();
  };

  const handleCreateCase = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      const created = await createCase({
        title: newTitle.trim(),
        description: newDescription.trim() || undefined,
        icao24: newIcao24.trim().toLowerCase() || undefined,
        anomaly_id: newAnomalyId.trim() || undefined,
        severity: newSeverity,
        initial_note: newInitialNote.trim() || undefined,
        claimed_name: newClaimedName.trim() || undefined,
      });
      setCreateModalOpen(false);
      // Reset form
      setNewTitle("");
      setNewDescription("");
      setNewIcao24("");
      setNewAnomalyId("");
      setNewSeverity("MEDIUM");
      setNewInitialNote("");
      setNewClaimedName("");
      navigate(`/investigations/${created.id}`);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create investigation case");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      <NeedsToken />
      <ErrorNote error={error} />

      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-100">
            Investigation Operations Center
          </h1>
          <p className="text-xs text-muted">
            End-to-end incident response, chain of custody evidence, forensic notes, and audit timelines ({total} cases recorded)
          </p>
        </div>
        <button
          onClick={() => setCreateModalOpen(true)}
          className="rounded-md bg-accent px-4 py-2 text-xs font-semibold text-ink shadow hover:bg-sky-400 transition-colors"
        >
          + Open New Investigation
        </button>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-panel p-3">
        {/* Status Dropdown */}
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-muted">Status:</span>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded border border-line bg-ink px-2.5 py-1 text-xs text-slate-200 focus:border-accent focus:outline-none"
          >
            {STATUS_FILTERS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        {/* Severity Dropdown */}
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-muted">Severity:</span>
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="rounded border border-line bg-ink px-2.5 py-1 text-xs text-slate-200 focus:border-accent focus:outline-none"
          >
            {SEVERITY_FILTERS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        {/* ICAO Search */}
        <form onSubmit={handleSearchSubmit} className="flex items-center gap-1.5 text-xs ml-auto">
          <input
            type="text"
            value={icaoSearch}
            onChange={(e) => setIcaoSearch(e.target.value)}
            placeholder="Filter by ICAO24 (e.g. 4d221d)..."
            className="w-48 rounded border border-line bg-ink px-2.5 py-1 text-xs text-slate-200 placeholder-muted/60 focus:border-accent focus:outline-none"
          />
          <button
            type="submit"
            className="rounded border border-line bg-card px-2.5 py-1 text-xs text-slate-300 hover:border-slate-500"
          >
            Filter
          </button>
        </form>
      </div>

      {/* Cases Table */}
      <div className="overflow-x-auto rounded-lg border border-line bg-panel shadow">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-line bg-ink/50 text-[11px] font-semibold text-muted uppercase tracking-wider">
            <tr>
              <th className="px-3 py-3">Case ID</th>
              <th className="px-3 py-3">Case Title & Finding</th>
              <th className="px-3 py-3">Severity</th>
              <th className="px-3 py-3">Status</th>
              <th className="px-3 py-3">Aircraft</th>
              <th className="px-3 py-3">Anomaly Ref</th>
              <th className="px-3 py-3">Lead Analyst</th>
              <th className="px-3 py-3">Notes</th>
              <th className="px-3 py-3">Last Updated (UTC)</th>
              <th className="px-3 py-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line/60">
            {loading ? (
              <tr>
                <td colSpan={10} className="p-8 text-center text-xs text-muted">
                  Loading investigation cases...
                </td>
              </tr>
            ) : cases.length === 0 ? (
              <tr>
                <td colSpan={10} className="p-8 text-center text-xs text-muted">
                  No investigation cases match the active filters.
                </td>
              </tr>
            ) : (
              cases.map((c) => (
                <tr key={c.id} className="hover:bg-card/40 transition-colors">
                  <td className="px-3 py-2.5 font-mono font-bold text-accent whitespace-nowrap">
                    <Link to={`/investigations/${c.id}`} className="hover:underline">
                      CASE-{c.id.toString().padStart(4, "0")}
                    </Link>
                  </td>
                  <td className="px-3 py-2.5 max-w-xs">
                    <div className="font-semibold text-slate-200 truncate">{c.title}</div>
                    {c.description && (
                      <div className="text-[11px] text-muted truncate">{c.description}</div>
                    )}
                  </td>
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    <SeverityBadge severity={c.severity as any} />
                  </td>
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    <WorkflowBadge status={c.status as any} />
                  </td>
                  <td className="px-3 py-2.5 font-mono whitespace-nowrap">
                    {c.icao24 ? (
                      <Link to={`/aircraft/${c.icao24}`} className="text-accent underline">
                        {c.icao24.toUpperCase()}
                      </Link>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 font-mono whitespace-nowrap">
                    {c.anomaly_id ? (
                      <Link to={`/anomalies/${c.anomaly_id}`} className="text-amber-400 underline">
                        {c.anomaly_id}
                      </Link>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-slate-300 whitespace-nowrap">
                    {c.lead_analyst || c.opened_by}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-slate-300 whitespace-nowrap">
                    <span className="rounded bg-line/60 px-2 py-0.5 text-[11px]">
                      {c.notes_count}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 whitespace-nowrap text-muted text-[11px]">
                    {fmtTime(c.updated_at)}
                  </td>
                  <td className="px-3 py-2.5 text-right whitespace-nowrap">
                    <Link
                      to={`/investigations/${c.id}`}
                      className="rounded border border-accent/40 bg-accent/10 px-2.5 py-1 text-[11px] font-semibold text-accent hover:bg-accent/20 transition-colors"
                    >
                      Dossier &rarr;
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Case Creation Modal */}
      {createModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-lg border border-line bg-panel p-6 shadow-2xl space-y-4">
            <div>
              <h2 className="text-base font-bold text-slate-100">Open New Investigation Case</h2>
              <p className="text-xs text-muted">
                Establish an auditable investigation dossier for security triage or forensic analysis.
              </p>
            </div>

            {createError && (
              <div className="rounded border border-red-500/30 bg-red-500/10 p-2.5 text-xs text-red-400">
                {createError}
              </div>
            )}

            <form onSubmit={handleCreateCase} className="space-y-3.5">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Case Title <span className="text-accent">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="e.g. Unscheduled Kinematic Dive over Restricted Sector"
                  className="w-full rounded border border-line bg-ink px-3 py-1.5 text-xs text-slate-200 focus:border-accent focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Aircraft ICAO24 (Optional)
                  </label>
                  <input
                    type="text"
                    pattern="^[0-9a-fA-F]{6}$"
                    value={newIcao24}
                    onChange={(e) => setNewIcao24(e.target.value)}
                    placeholder="e.g. 4d221d"
                    className="w-full rounded border border-line bg-ink px-3 py-1.5 text-xs font-mono text-slate-200 focus:border-accent focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Anomaly ID (Optional)
                  </label>
                  <input
                    type="text"
                    value={newAnomalyId}
                    onChange={(e) => setNewAnomalyId(e.target.value)}
                    placeholder="e.g. ANM-0042"
                    className="w-full rounded border border-line bg-ink px-3 py-1.5 text-xs font-mono text-slate-200 focus:border-accent focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Severity</label>
                  <select
                    value={newSeverity}
                    onChange={(e) => setNewSeverity(e.target.value as CaseSeverity)}
                    className="w-full rounded border border-line bg-ink px-3 py-1.5 text-xs text-slate-200 focus:border-accent focus:outline-none"
                  >
                    <option value="LOW">Low</option>
                    <option value="MEDIUM">Medium</option>
                    <option value="HIGH">High</option>
                    <option value="CRITICAL">Critical</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Lead Analyst Callsign
                  </label>
                  <input
                    type="text"
                    value={newClaimedName}
                    onChange={(e) => setNewClaimedName(e.target.value)}
                    placeholder="e.g. Lead Hunter"
                    className="w-full rounded border border-line bg-ink px-3 py-1.5 text-xs text-slate-200 focus:border-accent focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Description / Synopsis
                </label>
                <textarea
                  rows={2}
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="Summary of why this investigation is opened, initial radar observations..."
                  className="w-full rounded border border-line bg-ink p-2 text-xs text-slate-200 focus:border-accent focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Initial Forensic Note (Optional)
                </label>
                <textarea
                  rows={2}
                  value={newInitialNote}
                  onChange={(e) => setNewInitialNote(e.target.value)}
                  placeholder="First finding or triage instruction for responders..."
                  className="w-full rounded border border-line bg-ink p-2 text-xs text-slate-200 focus:border-accent focus:outline-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-line">
                <button
                  type="button"
                  onClick={() => setCreateModalOpen(false)}
                  className="rounded border border-line px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating || !newTitle.trim()}
                  className="rounded bg-accent px-4 py-1.5 text-xs font-semibold text-ink hover:bg-sky-400 disabled:opacity-50"
                >
                  {creating ? "Opening Case..." : "Establish Case"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
