import { useState } from "react";

import { StatusBadge } from "../components/StatusBadge";
import { ErrorNote, NeedsToken } from "../components/QueryNotice";
import { useAISettings, useSaveAISettings } from "../hooks/useAI";
import { useMe } from "../hooks/useSecurity";
import type { ProviderName, ProviderStatus } from "../types/ai";

function ProviderCard({ p, active, admin, onUse, onModel }: { p: ProviderStatus; active: boolean; admin: boolean; onUse: () => void; onModel: (m: string) => void }) {
  const [model, setModel] = useState(p.current_model ?? "");
  return (
    <div className={`rounded border p-4 ${active ? "border-accent" : "border-line"} bg-panel`}>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-semibold">{p.name === "ollama" ? "Ollama (local)" : "OpenRouter (cloud)"}</h2>
        {active && <span className="rounded bg-accent/20 px-2 py-0.5 text-[11px] text-accent">DEFAULT</span>}
      </div>
      <dl className="space-y-1 text-xs">
        <div className="flex justify-between"><dt className="text-muted">Configured</dt><dd>{p.configured ? "yes" : "no"}</dd></div>
        <div className="flex justify-between"><dt className="text-muted">Reachable</dt><dd>{p.healthy == null ? "—" : <StatusBadge status={p.healthy ? "ok" : "down"} />}{p.detail && !p.healthy ? ` ${p.detail}` : ""}</dd></div>
        {p.base_url && <div className="flex justify-between"><dt className="text-muted">Endpoint</dt><dd className="font-mono">{p.base_url}</dd></div>}
        <div className="flex justify-between"><dt className="text-muted">Models available</dt><dd>{p.models ? p.models.length : "—"}</dd></div>
      </dl>
      <p className="mt-2 text-[11px] text-muted">{p.name === "ollama" ? "Prompts and data stay on this machine." : "Prompts, including anomaly evidence, are sent to OpenRouter and its model providers. The API key is held server-side only."}</p>
      <label className="mt-3 block text-xs text-muted">
        Model
        <input list={`models-${p.name}`} value={model} onChange={(e) => setModel(e.target.value.trim())} disabled={!admin} maxLength={128} className="mt-1 w-full rounded border border-line bg-ink px-2 py-1 font-mono text-sm" />
        <datalist id={`models-${p.name}`}>{(p.models ?? []).map((m) => <option key={m} value={m} />)}</datalist>
      </label>
      {admin && (
        <div className="mt-3 flex gap-2 text-xs">
          <button disabled={!model || model === p.current_model} onClick={() => onModel(model)} className="rounded border border-line px-2 py-1 disabled:opacity-40">Save model</button>
          <button disabled={active} onClick={onUse} className="rounded bg-accent/20 px-2 py-1 text-accent disabled:opacity-40">Use as default</button>
        </div>
      )}
    </div>
  );
}

export function AIConfigPage() {
  const me = useMe();
  const admin = me.data?.role === "admin";
  const { data, error, isFetching, refetch } = useAISettings(true);
  const save = useSaveAISettings();
  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">AI Configuration</h1>
        <button className="text-xs text-accent underline" onClick={() => refetch()}>{isFetching ? "Checking…" : "Re-check providers"}</button>
      </div>
      <NeedsToken />
      <ErrorNote error={error ?? save.error} />
      {!admin && <p className="text-xs text-sev-medium">Read-only: changing the default provider or model needs an admin-role token.</p>}
      {data && (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            {data.providers.map((p) => (
              <ProviderCard key={p.name} p={p} active={data.provider === p.name} admin={admin}
                onUse={() => save.mutate({ provider: p.name as ProviderName })}
                onModel={(m) => save.mutate(p.name === "ollama" ? { ollama_model: m } : { openrouter_model: m })} />
            ))}
          </div>
          <p className="text-xs text-muted">Settings source: {data.source}. Limits: {Object.entries(data.limits).map(([k, v]) => `${k.replaceAll("_", " ")} ${v}`).join(" · ")}. API keys and endpoints are environment-only and cannot be changed here.</p>
        </>
      )}
    </section>
  );
}
