import { ApiError } from "../services/api";
import { useToken } from "../stores/auth";

export function NeedsToken() {
  const token = useToken();
  if (token) return null;
  return <p className="text-sm text-sev-medium">Enter an API token in the sidebar to load data.</p>;
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const msg =
    error instanceof ApiError && error.status === 401
      ? "Authentication failed. Check the API token in the sidebar."
      : error instanceof Error
        ? error.message
        : "Unexpected error";
  return (
    <p role="alert" className="text-sm text-sev-critical">
      {msg}
    </p>
  );
}
