import { useEffect, useState } from "react";

import { useAISettings, useAnalyses, useRunAnalysis } from "../hooks/useAI";
import { useMe } from "../hooks/useSecurity";
import type { Analysis, ProviderName } from "../types/ai";
import { fmtTime } from "../utils/format";
import { ErrorNote } from "./QueryNotice";

type Out = Record<string, unknown>;
const list = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

function scrollToEvidence(ref: string) {
  const m = /^E(\d+)$/.exec(ref);
  if (!m) return;
  const el = document.getElementById(`ev-${m[1]}`);
  el?.scrollIntoView({ behavior: "smooth", block: "center" });
  el?.classList.add("bg-accent/20");
  setTimeout(() => el?.classList.remove("bg-accent/20"), 1800);
}

const Chip = ({ r }: { r: string }) => (
  <button type="button" onClick={() => scrollToEvidence(r)} className="rounded border border-accent/40 px-1 font-mono text-[11px] text-accent hover:bg-accent/10" title="Evidence reference. E-refs jump to the evidence table">
    {r}
  </button>
);
const Bullets = ({ title, items }: { title: string; items: string[] }) =>
  items.length ? (
    <div>
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">{title}</h4>
      <ul className="list-disc space-y-1 pl-5 text-sm">{items.map((x, i) => <li key={i}>{x}</li>)}</ul>
    </div>
  ) : null;
const Block = ({ title, text }: { title: string; text: unknown }) =>
  typeof text === "string" && text ? (
    <div>
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">{title}</h4>
      <p className="text-sm">{text}</p>
    </div>
  ) : null;

function AnomalyResult({ o }: { o: Out }) {
  const ev = Array.isArray(o.supporting_evidence) ? (o.supporting_evidence as { ref: string; note?: string }[]) : [];
  return (
    <div className="space-y-3">
      <Block title="What happened" text={o.what_happened} />
      <Block title="Rule triggered" text={o.rule_triggered} />
      {ev.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Supporting evidence cited</h4>
          <ul className="space-y-1 text-sm">{ev.map((e, i) => <li key={i}><Chip r={e.ref} /> {e.note}</li>)}</ul>
        </div>
      )}
      <Bullets title="Alternative explanations" items={list(o.alternative_explanations)} />
      <Block title="Why it may matter" text={o.why_it_may_matter} />
      <Bullets title="Suggested next steps" items={list(o.next_steps)} />
      <Bullets title="Limitations" items={list(o.limitations)} />
    </div>
  );
}

function AircraftResult({ o }: { o: Out }) {
  const obs = Array.isArray(o.unusual_observations) ? (o.unusual_observations as { text: string; refs?: string[] }[]) : [];
  return (
    <div className="space-y-3">
      <Block title="Activity summary" text={o.activity_summary} />
      {obs.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Unusual observations</h4>
          <ul className="space-y-1 text-sm">{obs.map((x, i) => <li key={i}>{x.text} {(x.refs ?? []).map((r) => <Chip key={r} r={r} />)}</li>)}</ul>
        </div>
      )}
      <Bullets title="Possible explanations" items={list(o.possible_explanations)} />
      <Bullets title="Security implications" items={list(o.security_implications)} />
      <Bullets title="Recommendations" items={list(o.recommendations)} />
      <Bullets title="Limitations" items={list(o.limitations)} />
      {list(o.evidence_refs).length > 0 && <p className="text-xs text-muted">Evidence referenced: {list(o.evidence_refs).map((r) => <span key={r}><Chip r={r} />{" "}</span>)}</p>}
    </div>
  );
}

