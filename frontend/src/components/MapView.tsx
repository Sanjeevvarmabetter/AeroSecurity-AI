import { Map, NavigationControl, setWorkerUrl } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState, type ReactNode } from "react";

// MapLibre 6 ships an ES-module worker; Vite must bundle it so its imports resolve (see docs/frontend note).
setWorkerUrl(workerUrl);

// Default basemap: bundled Natural Earth country outlines (public domain). No keys, no third-party requests,
// works offline. Set VITE_MAP_TILE_URL (e.g. self-hosted raster tiles) to draw tiles underneath instead.
const TILE_URL: string | undefined = import.meta.env.VITE_MAP_TILE_URL;
const ATTRIBUTION: string = import.meta.env.VITE_MAP_ATTRIBUTION ?? "Natural Earth (public domain)";
const COUNTRIES_URL = `${import.meta.env.BASE_URL}basemap/countries-110m.geojson`;

interface Props {
  onReady: (map: Map) => void | (() => void);
  className?: string;
  /** Layer whose drawn features are counted and exposed as data-rendered-features (proves real rendering). */
  probeLayer?: string;
  children?: ReactNode;
}

/** Owns the MapLibre instance lifecycle. Layers/sources are managed by the caller via onReady. */
export function MapView({ onReady, className = "h-[420px]", probeLayer, children }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const [rendered, setRendered] = useState(0);
  const probe = useRef(probeLayer);
  const cb = useRef(onReady);
  cb.current = onReady;

  useEffect(() => {
    if (!el.current) return;
    const map = new Map({
      container: el.current,
      style: {
        version: 8,
        sources: {
          countries: { type: "geojson", data: COUNTRIES_URL, attribution: ATTRIBUTION },
          ...(TILE_URL ? { tiles: { type: "raster" as const, tiles: [TILE_URL], tileSize: 256 } } : {}),
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#0b1220" } },
          ...(TILE_URL ? [{ id: "tiles", type: "raster" as const, source: "tiles" }] : []),
          { id: "land", type: "fill", source: "countries", paint: { "fill-color": "#16233a" } },
          { id: "borders", type: "line", source: "countries", paint: { "line-color": "#2c3d5c", "line-width": 0.8 } },
        ],
      },
      center: [20, 30],
      zoom: 2,
      attributionControl: { compact: true },
    });
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    let cleanup: void | (() => void);
    map.on("idle", () => {
      if (probe.current && map.getLayer(probe.current)) {
        setRendered(map.queryRenderedFeatures({ layers: [probe.current] }).length);
      }
    });
    // MapLibre only reacts to window resizes; keep the canvas in sync when its own container changes size.
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el.current);
    map.on("load", () => {
      cleanup = cb.current(map);
    });
    return () => {
      ro.disconnect();
      if (typeof cleanup === "function") cleanup();
      map.remove();
    };
  }, []);

  return (
    <div data-rendered-features={rendered} className={`relative overflow-hidden rounded border border-line ${className}`}>
      {/* Inline style on purpose: maplibre-gl.css sets .maplibregl-map{position:relative}, which would beat a utility class. */}
      <div ref={el} style={{ position: "absolute", inset: 0 }} />
      {children}
    </div>
  );
}
