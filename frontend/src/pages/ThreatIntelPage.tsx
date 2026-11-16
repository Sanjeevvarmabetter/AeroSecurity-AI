import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ErrorNote, NeedsToken } from "../components/QueryNotice";
import { useAddIntel, useImportArxiv, useIntel } from "../hooks/useAssistant";
import { useMe } from "../hooks/useSecurity";
import type { IntelItem } from "../types/assistant";
import { fmtTime } from "../utils/format";

const input = "w-full rounded border border-line bg-ink px-2 py-1 text-sm";

function Item({ i, open }: { i: IntelItem; open: boolean }) {
  return (
    <li id={`doc-${i.id}`} className={`rounded border p-3 ${open ? "border-accent" : "border-line"} bg-panel`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">{i.title}</h2>
        <span className="font-mono text-[11px] text-muted">DOC:{i.id}</span>
      </div>
      <p className="text-xs text-muted">{i.authors ?? "authors not recorded"} · published {i.publication_date ?? "date not available"} · {i.source_name}</p>
      <p className="mt-2 text-sm">{i.excerpt}</p>
      <p className="mt-2 rounded border border-sev-medium/30 bg-sev-medium/5 p-2 text-xs text-sev-medium">Reliability limits: {i.reliability_notes}</p>
      <p className="mt-2 text-[11px] text-muted">
        Source: <a className="text-accent underline" href={i.source_url} target="_blank" rel="noreferrer noopener">{i.source_url}</a> · retrieved {fmtTime(i.retrieved_at)} · added by <span className="font-mono">{i.added_by}</span> ({i.origin})
      </p>
    </li>
  );
}

export function ThreatIntelPage() {
  const [sp] = useSearchParams();
  const open = Number(sp.get("doc")) || 0;
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");
  const { data, error } = useIntel(applied);
  const me = useMe();
  const canWrite = me.data?.role === "analyst" || me.data?.role === "admin";
  const imp = useImportArxiv();
  const add = useAddIntel();
  const [aq, setAq] = useState("ADS-B security");
  const [form, setForm] = useState({ source_name: "", source_url: "", title: "", authors: "", excerpt: "", reliability_notes: "" });
  const [showForm, setShowForm] = useState(false);

  return (
    <section className="space-y-4">
      <h1 className="text-lg font-semibold">Aviation Threat Intelligence</h1>
      <p className="max-w-3xl text-xs text-muted">
        Public research and advisories used as <em>context</em>. Every item carries its source, URL, publication and retrieval dates and a statement
        of its reliability limits. These documents describe research or events elsewhere; they are not evidence that anything occurred in this platform's data.
      </p>
      <NeedsToken />
      <ErrorNote error={error ?? imp.error ?? add.error} />
      <form onSubmit={(e) => { e.preventDefault(); setApplied(q.trim()); }} className="flex gap-2">
        <input aria-label="Search intelligence" value={q} onChange={(e) => setQ(e.target.value)} maxLength={100} placeholder="Search documents (e.g. spoofing detection)" className={input} />
        <button className="rounded border border-line px-3 text-sm">Search</button>
      </form>

      {canWrite && (
        <div className="space-y-3 rounded border border-line bg-panel p-3 text-xs">
          <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); imp.mutate({ query: aq, max: 5 }); }}>
            <label className="grow">
              <div className="mb-1 text-muted">Import abstracts from arXiv (documented public API, abstracts only)</div>
              <input aria-label="arXiv query" value={aq} onChange={(e) => setAq(e.target.value)} maxLength={100} className={input} />
            </label>
            <button disabled={imp.isPending} className="rounded bg-accent/20 px-3 py-1.5 text-accent disabled:opacity-40">{imp.isPending ? "Importing…" : "Import"}</button>
            {imp.data && <span className="text-ok">found {imp.data.found}, added {imp.data.added}, already stored {imp.data.skipped_existing}</span>}
          </form>
          <button className="text-accent underline" onClick={() => setShowForm(!showForm)}>{showForm ? "Hide manual form" : "Register a document manually"}</button>
          {showForm && (
            <form className="grid gap-2 md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); add.mutate({ ...form, authors: form.authors || null, tags: [] }, { onSuccess: () => setForm({ source_name: "", source_url: "", title: "", authors: "", excerpt: "", reliability_notes: "" }) }); }}>
              {(["source_name", "source_url", "title", "authors"] as const).map((k) => (
                <label key={k}><div className="mb-1 text-muted">{k.replace("_", " ")}{k === "authors" ? " (optional)" : ""}</div><input aria-label={k} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} className={input} /></label>
              ))}
              <label className="md:col-span-2"><div className="mb-1 text-muted">Excerpt or your own summary (20–4000 chars; not full text)</div><textarea aria-label="excerpt" rows={3} value={form.excerpt} onChange={(e) => setForm({ ...form, excerpt: e.target.value })} className={input} /></label>
              <label className="md:col-span-2"><div className="mb-1 text-muted">Reliability limits (required)</div><textarea aria-label="reliability" rows={2} value={form.reliability_notes} onChange={(e) => setForm({ ...form, reliability_notes: e.target.value })} className={input} /></label>
              <button disabled={add.isPending} className="w-fit rounded bg-accent px-3 py-1.5 font-medium text-ink disabled:opacity-40">Register</button>
            </form>
          )}
        </div>
      )}

      {data && <p className="text-xs text-muted">{data.total} document{data.total === 1 ? "" : "s"}{applied ? ` matching “${applied}”` : ""}</p>}
      <ul className="space-y-3">{data?.items.map((i) => <Item key={i.id} i={i} open={i.id === open} />)}</ul>
      {data && data.items.length === 0 && <p className="text-sm text-muted">No documents. {canWrite ? "Import from arXiv or register one manually." : "An analyst can import documents."}</p>}
    </section>
  );
}
