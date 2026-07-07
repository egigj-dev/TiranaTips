// src/components/MapPanel/MapPanel.jsx
import { useEffect, useRef } from "react";
import { setOptions, importLibrary } from "@googlemaps/js-api-loader";

const TIRANA_CENTER = { lat: 41.3275, lng: 19.8187 };

export default function MapPanel({ activeMapData }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const overlaysRef = useRef([]);
  const geometryRef = useRef(null);   // geometry lib, for decodePath

  // Mount once. setOptions configures the key; importLibrary loads only the
  // pieces we use (maps for the Map/Marker/Polyline, geometry for decodePath).
  // Guarded so a missing key disables ONLY the map, never the whole app.
  useEffect(() => {
    const key = import.meta.env.VITE_GOOGLE_MAPS_KEY;
    if (!key) {
      console.warn("[MapPanel] no maps key — panel disabled");
      return;
    }
    let cancelled = false;
    setOptions({ key, v: "weekly" });

    Promise.all([importLibrary("maps"), importLibrary("marker"), importLibrary("geometry")])
      .then(([maps, marker, geometry]) => {
        if (cancelled || !containerRef.current) return;
        geometryRef.current = geometry;
        mapRef.current = new maps.Map(containerRef.current, {
          center: TIRANA_CENTER,
          zoom: 13,
          clickableIcons: false,
          mapId: "DEMO_MAP_ID",   // AdvancedMarker requires a mapId
        });
        // Trigger the first redraw now that the map exists, in case a
        // payload already arrived before the library finished loading.
        redraw();
      })
      .catch((e) => console.error("[MapPanel] load failed:", e));

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The redraw — pure function of activeMapData. Defined here so both the
  // mount effect (first paint) and the payload effect (updates) can call it.
  const redraw = () => {
    const map = mapRef.current;
    const geometry = geometryRef.current;
    if (!map || !geometry || !activeMapData || !window.google) return;
    const g = window.google;

    overlaysRef.current.forEach((o) => (o.setMap ? o.setMap(null) : (o.map = null)));
    overlaysRef.current = [];

    const bounds = new g.maps.LatLngBounds();

    (activeMapData.markers || []).forEach((m) => {
      const pos = { lat: m.lat, lng: m.lng };
      const pin = new g.maps.marker.AdvancedMarkerElement({
        position: pos, map, title: m.label || "",
      });
      if (m.maps_url) {
        pin.addListener("click", () => window.open(m.maps_url, "_blank"));
      }
      overlaysRef.current.push(pin);
      bounds.extend(pos);
    });

    if (activeMapData.polyline) {
      const path = geometry.encoding.decodePath(activeMapData.polyline);
      const line = new g.maps.Polyline({
        path, map, strokeColor: "#1D9E75", strokeWeight: 4, strokeOpacity: 0.9,
      });
      overlaysRef.current.push(line);
      path.forEach((p) => bounds.extend(p));
    }

    if (!bounds.isEmpty()) {
      map.fitBounds(bounds, 48);
      const count = (activeMapData.markers || []).length;
      if (count <= 1 && !activeMapData.polyline) {
        g.maps.event.addListenerOnce(map, "idle", () => {
          if (map.getZoom() > 16) map.setZoom(16);
        });
      }
    }
  };

  // Redraw on every payload change (map may already be mounted).
  useEffect(() => {
    redraw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeMapData]);

  return (
    <div
      ref={containerRef}
      className="map-panel"
      role="img"
      aria-label="Map of places and routes from the current answer"
    />
  );
}