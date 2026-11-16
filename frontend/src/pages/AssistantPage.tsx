import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { ErrorNote, NeedsToken } from "../components/QueryNotice";
import { useAISettings } from "../hooks/useAI";
import { useConversation, useConversations, useSendChat } from "../hooks/useAssistant";
import { useMe } from "../hooks/useSecurity";
import type { ProviderName } from "../types/ai";
import type { ChatMessage, ChatReply, Citation, ToolCall } from "../types/assistant";
import { fmtTime } from "../utils/format";

const SUGGESTIONS = [
  "Summarize the emergency squawk events in the data.",
  "Which aircraft have HIGH severity detections?",
  "Is there published research relevant to detecting ADS-B spoofing?",
  "Explain the limitations of the barometric/geometric altitude divergence detection.",
];

function CitationChips({ items }: { items: Citation[] }) {
  if (!items.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
      <span className="text-muted">Cited records:</span>
      {items.map((c) =>
        c.link ? (
          <Link key={c.ref} to={c.link} title={c.note} className="rounded border border-accent/40 px-1.5 py-0.5 font-mono text-accent hover:bg-accent/10">{c.ref}</Link>
        ) : (
          <span key={c.ref} title={c.note} className="rounded border border-line px-1.5 py-0.5 font-mono text-muted">{c.ref}</span>
        ),
      )}
    </div>
  );
}

function Tools({ calls }: { calls: ToolCall[] }) {
  if (!calls.length) return null;
  return (
    <details className="mt-2 text-[11px] text-muted">
      <summary className="cursor-pointer">Used {calls.length} platform tool{calls.length > 1 ? "s" : ""} (read-only)</summary>
      <ul className="mt-1 space-y-1 font-mono">
        {calls.map((t, i) => (
          <li key={i}>
            <span className={t.ok ? "text-ok" : "text-sev-high"}>{t.ok ? "✓" : "✗"}</span> {t.tool}({JSON.stringify(t.arguments)})
            {t.ok ? ` → ${t.records.length} record${t.records.length === 1 ? "" : "s"}` : ` → ${t.error}`}
          </li>
        ))}
      </ul>
    </details>
  );
}

