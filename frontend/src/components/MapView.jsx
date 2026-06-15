import { useEffect, useMemo } from "react";
import { MapContainer, TileLayer, Marker, Polyline, Circle, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const makeDivIcon = (color, label) =>
  L.divIcon({
    className: "",
    html: `<div style="width:28px;height:28px;border-radius:50%;background:${color};border:2px solid #050505;box-shadow:0 0 0 2px ${color}aa,0 0 18px ${color};display:flex;align-items:center;justify-content:center;color:#050505;font-weight:700;font-size:13px;font-family:'Outfit',sans-serif;">${label}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });

const userIcon = L.divIcon({
  className: "",
  html: `<div class="user-pin"><span class="ring"></span><span class="dot"></span></div>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

const ORIGIN_ICON = makeDivIcon("#10b981", "A");
const DEST_ICON = makeDivIcon("#ef4444", "B");

function FitBounds({ bounds }) {
  const map = useMap();
  useEffect(() => {
    if (bounds && bounds.length > 1) {
      map.fitBounds(bounds, { padding: [80, 80], maxZoom: 15 });
    }
  }, [bounds, map]);
  return null;
}

function ClickHandler({ markingMode, onAddCritical }) {
  useMapEvents({
    click(e) {
      if (markingMode) onAddCritical({ lat: e.latlng.lat, lng: e.latlng.lng });
    },
  });
  return null;
}

function CursorClass({ markingMode }) {
  const map = useMap();
  useEffect(() => {
    const el = map.getContainer();
    if (markingMode) el.style.cursor = "crosshair";
    else el.style.cursor = "";
  }, [markingMode, map]);
  return null;
}

export default function MapView({
  origin,
  destination,
  userLocation,
  routeResponse,
  activeAltId,
  criticalZones,
  markingMode,
  onAddCritical,
}) {
  const center = useMemo(() => {
    if (origin) return [origin.lat, origin.lng];
    if (userLocation) return [userLocation.lat, userLocation.lng];
    return [19.4326, -99.1332];
  }, [origin, userLocation]);

  const allRoutes = useMemo(() => {
    if (!routeResponse) return [];
    return [routeResponse.best, ...routeResponse.alternatives];
  }, [routeResponse]);

  const bounds = useMemo(() => {
    const pts = [];
    if (origin) pts.push([origin.lat, origin.lng]);
    if (destination) pts.push([destination.lat, destination.lng]);
    allRoutes.forEach((r) => r.segments.forEach((s) => s.coords.forEach((c) => pts.push(c))));
    return pts;
  }, [origin, destination, allRoutes]);

  return (
    <div data-testid="map-container" className="h-full w-full">
    <MapContainer center={center} zoom={13} className="h-full w-full" zoomControl>
      <TileLayer
        attribution='&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://openstreetmap.org/">OSM</a>'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />
      <ClickHandler markingMode={markingMode} onAddCritical={onAddCritical} />
      <CursorClass markingMode={markingMode} />

      {userLocation && <Marker position={[userLocation.lat, userLocation.lng]} icon={userIcon} />}
      {origin && <Marker position={[origin.lat, origin.lng]} icon={ORIGIN_ICON} />}
      {destination && <Marker position={[destination.lat, destination.lng]} icon={DEST_ICON} />}

      {/* Critical zones */}
      {criticalZones.map((z, i) => (
        <Circle
          key={`${z.lat}-${z.lng}-${i}`}
          center={[z.lat, z.lng]}
          radius={300}
          pathOptions={{
            color: "#ef4444",
            fillColor: "#ef4444",
            fillOpacity: 0.18,
            weight: 2,
            dashArray: "4 4",
          }}
        />
      ))}

      {/* Inactive routes faded */}
      {allRoutes
        .filter((r) => r.id !== activeAltId)
        .map((r) =>
          r.segments.map((seg, i) => (
            <Polyline
              key={`${r.id}-${i}`}
              positions={seg.coords}
              pathOptions={{ color: "#3f3f46", weight: 4, opacity: 0.55, dashArray: "4 6" }}
            />
          ))
        )}

      {/* Active route */}
      {allRoutes
        .filter((r) => r.id === activeAltId)
        .map((r) =>
          r.segments.map((seg, i) => {
            const isManhattan = seg.algorithm === "Manhattan";
            return (
              <Polyline
                key={`${r.id}-${i}`}
                positions={seg.coords}
                pathOptions={{
                  color: isManhattan ? "#f59e0b" : "#22d3ee",
                  weight: isManhattan ? 7 : 5,
                  opacity: 1,
                  dashArray: isManhattan ? "10 8" : undefined,
                  lineCap: "round",
                  lineJoin: "round",
                }}
              />
            );
          })
        )}

      <FitBounds bounds={bounds} />
    </MapContainer>
    </div>
  );
}