function Result({ a }: { a: Analysis }) {
  return (
    <div className="space-y-3 rounded border border-accent/30 bg-ink p-3">
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <span className="rounded bg-accent/20 px-1.5 py-0.5 font-semibold tracking-wide text-accent">AI-GENERATED INTERPRETATION</span>
        <span className="text-muted">not a verified finding</span>
        <span className="ml-auto font-mono text-muted">{a.provider} · {a.model} · {a.prompt_version}{a.latency_ms != null && ` · ${(a.latency_ms / 1000).toFixed(0)} s`}{a.completion_tokens != null && ` · ${a.completion_tokens} tok`}</span>
      </div>
      {a.deterministic && (
        <p className="text-xs text-muted">Deterministic detection (unchanged by AI): <span className="font-mono">{a.deterministic.rule} · {a.deterministic.severity} · confidence {a.deterministic.confidence.toFixed(2)} · {a.deterministic.status}</span></p>
      )}
      {a.warnings.map((w) => <p key={w} className="rounded border border-sev-medium/40 bg-sev-medium/10 p-2 text-xs text-sev-medium">⚠ {w}</p>)}
      {a.output && (a.kind === "anomaly_explanation" ? <AnomalyResult o={a.output} /> : a.kind === "threat_correlation" ? <CorrelationResult o={a.output} /> : <AircraftResult o={a.output} />)}
      <p className="text-[11px] text-muted">Generated {fmtTime(a.created_at)} for <span className="font-mono">{a.requested_by}</span>. Verify against the evidence before acting.</p>
    </div>
  );
}

const KIND_OF = { anomaly: "anomaly_explanation", aircraft: "aircraft_investigation", correlation: "threat_correlation" } as const;
const TITLE = { anomaly: "AI explanation", aircraft: "AI investigation assistant", correlation: "Threat-intelligence correlation (AI)" } as const;
const CTA = { anomaly: "Explain with AI", aircraft: "Investigate with AI", correlation: "Correlate with threat intel" } as const;

type Finding = { text: string; refs?: string[] };
const asFindings = (v: unknown): Finding[] => (Array.isArray(v) ? (v as Finding[]) : []);

function Layer({ title, tone, items }: { title: string; tone: string; items: Finding[] }) {
  if (!items.length) return null;
  return (
    <div className={`rounded border-l-2 pl-3 ${tone}`}>
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide">{title}</h4>
      <ul className="space-y-1 text-sm text-slate-200">{items.map((f, i) => <li key={i}>{f.text} {(f.refs ?? []).map((r) => <Chip key={r} r={r} />)}</li>)}</ul>
    </div>
  );
}