function Bubble({ role, text, citations, warnings, calls, meta }: { role: "user" | "assistant"; text: string; citations?: Citation[]; warnings?: string[]; calls?: ToolCall[]; meta?: string }) {
  const mine = role === "user";
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-3xl rounded border p-3 text-sm ${mine ? "border-accent/40 bg-accent/10" : "border-line bg-panel"}`}>
        {!mine && (
          <div className="mb-1 flex items-center gap-2 text-[10px]">
            <span className="rounded bg-accent/20 px-1.5 py-0.5 font-semibold tracking-wide text-accent">AI-GENERATED</span>
            <span className="text-muted">not a verified finding{meta ? ` · ${meta}` : ""}</span>
          </div>
        )}
        {/* Model output is untrusted: rendered as a text node, never as HTML. */}
        <div className="whitespace-pre-wrap break-words">{text}</div>
        {warnings?.map((w) => <p key={w} className="mt-2 rounded border border-sev-medium/40 bg-sev-medium/10 p-2 text-xs text-sev-medium">⚠ {w}</p>)}
        {calls && <Tools calls={calls} />}
        {citations && <CitationChips items={citations} />}
      </div>
    </div>
  );
}

export function AssistantPage() {
  const me = useMe();
  const canChat = me.data?.role === "analyst" || me.data?.role === "admin";
  const settings = useAISettings(false);
  const list = useConversations();
  const [cid, setCid] = useState<string | null>(null);
  const detail = useConversation(cid);
  const send = useSendChat();
  const [text, setText] = useState("");
  const [provider, setProvider] = useState<ProviderName | "">("");
  const [pending, setPending] = useState<string | null>(null);
  const [last, setLast] = useState<ChatReply | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!send.isPending) return;
    setElapsed(0);
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, [send.isPending]);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [detail.data, pending, last]);

  const effective = provider || settings.data?.provider || "ollama";
  // Persisted turns are what the server stored; hide tool plumbing rows and show only questions and final answers.
  const shown: ChatMessage[] = (detail.data?.messages ?? []).filter((m) => m.role === "user" || (m.role === "assistant" && !m.tool_name));

  const submit = (msg: string) => {
    if (!msg.trim() || send.isPending) return;
    setPending(msg);
    setText("");
    send.mutate(
      { message: msg, conversation_id: cid, target: { provider: provider || undefined } },
      { onSuccess: (r) => { setCid(r.conversation_id); setLast(r); }, onSettled: () => setPending(null) },
    );
  };

  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h1 className="text-lg font-semibold">AI Intelligence Assistant</h1>
        <span className="text-[11px] text-muted">{effective === "openrouter" ? "☁ prompts and tool results go to OpenRouter" : "⌂ runs locally on Ollama"}</span>
      </div>
      <p className="max-w-3xl text-xs text-muted">
        Ask about the stored aviation data. The assistant can only use nine read-only platform tools, cannot change anything, and every
        answer is AI-generated and unverified. Check cited records before acting.
      </p>
      <NeedsToken />
      {!canChat && <p className="text-xs text-sev-medium">An analyst-role token is required to chat. Earlier conversations you own are not available to viewers.</p>}
      <div className="grid gap-4 lg:grid-cols-[14rem_1fr]">
        <aside className="space-y-2">
          <button onClick={() => { setCid(null); setLast(null); }} className="w-full rounded border border-line px-2 py-1.5 text-sm hover:bg-line">+ New conversation</button>
          <ul className="divide-y divide-line rounded border border-line bg-panel text-xs">
            {list.data?.map((c) => (
              <li key={c.id}>
                <button onClick={() => { setCid(c.id); setLast(null); }} className={`block w-full px-2 py-2 text-left hover:bg-line ${c.id === cid ? "bg-accent/15" : ""}`}>
                  <div className="truncate">{c.title}</div>
                  <div className="text-[10px] text-muted">{fmtTime(c.created_at)}</div>
                </button>
              </li>
            ))}
            {list.data?.length === 0 && <li className="px-2 py-2 text-muted">No conversations yet.</li>}
          </ul>
        </aside>

        <div className="flex min-h-[28rem] flex-col rounded border border-line bg-ink">
          <div className="flex-1 space-y-3 overflow-y-auto p-3" aria-live="polite">
            {shown.length === 0 && !pending && (
              <div className="space-y-2 text-sm text-muted">
                <p>Try a question:</p>
                <div className="flex flex-wrap gap-2">
                  {SUGGESTIONS.map((q) => <button key={q} disabled={!canChat} onClick={() => submit(q)} className="rounded border border-line px-2 py-1 text-left text-xs hover:bg-line disabled:opacity-40">{q}</button>)}
                </div>
              </div>
            )}
            {shown.map((m, i) => {
              const isLast = i === shown.length - 1 && m.role === "assistant" && last?.conversation_id === cid;
              return (
                <Bubble key={m.id} role={m.role as "user" | "assistant"} text={m.content} citations={m.citations ?? undefined} warnings={m.warnings ?? undefined}
                  calls={isLast ? last?.tool_calls : undefined} meta={m.provider ? `${m.provider} · ${m.model}` : undefined} />
              );
            })}
            {pending && <Bubble role="user" text={pending} />}
            {send.isPending && <p className="text-xs text-muted">Thinking and querying platform tools… {elapsed}s (local models can take a minute or more)</p>}
            <ErrorNote error={send.error} />
            <div ref={end} />
          </div>
          <form onSubmit={(e) => { e.preventDefault(); submit(text); }} className="flex flex-wrap items-center gap-2 border-t border-line p-2">
            <select aria-label="AI provider" value={provider || effective} onChange={(e) => setProvider(e.target.value as ProviderName)} className="rounded border border-line bg-panel px-2 py-1.5 text-xs">
              <option value="ollama">Ollama (local)</option>
              <option value="openrouter">OpenRouter (cloud)</option>
            </select>
            <input aria-label="Message" value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} disabled={!canChat || send.isPending}
              placeholder="Ask about aircraft, detections, emergencies, airports or research…" className="min-w-0 flex-1 rounded border border-line bg-panel px-3 py-1.5 text-sm" />
            <button disabled={!canChat || send.isPending || !text.trim()} className="rounded bg-accent px-3 py-1.5 text-sm font-medium text-ink disabled:opacity-40">Send</button>
          </form>
        </div>
      </div>
    </section>
  );
}
