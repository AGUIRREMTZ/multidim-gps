import { useEffect, useState } from "react";
import Sidebar from "@/components/Sidebar";
import MapView from "@/components/MapView";
import MetricsPanel from "@/components/MetricsPanel";
import { computeRoute, fetchDimensions, reverseGeocode } from "@/lib/api";
import { toast } from "sonner";

export default function GpsPage() {
  const [dimensions, setDimensions] = useState([]);
  const [origin, setOrigin] = useState(null);
  const [destination, setDestination] = useState(null);
  const [userLocation, setUserLocation] = useState(null);
  const [selectedDims, setSelectedDims] = useState({ time: "min", distance: "min" });
  const [criticalZones, setCriticalZones] = useState([]);
  const [markingMode, setMarkingMode] = useState(false);
  const [routeResponse, setRouteResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeAltId, setActiveAltId] = useState(null);

  useEffect(() => {
    fetchDimensions().then(setDimensions).catch(() => toast.error("No se cargaron las dimensiones"));
  }, []);

  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const c = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        setUserLocation(c);
        try {
          const name = await reverseGeocode(c.lat, c.lng);
          setOrigin({ ...c, display_name: name });
        } catch {
          setOrigin({ ...c, display_name: `${c.lat.toFixed(5)}, ${c.lng.toFixed(5)}` });
        }
      },
      () => toast("Permite tu ubicación para usar como origen", { description: "También puedes escribirla manualmente." }),
      { enableHighAccuracy: true, timeout: 8000 }
    );
  }, []);

  const handleAddCritical = (zone) => {
    setCriticalZones((zs) => [...zs, zone]);
    if (routeResponse) {
      // Recompute will toast; don't duplicate
      setTimeout(() => recompute([...criticalZones, zone]), 100);
    } else {
      toast.success("Zona crítica marcada", { description: `${zone.lat.toFixed(4)}, ${zone.lng.toFixed(4)}` });
    }
  };

  const recompute = async (zones) => {
    if (!origin || !destination) return;
    setLoading(true);
    try {
      const data = await computeRoute(
        { lat: origin.lat, lng: origin.lng },
        { lat: destination.lat, lng: destination.lng },
        selectedDims,
        zones ?? criticalZones
      );
      setRouteResponse(data);
      setActiveAltId(data.best.id);
      toast.success("Ruta recalculada", { description: data.explanation });
    } catch (e) {
      toast.error("Error recalculando", { description: e?.response?.data?.detail || e.message });
    } finally {
      setLoading(false);
    }
  };

  const handleCompute = async () => {
    if (!origin || !destination) {
      toast.error("Define origen y destino");
      return;
    }
    if (Object.keys(selectedDims).length === 0 && criticalZones.length === 0) {
      toast.error("Selecciona al menos una dimensión");
      return;
    }
    await recompute(criticalZones);
  };

  return (
    <div className="h-screen w-full flex flex-col md:flex-row overflow-hidden bg-[#050505]">
      <Sidebar
        dimensions={dimensions}
        origin={origin}
        destination={destination}
        userLocation={userLocation}
        onOriginChange={setOrigin}
        onDestinationChange={setDestination}
        selectedDims={selectedDims}
        onSelectedDimsChange={setSelectedDims}
        criticalZones={criticalZones}
        markingMode={markingMode}
        onToggleMarking={() => setMarkingMode((m) => !m)}
        onClearCritical={() => {
          setCriticalZones([]);
          if (routeResponse) setTimeout(() => recompute([]), 100);
        }}
        onRemoveCritical={(idx) => {
          const next = criticalZones.filter((_, i) => i !== idx);
          setCriticalZones(next);
          if (routeResponse) setTimeout(() => recompute(next), 100);
        }}
        onCompute={handleCompute}
        loading={loading}
      />
      <div className="flex-1 relative">
        <MapView
          origin={origin}
          destination={destination}
          userLocation={userLocation}
          routeResponse={routeResponse}
          activeAltId={activeAltId}
          criticalZones={criticalZones}
          markingMode={markingMode}
          onAddCritical={handleAddCritical}
        />
        {markingMode && (
          <div
            data-testid="marking-banner"
            className="absolute top-6 left-1/2 -translate-x-1/2 z-[400] bg-red-500/15 backdrop-blur-xl border border-red-400/50 px-5 py-2.5 text-xs mono uppercase tracking-widest text-red-200 shadow-2xl"
          >
            ● Modo marcado activo — clic en el mapa para añadir zona crítica
          </div>
        )}
        {routeResponse && (
          <MetricsPanel
            response={routeResponse}
            dimensions={dimensions}
            activeAltId={activeAltId}
            onSelectAlt={setActiveAltId}
            selectedDims={selectedDims}
          />
        )}
      </div>
    </div>
  );
}
