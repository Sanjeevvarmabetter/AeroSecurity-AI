import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { SystemHealthPage } from "./SystemHealthPage";

const wrap = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <SystemHealthPage />
    </QueryClientProvider>,
  );

afterEach(() => vi.unstubAllGlobals());

test("renders component statuses from the API", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200,
    json: async () => ({ status: "ok", version: "0.1.0", environment: "test",
      components: { database: { status: "ok", detail: null }, postgis: { status: "ok", detail: "3.4" } } }),
  }));
  wrap();
  expect(await screen.findByText("postgis")).toBeInTheDocument();
});

test("shows an explicit unavailable message, not fabricated data", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("net")));
  wrap();
  expect(await screen.findByRole("alert")).toHaveTextContent(/unreachable/i);
});
