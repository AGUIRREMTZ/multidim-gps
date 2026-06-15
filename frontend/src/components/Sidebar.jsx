import { Compass, NavigationArrow, Path, Spinner, MapPinLine, Trash, Crosshair } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import { ScrollArea } from "@/components/ui/scroll-area";
import AutocompleteField from "@/components/AutocompleteField";

function DimensionRow({ dim, active, preference, onToggle, onPrefChange }) {
  return (
    <div className="px-4 py-3 hover:bg-[#0c0c0c]">
      <div className="flex items-center justify-between gap-3">
        <label className="flex items-center gap-3 cursor-pointer flex-1" data-testid={`dimension-toggle-${dim.key}`}>
          <Checkbox
            checked={active}
            onCheckedChange={() => onToggle(dim.key)}
            className="border-zinc-700 data-[state=checked]:bg-cyan-400 data-[state=checked]:text-black data-[state=checked]:border-cyan-400 rounded-none"
          />
          <div className="flex-1">
            <div className="text-sm text-zinc-200 flex items-center gap-1.5">
              {dim.label}
              {dim.source && (
                <span
                  title={dim.source}
                  className="text-[9px] mono uppercase tracking-wider text-zinc-600 hover:text-cyan-400 cursor-help border border-zinc-800 px-1 leading-tight"
                >
                  ?
                </span>
              )}
            </div>
            <div className="text-[10px] mono text-zinc-500 tracking-wider uppercase mt-0.5">{dim.hint}</div>
          </div>
        </label>
        <span className="text-[10px] mono text-zinc-500 uppercase">{dim.unit}</span>
      </div>

      {active && dim.toggle && (
        <div className="mt-3 pl-7 flex gap-2" data-testid={`dimension-pref-${dim.key}`}>
          {["min", "max"].map((p) => (
            <button
              key={p}
              onClick={() => onPrefChange(dim.key, p)}
              data-testid={`dimension-pref-${dim.key}-${p}`}
              className={`flex-1 text-[11px] mono uppercase tracking-wider px-3 py-1.5 border transition-colors ${
                preference === p
                  ? "border-cyan-400 text-cyan-300 bg-cyan-400/10"
                  : "border-zinc-800 text-zinc-500 hover:text-zinc-200 hover:border-zinc-600"
              }`}
            >
              {p === "min" ? "Menor" : "Mayor"}
            </button>
          ))}
        </div>
      )}

      {active && !dim.toggle && (
        <div className="mt-2 pl-7">
          <span className="inline-block text-[10px] mono uppercase tracking-wider px-2 py-0.5 bg-cyan-400/10 text-cyan-400 border border-cyan-400/30">
            ↓ Optimizar al menor
          </span>
        </div>
      )}
    </div>
  );
}