function CorrelationResult({ o }: { o: Out }) {
  const docs = Array.isArray(o.documents_supplied) ? (o.documents_supplied as { ref: string; title: string; authors: string | null; published: string; url: string; reliability: string }[]) : [];
  return (
    <div className="space-y-3">
      <p className="text-[11px] text-muted">Four layers are kept separate. Documents describe research and are not evidence about this platform's data.</p>
      <Layer title="Verified observations (platform records)" tone="border-ok text-ok" items={asFindings(o.verified_observations)} />
      <Layer title="External facts (stated by the supplied documents)" tone="border-accent text-accent" items={asFindings(o.external_facts)} />
      <Layer title="Analytical hypotheses (AI reasoning, not facts)" tone="border-sev-medium text-sev-medium" items={asFindings(o.analytical_hypotheses)} />
      <Block title="AI interpretation" text={o.ai_interpretation} />
      <Bullets title="Consistent with these categories" items={list(o.consistent_with_categories)} />
      <Bullets title="Gaps and limitations" items={list(o.gaps_and_limitations)} />
      <div>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Documents supplied to the model ({docs.length})</h4>
        {docs.length === 0 && <p className="text-xs text-muted">No relevant documents were found in the intelligence store.</p>}
        <ul className="space-y-2 text-xs">
          {docs.map((d) => (
            <li key={d.ref} className="rounded border border-line p-2">
              <span className="font-mono text-accent">{d.ref}</span> <a className="underline" href={d.url} target="_blank" rel="noreferrer noopener">{d.title}</a>
              <div className="text-muted">{d.authors ?? "authors n/a"} · {d.published}</div>
              <div className="text-muted">Reliability: {d.reliability}</div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function AiPanel({ kind, subject }: { kind: "anomaly" | "aircraft" | "correlation"; subject: string }) {
  const me = useMe();
  const canRun = me.data?.role === "analyst" || me.data?.role === "admin";
  const settings = useAISettings(false);
  const history = useAnalyses(kind === "aircraft" ? { icao24: subject } : { anomaly_id: subject });
  const run = useRunAnalysis(kind, subject);
  const [provider, setProvider] = useState<ProviderName | "">("");
  const [model, setModel] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [shown, setShown] = useState<Analysis | null>(null);

  useEffect(() => {
    if (!run.isPending) return;
    setElapsed(0);
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, [run.isPending]);

  const effective = provider || settings.data?.provider || "ollama";
  const configured = settings.data?.providers.find((p) => p.name === effective);
  const mine = history.data?.filter((a) => a.kind === KIND_OF[kind]);
  const latestOk = mine?.find((a) => a.status === "OK") ?? null;
  // While a request runs (or after it failed), older results are hidden so they cannot be mistaken for the one
  // requested. They stay reachable under History.
  const result = run.isPending || run.isError ? null : (shown ?? run.data ?? latestOk);

  return (
    <section className="rounded border border-line bg-panel p-4" aria-label="AI analysis">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-sm font-semibold">{TITLE[kind]}</h2>
        <span className="text-[11px] text-muted">{effective === "openrouter" ? "☁ data is sent to OpenRouter" : "⌂ runs locally on Ollama"}</span>
      </div>
      <p className="mb-3 text-xs text-muted">
        The AI explains; it never changes a detection, severity or status. Output is validated against the platform's records.
      </p>
      {!canRun && <p className="mb-2 text-xs text-sev-medium">An analyst-role token is required to request AI analysis. Earlier analyses are visible read-only.</p>}
      <div className="mb-3 flex flex-wrap items-end gap-3 text-xs">
        <label>
          <div className="mb-1 text-muted">Provider</div>
          <select aria-label="AI provider" value={provider || effective} onChange={(e) => { setProvider(e.target.value as ProviderName); setModel(""); }} className="rounded border border-line bg-ink px-2 py-1">
            <option value="ollama">Ollama (local)</option>
            <option value="openrouter">OpenRouter (cloud)</option>
          </select>
        </label>
        <label>
          <div className="mb-1 text-muted">Model (blank = configured default)</div>
          <input aria-label="AI model" value={model} onChange={(e) => setModel(e.target.value.trim())} placeholder={configured?.current_model ?? "not configured"} className="w-64 rounded border border-line bg-ink px-2 py-1 font-mono" maxLength={128} />
        </label>
        <button disabled={!canRun || run.isPending || (configured !== undefined && !configured.configured && !model)} onClick={() => { setShown(null); run.mutate({ provider: provider || undefined, model: model || undefined }); }} className="rounded bg-accent px-3 py-1.5 font-medium text-ink disabled:opacity-40">
          {run.isPending ? `Generating… ${elapsed}s` : result ? "Regenerate" : CTA[kind]}
        </button>
      </div>
      {run.isPending && <p className="mb-2 text-xs text-muted">Waiting for the model. Local models can take 1–2 minutes; cloud reasoning models can take longer.</p>}
      <ErrorNote error={run.error} />
      {result ? <Result a={result} /> : !run.isPending && <p className="text-xs text-muted">No AI analysis yet.</p>}
      {(run.isPending || run.isError) && latestOk && <p className="text-[11px] text-muted">An earlier analysis exists (see History); it is hidden so it is not mistaken for this request.</p>}
      {mine && mine.length > 1 && (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer text-muted">History ({mine.length})</summary>
          <ul className="mt-2 space-y-1">
            {mine.map((a) => (
              <li key={a.analysis_id} className="flex items-center gap-2">
                <span className={a.status === "OK" ? "text-ok" : "text-sev-high"}>{a.status}</span>
                <span className="font-mono text-muted">{fmtTime(a.created_at)} · {a.provider}/{a.model}</span>
                {a.status === "OK" && <button className="ml-auto text-accent underline" onClick={() => setShown(a)}>view</button>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
