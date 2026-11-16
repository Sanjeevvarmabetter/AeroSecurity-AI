import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { SeverityBadge, WorkflowBadge } from "../components/Badges";
import { ErrorNote, NeedsToken } from "../components/QueryNotice";
import { addCaseNote, getCaseDetail, updateCaseStatus } from "../services/api";
import type { CaseDetail, CaseStatus } from "../types/investigation";
import { fmtTime } from "../utils/format";

const ALL_STATUSES: { value: CaseStatus; label: string; desc: string }[] = [
  { value: "NEW", label: "New", desc: "Newly created case pending triage" },
  { value: "IN_PROGRESS", label: "In Progress", desc: "Active investigation underway" },
  { value: "UNDER_REVIEW", label: "Under Review", desc: "Awaiting senior analyst review" },
  { value: "ESCALATED", label: "Escalated", desc: "Escalated for immediate SOC / ATC action" },
  { value: "CLOSED", label: "Closed", desc: "Investigation resolved and finalized" },
  { value: "FALSE_POSITIVE", label: "False Positive", desc: "Determined to be sensor artifact or benign anomaly" },
];

export function InvestigationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const caseId = Number(id);

  const [caseData, setCaseData] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  // Status modal
  const [statusModalOpen, setStatusModalOpen] = useState(false);
  const [nextStatus, setNextStatus] = useState<CaseStatus>("IN_PROGRESS");
  const [statusReason, setStatusReason] = useState("");
  const [analystName, setAnalystName] = useState("");
  const [statusSubmitting, setStatusSubmitting] = useState(false);

  // Note form
  const [noteBody, setNoteBody] = useState("");
  const [noteAuthor, setNoteAuthor] = useState("");
  const [noteSubmitting, setNoteSubmitting] = useState(false);

  const loadCase = async () => {
    if (isNaN(caseId)) return;
    setLoading(true);
    try {
      const data = await getCaseDetail(caseId);
      setCaseData(data);
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCase();
  }, [caseId]);

  const handleStatusUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!caseData) return;
    setStatusSubmitting(true);
    try {
      const updated = await updateCaseStatus(caseData.id, {
        status: nextStatus,
        reason: statusReason.trim() || undefined,
        claimed_name: analystName.trim() || undefined,
      });
      setCaseData(updated);
      setStatusModalOpen(false);
      setStatusReason("");
    } catch (err) {
      setError(err);
    } finally {
      setStatusSubmitting(false);
    }
  };

  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!caseData || !noteBody.trim()) return;
    setNoteSubmitting(true);
    try {
      await addCaseNote(caseData.id, {
        body: noteBody.trim(),
        claimed_name: noteAuthor.trim() || undefined,
      });
      setNoteBody("");
      await loadCase();
    } catch (err) {
      setError(err);
    } finally {
      setNoteSubmitting(false);
    }
  };

  const handleExportMarkdown = () => {
    if (!caseData) return;
    const lines = [
      `# Case Dossier: CASE-${caseData.id.toString().padStart(4, "0")} - ${caseData.title}`,
      ``,
      `**Status**: ${caseData.status} | **Severity**: ${caseData.severity}`,
      `**Opened By**: ${caseData.opened_by} at ${fmtTime(caseData.opened_at)}`,
      `**Last Updated**: ${fmtTime(caseData.updated_at)}`,
      caseData.closed_at ? `**Closed At**: ${fmtTime(caseData.closed_at)}` : "",
      caseData.lead_analyst ? `**Lead Analyst**: ${caseData.lead_analyst}` : "",
      ``,
      `## Overview`,
      caseData.description || "No description provided.",
      ``,
      `## Associated Entities`,
      caseData.icao24 ? `- **Aircraft ICAO24**: ${caseData.icao24}` : "- Aircraft: Not linked",
      caseData.anomaly_id ? `- **Anomaly Reference**: ${caseData.anomaly_id} (${caseData.anomaly_title || ""})` : "- Anomaly: Standalone case",
      ``,
      `## Investigation Notes (${caseData.notes.length})`,
      ...caseData.notes.map(
        (n) => `### [${fmtTime(n.created_at)}] ${n.author}${n.claimed_name ? ` (${n.claimed_name})` : ""}\n\n${n.body}\n`
      ),
      ``,
      `## Audit Timeline (${caseData.timeline.length} events)`,
      ...caseData.timeline.map(
        (t) => `- **${fmtTime(t.timestamp)}** [${t.actor}]: ${t.action} - ${JSON.stringify(t.details)}`
      ),
    ].filter(Boolean);

    const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `case-${caseData.id}-dossier.md`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent mx-auto mb-2" />
          <p className="text-xs text-muted">Loading case intelligence dossier...</p>
        </div>
      </div>
    );
  }

  if (!caseData) {
    return (
      <div className="rounded border border-line bg-panel p-6 text-center">
        <p className="text-sm text-red-400">Case not found or failed to load.</p>
        <Link to="/investigations" className="mt-4 inline-block text-xs text-accent underline">
          Return to Investigation Center
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <NeedsToken />
      <ErrorNote error={error} />

      {/* Breadcrumb & Navigation */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-muted">
          <Link to="/investigations" className="hover:text-accent">
            Investigations
          </Link>
          <span>/</span>
          <span className="font-mono text-slate-300">CASE-{caseData.id.toString().padStart(4, "0")}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setNextStatus(caseData.status);
              setStatusModalOpen(true);
            }}
            className="rounded border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent hover:bg-accent/20 transition-colors"
          >
            Update Status
          </button>
          <button
            onClick={handleExportMarkdown}
            className="rounded border border-line bg-card px-3 py-1.5 text-xs text-slate-300 hover:border-slate-500 transition-colors"
          >
            Export Dossier (.md)
          </button>
        </div>
      </div>

      {/* Header Banner */}
      <div className="rounded-lg border border-line bg-panel p-5 shadow-lg">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <span className="font-mono text-sm font-bold text-accent">
                CASE-{caseData.id.toString().padStart(4, "0")}
              </span>
              <WorkflowBadge status={caseData.status} />
              <SeverityBadge severity={caseData.severity} />
            </div>
            <h1 className="text-xl font-bold text-slate-100">{caseData.title}</h1>
            {caseData.description && (
              <p className="text-xs text-slate-400 max-w-3xl leading-relaxed">{caseData.description}</p>
            )}
          </div>

          {/* Metadata Block */}
          <div className="rounded border border-line/60 bg-ink/50 p-3 text-xs space-y-1.5 min-w-[240px]">
            <div className="flex justify-between">
              <span className="text-muted">Lead Analyst:</span>
              <span className="font-mono text-slate-300">{caseData.lead_analyst || caseData.opened_by}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Opened:</span>
              <span className="font-mono text-slate-300">{fmtTime(caseData.opened_at)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Updated:</span>
              <span className="font-mono text-slate-300">{fmtTime(caseData.updated_at)}</span>
            </div>
            {caseData.closed_at && (
              <div className="flex justify-between">
                <span className="text-muted">Closed:</span>
                <span className="font-mono text-emerald-400">{fmtTime(caseData.closed_at)}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Linked Entities Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Linked Aircraft */}
        <div className="rounded border border-line bg-panel p-4">
          <div className="flex items-center justify-between mb-3 border-b border-line/60 pb-2">
            <h2 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
              Linked Aircraft Intelligence
            </h2>
            {caseData.icao24 && (
              <Link
                to={`/aircraft/${caseData.icao24}`}
                className="text-[11px] text-accent hover:underline"
              >
                Full Aircraft Profile &rarr;
              </Link>
            )}
          </div>
          {caseData.icao24 ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs text-muted block">ICAO24 Transponder</span>
                  <span className="font-mono text-base font-bold text-accent">{caseData.icao24.toUpperCase()}</span>
                </div>
                {caseData.aircraft_summary && (
                  <span className="rounded bg-sky-500/10 border border-sky-500/30 px-2 py-0.5 text-[11px] font-mono text-sky-400">
                    {String(caseData.aircraft_summary.category || "UNKNOWN")}
                  </span>
                )}
              </div>

              {caseData.aircraft_summary && (
                <div className="grid grid-cols-2 gap-2 text-xs pt-2 border-t border-line/40">
                  <div>
                    <span className="text-muted block text-[10px]">Registration / Type</span>
                    <span className="font-mono text-slate-200">
                      {String(caseData.aircraft_summary.registration || "—")} /{" "}
                      {String(caseData.aircraft_summary.model || caseData.aircraft_summary.typecode || "—")}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted block text-[10px]">Operator / Country</span>
                    <span className="text-slate-200 truncate block">
                      {String(caseData.aircraft_summary.operator || "—")} (
                      {String(caseData.aircraft_summary.country || "—")})
                    </span>
                  </div>
                  <div>
                    <span className="text-muted block text-[10px]">Observations</span>
                    <span className="font-mono text-slate-200">
                      {Number(caseData.aircraft_summary.observations_count || 0).toLocaleString()}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted block text-[10px]">Kinematic Trajectory</span>
                    <Link
                      to={`/trajectories?icao24=${caseData.icao24}`}
                      className="text-accent underline text-[11px]"
                    >
                      Analyze Kinematics
                    </Link>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-muted py-4 text-center">No aircraft directly attached to this case.</p>
          )}
        </div>

        {/* Linked Anomaly */}
        <div className="rounded border border-line bg-panel p-4">
          <div className="flex items-center justify-between mb-3 border-b border-line/60 pb-2">
            <h2 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
              Triggering Anomaly Evidence
            </h2>
            {caseData.anomaly_id && (
              <Link
                to={`/anomalies/${caseData.anomaly_id}`}
                className="text-[11px] text-accent hover:underline"
              >
                Inspect Anomaly &rarr;
              </Link>
            )}
          </div>
          {caseData.anomaly_id ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs text-muted block">Detection ID</span>
                  <span className="font-mono text-sm font-bold text-amber-400">{caseData.anomaly_id}</span>
                </div>
                {caseData.anomaly_summary && (
                  <span className="rounded bg-amber-500/10 border border-amber-500/30 px-2 py-0.5 text-[11px] font-mono text-amber-300">
                    Confidence: {Number(caseData.anomaly_summary.confidence || 0).toFixed(2)}
                  </span>
                )}
              </div>
              <p className="text-xs font-medium text-slate-200">
                {caseData.anomaly_title || (caseData.anomaly_summary ? String(caseData.anomaly_summary.title) : "—")}
              </p>

              {caseData.anomaly_summary && (
                <div className="grid grid-cols-2 gap-2 text-xs pt-2 border-t border-line/40">
                  <div>
                    <span className="text-muted block text-[10px]">Rule ID</span>
                    <span className="font-mono text-slate-300 text-[11px]">
                      {String(caseData.anomaly_summary.rule_id || "—")}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted block text-[10px]">Detection Type</span>
                    <span className="font-mono text-slate-300 text-[11px]">
                      {String(caseData.anomaly_summary.detection_type || "—")}
                    </span>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-muted py-4 text-center">
              This is a standalone intelligence case (not bound to a single detection).
            </p>
          )}
        </div>
      </div>

      {/* Main Investigation Columns: Notes & Timeline */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column (2 spans): Case Notes & Add Note */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between border-b border-line pb-2">
            <h2 className="text-sm font-semibold text-slate-200">
              Analyst Notes & Findings ({caseData.notes.length})
            </h2>
            <span className="text-xs text-muted">Chronological investigation entries</span>
          </div>

          {/* Add Note Card */}
          <form onSubmit={handleAddNote} className="rounded-lg border border-line bg-panel p-4 space-y-3">
            <h3 className="text-xs font-semibold text-slate-300">Add Case Note</h3>
            <textarea
              required
              rows={3}
              value={noteBody}
              onChange={(e) => setNoteBody(e.target.value)}
              placeholder="Record forensic observation, verification results, hypothesis, or interview notes..."
              className="w-full rounded border border-line bg-ink p-2.5 text-xs text-slate-200 placeholder-muted/60 focus:border-accent focus:outline-none"
            />
            <div className="flex items-center justify-between">
              <input
                type="text"
                value={noteAuthor}
                onChange={(e) => setNoteAuthor(e.target.value)}
                placeholder="Analyst callsign (optional)"
                className="w-48 rounded border border-line bg-ink px-2.5 py-1 text-xs text-slate-200 placeholder-muted/60 focus:border-accent focus:outline-none"
              />
              <button
                type="submit"
                disabled={noteSubmitting || !noteBody.trim()}
                className="rounded bg-accent px-3 py-1.5 text-xs font-semibold text-ink hover:bg-sky-400 disabled:opacity-50 transition-colors"
              >
                {noteSubmitting ? "Adding..." : "Post Note"}
              </button>
            </div>
          </form>

          {/* Notes Feed */}
          <div className="space-y-3">
            {caseData.notes.length === 0 ? (
              <p className="rounded border border-line/60 bg-panel/50 p-6 text-center text-xs text-muted">
                No notes posted yet. Use the form above to log analyst remarks.
              </p>
            ) : (
              caseData.notes.map((note) => (
                <div key={note.id} className="rounded-lg border border-line bg-panel p-4 space-y-2">
                  <div className="flex items-center justify-between text-xs border-b border-line/40 pb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-accent">{note.author}</span>
                      {note.claimed_name && (
                        <span className="text-[11px] text-muted">({note.claimed_name})</span>
                      )}
                    </div>
                    <span className="font-mono text-muted text-[11px]">{fmtTime(note.created_at)}</span>
                  </div>
                  <p className="text-xs text-slate-200 whitespace-pre-wrap leading-relaxed">
                    {note.body}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Column: Immutable Audit Timeline */}
        <div className="space-y-4">
          <div className="border-b border-line pb-2">
            <h2 className="text-sm font-semibold text-slate-200">
              Audit Timeline ({caseData.timeline.length})
            </h2>
            <p className="text-[11px] text-muted">Cryptographically audited action log</p>
          </div>

          <div className="relative pl-6 space-y-6 before:absolute before:bottom-0 before:left-2 before:top-2 before:w-0.5 before:bg-line">
            {caseData.timeline.map((evt, idx) => (
              <div key={idx} className="relative group">
                {/* Dot */}
                <div className="absolute -left-[21px] top-1 h-3 w-3 rounded-full border-2 border-line bg-ink group-hover:border-accent" />
                <div className="rounded border border-line bg-panel p-3 text-xs space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-semibold text-slate-200 text-[11px]">
                      {evt.action.replace(/_/g, " ").toUpperCase()}
                    </span>
                    <span className="text-[10px] text-muted">{fmtTime(evt.timestamp)}</span>
                  </div>
                  <div className="text-[11px] text-muted">
                    Actor: <span className="font-mono text-slate-300">{evt.actor}</span>
                  </div>
                  {evt.details && Object.keys(evt.details).length > 0 && (
                    <div className="mt-1 rounded bg-ink/70 p-2 font-mono text-[10px] text-slate-400 overflow-x-auto">
                      {Object.entries(evt.details).map(([k, v]) => (
                        <div key={k}>
                          <span className="text-muted">{k}:</span> {String(v)}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Status Transition Modal */}
      {statusModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-lg border border-line bg-panel p-6 shadow-2xl">
            <h3 className="text-base font-bold text-slate-100 mb-1">Update Case Workflow Status</h3>
            <p className="text-xs text-muted mb-4">
              Advancing workflow state records an immutable audit trail entry.
            </p>

            <form onSubmit={handleStatusUpdate} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">New Status</label>
                <div className="space-y-1.5">
                  {ALL_STATUSES.map((st) => (
                    <label
                      key={st.value}
                      className={`flex items-start gap-2.5 p-2 rounded border cursor-pointer transition-colors ${
                        nextStatus === st.value
                          ? "border-accent bg-accent/10"
                          : "border-line bg-ink/50 hover:border-slate-600"
                      }`}
                    >
                      <input
                        type="radio"
                        name="status"
                        value={st.value}
                        checked={nextStatus === st.value}
                        onChange={() => setNextStatus(st.value)}
                        className="mt-0.5"
                      />
                      <div>
                        <div className="text-xs font-semibold text-slate-200">{st.label}</div>
                        <div className="text-[11px] text-muted">{st.desc}</div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Reason for Transition (Optional)
                </label>
                <input
                  type="text"
                  value={statusReason}
                  onChange={(e) => setStatusReason(e.target.value)}
                  placeholder="e.g., Confirmed trajectory jump matches GPS multipath reflection"
                  className="w-full rounded border border-line bg-ink px-3 py-1.5 text-xs text-slate-200 focus:border-accent focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Analyst Callsign (Optional)
                </label>
                <input
                  type="text"
                  value={analystName}
                  onChange={(e) => setAnalystName(e.target.value)}
                  placeholder="e.g., S. Varma (Lead Analyst)"
                  className="w-full rounded border border-line bg-ink px-3 py-1.5 text-xs text-slate-200 focus:border-accent focus:outline-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-line">
                <button
                  type="button"
                  onClick={() => setStatusModalOpen(false)}
                  className="rounded border border-line px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={statusSubmitting}
                  className="rounded bg-accent px-4 py-1.5 text-xs font-semibold text-ink hover:bg-sky-400 disabled:opacity-50"
                >
                  {statusSubmitting ? "Updating..." : "Confirm Transition"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