export default function Sidebar({
  dimensions,
  origin,
  destination,
  userLocation,
  onOriginChange,
  onDestinationChange,
  selectedDims,
  onSelectedDimsChange,
  criticalZones,
  markingMode,
  onToggleMarking,
  onClearCritical,
  onRemoveCritical,
  onCompute,
  loading,
}) {
  const toggleDim = (key) => {
    const next = { ...selectedDims };
    if (next[key]) delete next[key];
    else {
      const meta = dimensions.find((d) => d.key === key);
      next[key] = meta?.default || "min";
    }
    onSelectedDimsChange(next);
  };
  const setPref = (key, pref) => onSelectedDimsChange({ ...selectedDims, [key]: pref });

  return (
    <aside
      data-testid="sidebar"
      className="w-full md:w-[400px] h-full flex flex-col border-r border-zinc-900 bg-[#080808] grid-bg z-10 shadow-2xl shadow-black"
    >
      <div className="px-6 pt-6 pb-5 border-b border-zinc-900">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 flex items-center justify-center bg-cyan-400 text-black">
            <Compass weight="bold" size={22} />
          </div>
          <div>
            <h1 className="font-display text-2xl tracking-tight font-medium">MultiDim GPS</h1>
            <div className="text-[10px] uppercase tracking-[0.25em] mono text-zinc-500">A* + Manhattan · 7D</div>
          </div>
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-6 space-y-6">
          <AutocompleteField
            label="Origen"
            placeholder="Ej. Jilotepec edo mex"
            value={origin}
            onChange={onOriginChange}
            testId="origin-input"
            accent="bg-emerald-400"
          />
          {userLocation && (
            <button
              data-testid="use-location-btn"
              onClick={() => onOriginChange({ ...userLocation, display_name: "Mi ubicación actual" })}
              className="flex items-center justify-center gap-2 w-full -mt-3 py-2 text-xs mono uppercase tracking-wider border border-cyan-400/40 text-cyan-300 hover:bg-cyan-400/10 transition-colors"
            >
              <NavigationArrow weight="fill" size={14} />
              Usar mi ubicación
            </button>
          )}

          <AutocompleteField
            label="Destino"
            placeholder="Ej. Tepeji del Río"
            value={destination}
            onChange={onDestinationChange}
            testId="destination-input"
            accent="bg-red-400"
          />

          {/* Critical zones marking */}
          <div className="border border-zinc-900 bg-[#0a0a0a]">
            <div className="px-4 py-3 flex items-center justify-between border-b border-zinc-900">
              <div>
                <div className="text-xs uppercase tracking-[0.2em] mono text-zinc-400">Zonas críticas</div>
                <div className="text-[10px] mono text-zinc-500 mt-0.5">
                  {criticalZones.length} marcada(s) · clic en el mapa
                </div>
              </div>
              <button
                data-testid="toggle-marking-btn"
                onClick={onToggleMarking}
                className={`text-[11px] mono uppercase tracking-wider px-3 py-1.5 border transition-colors ${
                  markingMode
                    ? "border-red-400 text-red-300 bg-red-400/10"
                    : "border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600"
                }`}
              >
                {markingMode ? "● Marcando" : "Marcar"}
              </button>
            </div>
            {criticalZones.length > 0 && (
              <div className="divide-y divide-zinc-900 max-h-32 overflow-y-auto">
                {criticalZones.map((z, i) => (
                  <div key={`${z.lat}-${z.lng}-${i}`} className="px-4 py-2 flex items-center justify-between text-[11px] mono">
                    <span className="text-zinc-400 flex items-center gap-1.5">
                      <MapPinLine size={12} className="text-red-400" />
                      {z.lat.toFixed(4)}, {z.lng.toFixed(4)}
                    </span>
                    <button
                      onClick={() => onRemoveCritical(i)}
                      data-testid={`remove-critical-${i}`}
                      className="text-zinc-500 hover:text-red-400"
                    >
                      <Trash size={13} />
                    </button>
                  </div>
                ))}
                <button
                  onClick={onClearCritical}
                  data-testid="clear-critical-btn"
                  className="w-full text-[10px] mono uppercase tracking-wider py-2 text-zinc-500 hover:text-red-400 hover:bg-red-400/5 transition-colors"
                >
                  Limpiar todas
                </button>
              </div>
            )}
          </div>

          {/* Dimensions */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-[0.2em] mono text-zinc-400">Dimensiones (7)</span>
              <span className="text-[10px] mono text-cyan-400">{Object.keys(selectedDims).length} activas</span>
            </div>
            <Accordion type="single" collapsible defaultValue="dims" className="border border-zinc-900 bg-[#0a0a0a]">
              <AccordionItem value="dims" className="border-none">
                <AccordionTrigger data-testid="dimensions-toggle" className="px-4 py-3 hover:bg-[#101010] text-sm font-medium hover:no-underline">
                  <span className="flex items-center gap-2">
                    <Path size={16} className="text-cyan-400" />
                    Selección multidimensional
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-0 pt-0">
                  <div className="divide-y divide-zinc-900">
                    {dimensions.map((d) => (
                      <DimensionRow
                        key={d.key}
                        dim={d}
                        active={!!selectedDims[d.key]}
                        preference={selectedDims[d.key] || d.default}
                        onToggle={toggleDim}
                        onPrefChange={setPref}
                      />
                    ))}
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </div>

          <div className="text-[11px] leading-relaxed text-zinc-500 border border-zinc-900 bg-[#0a0a0a] p-4">
            <div className="text-[10px] uppercase tracking-[0.25em] mono text-zinc-400 mb-2">Modelo matemático</div>
            Las rutas se exploran con <span className="text-cyan-400">A*</span> ponderado por las preferencias activas
            (menor/mayor). El tramo final se refina con <span className="text-orange-400">distancia Manhattan</span>.
            Las zonas críticas marcadas se evitan con penalty real por proximidad ≤ 300m.
          </div>
        </div>
      </ScrollArea>

      <div className="p-6 border-t border-zinc-900 bg-[#070707]">
        <Button
          data-testid="calculate-route-button"
          disabled={loading}
          onClick={onCompute}
          className="w-full rounded-none bg-cyan-400 text-black hover:bg-cyan-300 font-semibold py-6 transition-all"
        >
          {loading ? (
            <span className="flex items-center gap-2"><Spinner className="animate-spin" /> Calculando…</span>
          ) : (
            <span className="flex items-center gap-2"><NavigationArrow weight="fill" /> Calcular ruta óptima</span>
          )}
        </Button>
      </div>
    </aside>
  );
}
