import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ErrorNote, NeedsToken } from "../components/QueryNotice";
import { useMe } from "../hooks/useSecurity";
import { getDetectionRules, runDetection, updateDetectionRule } from "../services/api";
import type { DetectionRuleOut, DetectionRunReport } from "../types/detection";

export function DetectionRulesPage() {
  const queryClient = useQueryClient();
  const me = useMe();
  const canWrite = me.data?.role === "analyst" || me.data?.role === "admin";

  const { data: rules, error, isLoading } = useQuery({
    queryKey: ["detection-rules"],
    queryFn: getDetectionRules,
  });

  const [selectedRule, setSelectedRule] = useState<DetectionRuleOut | null>(null);
  const [configJson, setConfigJson] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [runReport, setRunReport] = useState<DetectionRunReport | null>(null);

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      updateDetectionRule(id, { enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["detection-rules"] }),
  });

  const saveConfigMutation = useMutation({
    mutationFn: ({ id, config }: { id: string; config: Record<string, unknown> }) =>
      updateDetectionRule(id, { config }),
    onSuccess: (updated) => {
      setSelectedRule(updated);
      setSaveError(null);
      queryClient.invalidateQueries({ queryKey: ["detection-rules"] });
    },
    onError: (err: any) => setSaveError(err.message || "Failed to update configuration"),
  });

  const runMutation = useMutation({
    mutationFn: () => runDetection(),
    onSuccess: (res) => {
      setRunReport(res);
      queryClient.invalidateQueries({ queryKey: ["detection-rules"] });
      queryClient.invalidateQueries({ queryKey: ["overview-analytics"] });
    },
  });

  const openConfigModal = (rule: DetectionRuleOut) => {
    setSelectedRule(rule);
    setConfigJson(JSON.stringify(rule.config, null, 2));
    setSaveError(null);
  };

  return (
    <section className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line/60 pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            <span>Detection Engine & Rule Architecture</span>
            <span className="rounded bg-accent/15 px-2 py-0.5 text-xs font-mono text-accent">
              DETERMINISTIC
            </span>
          </h1>
          <p className="mt-1 text-xs text-muted">
            Versioned, pure-function cyber-physical detection rules. AI models never invent, modify, or suppress verdicts.
          </p>
        </div>

        {canWrite && (
          <button
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
            className="flex items-center gap-2 rounded bg-accent px-3 py-1.5 text-xs font-semibold text-ink shadow-md hover:bg-accent/90 disabled:opacity-50 transition-all"
          >
            {runMutation.isPending ? (
              <>
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-ink border-t-transparent" />
                <span>Running Detection...</span>
              </>
            ) : (
              <>
                <span>▶</span>
                <span>Execute Detection Run</span>
              </>
            )}
          </button>
        )}
      </div>

      <NeedsToken />
      <ErrorNote error={error} />

      {/* Detection Run Status Banner */}
      {runReport && (
        <div className="rounded border border-ok/40 bg-ok/10 p-4 text-xs text-slate-200 shadow-md">
          <div className="flex items-center justify-between mb-2">
            <strong className="text-ok font-semibold">Detection Engine Run Completed Successfully</strong>
            <button onClick={() => setRunReport(null)} className="text-muted hover:text-white">✕</button>
          </div>
          <div className="grid grid-cols-3 gap-3 font-mono text-[11px]">
            <div>Aircraft Processed: <span className="font-bold text-white">{runReport.aircraft_processed}</span></div>
            <div>Airports Evaluated: <span className="font-bold text-white">{runReport.airports_processed}</span></div>
            <div>Observations Scanned: <span className="font-bold text-white">{runReport.observations_read.toLocaleString()}</span></div>
          </div>
        </div>
      )}

      {isLoading && (
        <div className="flex h-64 items-center justify-center rounded border border-line bg-panel">
          <div className="flex flex-col items-center gap-2">
            <span className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            <span className="text-xs font-mono text-muted">Loading detection rule catalog...</span>
          </div>
        </div>
      )}

      {/* Rules Grid */}
      {rules && (
        <div className="grid gap-4 md:grid-cols-2">
          {rules.map((rule) => (
            <div
              key={rule.id}
              className={`rounded border p-4 shadow-sm transition-all ${
                rule.enabled ? "border-line bg-panel" : "border-line/40 bg-panel/50 opacity-70"
              }`}
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-accent">{rule.id}</span>
                    <span className="rounded bg-subpanel px-1.5 py-0.5 text-[10px] font-mono text-muted">
                      v{rule.version}
                    </span>
                    <span className="rounded bg-subpanel px-1.5 py-0.5 text-[10px] font-semibold text-slate-300">
                      {rule.category}
                    </span>
                  </div>
                  <h2 className="text-sm font-bold text-white mt-1">{rule.name}</h2>
                </div>

                <div className="flex items-center gap-2">
                  <span
                    className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                      rule.enabled ? "bg-ok/20 text-ok" : "bg-muted/20 text-muted"
                    }`}
                  >
                    {rule.enabled ? "ENABLED" : "DISABLED"}
                  </span>
                  {canWrite && (
                    <button
                      onClick={() => toggleMutation.mutate({ id: rule.id, enabled: !rule.enabled })}
                      className="rounded border border-line px-2 py-0.5 text-[10px] text-muted hover:border-accent hover:text-accent"
                    >
                      {rule.enabled ? "Disable" : "Enable"}
                    </button>
                  )}
                </div>
              </div>

              <p className="text-xs text-muted leading-relaxed mb-4">{rule.description}</p>

              <div className="flex items-center justify-between border-t border-line/60 pt-3 text-xs">
                <div className="font-mono text-slate-300">
                  Total Detections:{" "}
                  <span className="font-bold text-accent">{rule.findings_count}</span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => openConfigModal(rule)}
                    className="rounded border border-line bg-subpanel px-2.5 py-1 text-[11px] font-medium text-slate-300 hover:border-accent hover:text-accent"
                  >
                    Inspect Config ({Object.keys(rule.config).length})
                  </button>
                  <Link
                    to={`/anomalies?rule_id=${rule.id}`}
                    className="rounded bg-accent/15 px-2.5 py-1 text-[11px] font-medium text-accent hover:bg-accent/25"
                  >
                    View Hits →
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Threshold & Config Modal */}
      {selectedRule && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded border border-line bg-panel p-5 shadow-2xl space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-base font-bold text-white flex items-center gap-2 font-mono">
                  <span>{selectedRule.id}</span>
                  <span className="text-sm font-sans font-medium text-slate-300">
                    {selectedRule.name}
                  </span>
                </h3>
                <div className="text-xs text-muted mt-0.5">
                  Version {selectedRule.version} · {selectedRule.category}
                </div>
              </div>
              <button
                onClick={() => setSelectedRule(null)}
                className="text-muted hover:text-white font-mono text-sm"
              >
                ✕
              </button>
            </div>

            {saveError && (
              <div className="rounded bg-sev-critical/10 p-2 text-xs text-sev-critical border border-sev-critical/30">
                {saveError}
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-muted mb-1">
                Thresholds & Parameters (JSONB)
              </label>
              <textarea
                value={configJson}
                onChange={(e) => setConfigJson(e.target.value)}
                disabled={!canWrite}
                rows={9}
                className="w-full rounded border border-line bg-ink p-2.5 font-mono text-xs text-slate-200 focus:border-accent"
              />
            </div>

            <div className="flex items-center justify-between text-xs border-t border-line/60 pt-3">
              <span className="text-[11px] text-muted">
                {canWrite ? "Strict Pydantic schema validation enforced." : "Read-only access."}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setSelectedRule(null)}
                  className="rounded border border-line px-3 py-1.5 text-muted hover:bg-subpanel"
                >
                  Close
                </button>
                {canWrite && (
                  <button
                    onClick={() => {
                      try {
                        const parsed = JSON.parse(configJson);
                        saveConfigMutation.mutate({ id: selectedRule.id, config: parsed });
                      } catch {
                        setSaveError("Invalid JSON syntax.");
                      }
                    }}
                    disabled={saveConfigMutation.isPending}
                    className="rounded bg-accent px-3 py-1.5 font-semibold text-ink hover:bg-accent/90 disabled:opacity-50"
                  >
                    Save Thresholds
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
