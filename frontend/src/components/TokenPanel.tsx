import { useState } from "react";

import { setToken, useToken } from "../stores/auth";

export function TokenPanel() {
  const token = useToken();
  const [draft, setDraft] = useState("");
  if (token)
    return (
      <div className="text-xs text-muted">
        <span className="text-ok">●</span> API token set (this tab only){" "}
        <button className="ml-1 underline" onClick={() => setToken(null)}>
          clear
        </button>
      </div>
    );
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (draft.trim()) setToken(draft.trim());
        setDraft("");
      }}
      className="space-y-1"
    >
      <label className="text-xs text-muted" htmlFor="tok">
        API token
      </label>
      <input
        id="tok"
        type="password"
        autoComplete="off"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        className="w-full rounded border border-line bg-ink px-2 py-1 text-sm"
      />
      <button className="w-full rounded bg-accent/20 py-1 text-xs text-accent">Use token</button>
    </form>
  );
}
