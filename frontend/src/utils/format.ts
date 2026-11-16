// All stored values are SI. Conversions are for display only.
const dash = "—";

export const m2ft = (m: number) => m * 3.280839895;
export const ms2kt = (ms: number) => ms * 1.943844492;
export const ms2fpm = (ms: number) => ms * 196.850394;

export function fmtAlt(m: number | null | undefined): string {
  return m == null ? dash : `${Math.round(m).toLocaleString()} m (${Math.round(m2ft(m)).toLocaleString()} ft)`;
}
export function fmtSpeed(ms: number | null | undefined): string {
  return ms == null ? dash : `${ms.toFixed(1)} m/s (${Math.round(ms2kt(ms))} kt)`;
}
export function fmtVRate(ms: number | null | undefined): string {
  return ms == null ? dash : `${ms.toFixed(1)} m/s (${Math.round(ms2fpm(ms)).toLocaleString()} ft/min)`;
}
export function fmtDistance(m: number): string {
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`;
}
export function fmtDuration(s: number): string {
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)} s`;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min ${Math.round(s % 60)} s`;
}
export function fmtTime(iso: string | null | undefined): string {
  return iso ? `${iso.replace("T", " ").replace(/\.\d+/, "").replace(/(Z|\+00:00)$/, "")} UTC` : dash;
}
export const orDash = (v: string | number | null | undefined) => (v == null || v === "" ? dash : String(v));
