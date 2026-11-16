import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

import { TokenPanel } from "../components/TokenPanel";
import { useMe } from "../hooks/useSecurity";

const NAV = [
  {
    section: "SURVEILLANCE & RADAR",
    items: [
      { to: "/", label: "Mission Overview", icon: "📊" },
      { to: "/radar", label: "Live Flight Radar", icon: "🛰️" },
      { to: "/aircraft", label: "Aircraft Intelligence", icon: "✈️" },
    ],
  },
  {
    section: "ANALYTICS & DYNAMICS",
    items: [
      { to: "/analytics", label: "Flight Analytics", icon: "📈" },
      { to: "/trajectories", label: "Trajectory Analysis", icon: "🧭" },
      { to: "/airports", label: "Airport Intelligence", icon: "🏢" },
    ],
  },
  {
    section: "SECURITY OPERATIONS",
    items: [
      { to: "/anomalies", label: "Anomaly Center", icon: "⚠️" },
      { to: "/emergencies", label: "Emergency Monitoring", icon: "🚨" },
      { to: "/investigations", label: "Investigation Center", icon: "📁" },
      { to: "/rules", label: "Detection Rules", icon: "⚙️" },
    ],
  },
  {
    section: "INTELLIGENCE & AI",
    items: [
      { to: "/assistant", label: "AI Intelligence Assistant", icon: "🤖" },
      { to: "/threat-intel", label: "Threat Intelligence", icon: "📑" },
      { to: "/reports", label: "Intelligence Reports", icon: "📄" },
    ],
  },
  {
    section: "SYSTEM INFRASTRUCTURE",
    items: [
      { to: "/data-sources", label: "Data Sources", icon: "🗄️" },
      { to: "/ai-config", label: "AI Configuration", icon: "🧠" },
      { to: "/system-health", label: "System Health", icon: "💚" },
    ],
  },
];

export function AppLayout() {
  const [utcTime, setUtcTime] = useState("");
  const me = useMe();
  const location = useLocation();

  useEffect(() => {
    const update = () => {
      const d = new Date();
      setUtcTime(
        d.toISOString().slice(0, 19).replace("T", " ") + " UTC"
      );
    };
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex min-h-screen bg-ink text-slate-200">
      {/* Sidebar Navigation */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-line bg-panel p-4 shadow-xl">
        {/* Brand / Logo */}
        <Link to="/" className="mb-6 block border-b border-line/60 pb-4">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded bg-accent/20 font-mono text-sm font-bold text-accent shadow-inner">
              AS
            </span>
            <div>
              <div className="text-xs font-bold tracking-widest text-slate-100">
                AEROSECURITY AI
              </div>
              <div className="text-[10px] tracking-wider text-muted">
                AVIATION CYBERSECURITY
              </div>
            </div>
          </div>
        </Link>

        {/* Navigation Sections */}
        <div className="flex-1 space-y-4 overflow-y-auto pr-1">
          {NAV.map((g) => (
            <nav key={g.section} className="space-y-1">
              <div className="px-2 pb-1 text-[10px] font-semibold tracking-wider text-muted/70">
                {g.section}
              </div>
              {g.items.map((i) => {
                const isExact = i.to === "/";
                const isActive = isExact
                  ? location.pathname === "/"
                  : location.pathname.startsWith(i.to);

                return (
                  <NavLink
                    key={i.to}
                    to={i.to}
                    className={`flex items-center gap-2.5 rounded px-2.5 py-1.5 text-xs font-medium transition-all ${
                      isActive
                        ? "border border-accent/30 bg-accent/15 text-accent shadow-sm"
                        : "text-slate-300 hover:bg-subpanel hover:text-white"
                    }`}
                  >
                    <span className="text-xs">{i.icon}</span>
                    <span>{i.label}</span>
                  </NavLink>
                );
              })}
            </nav>
          ))}
        </div>

        {/* Footer & Token Drawer */}
        <div className="mt-auto border-t border-line/60 pt-4">
          <TokenPanel />
        </div>
      </aside>

      {/* Main Content Viewport */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top Operations Header */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-panel/80 px-6 backdrop-blur">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 rounded-full border border-ok/30 bg-ok/10 px-2.5 py-1 text-[11px] font-medium text-ok">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-ok opacity-75"></span>
                <span className="relative inline-flex h-2 w-2 rounded-full bg-ok"></span>
              </span>
              SURVEILLANCE ACTIVE
            </div>
            <span className="text-xs font-mono text-muted">|</span>
            <span className="font-mono text-xs text-slate-300 tracking-wide">
              {utcTime || "UTC CLOCK SYNC..."}
            </span>
          </div>

          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-muted">Role:</span>
              <span className="rounded border border-line bg-subpanel px-2 py-0.5 font-mono text-[11px] font-semibold text-accent uppercase">
                {me.data?.role ?? "ANONYMOUS"}
              </span>
            </div>
          </div>
        </header>

        {/* Main Routed Content */}
        <main className="min-w-0 flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
