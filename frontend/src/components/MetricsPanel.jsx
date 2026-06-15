import { motion, AnimatePresence } from "framer-motion";
import { Clock, Path, Coin, GasPump, User, Warning, Mountains, Trophy } from "@phosphor-icons/react";

const ICONS = {
  time: Clock,
  distance: Path,
  tolls: Coin,
  fuel: GasPump,
  operator: User,
  critical: Warning,
  elevation: Mountains,
};

function MetricRow({ dimKey, label, unit, value, active, preference }) {
  const Icon = ICONS[dimKey] || Path;
  return (
    <div
      className={`flex items-center justify-between gap-3 py-2.5 px-3 border-l-2 transition-colors ${
        active ? "border-cyan-400 bg-cyan-400/5" : "border-transparent"
      }`}
      data-testid={`metric-${dimKey}`}
    >
      <div className="flex items-center gap-2.5">
        <Icon size={15} className={active ? "text-cyan-400" : "text-zinc-500"} />
        <div>
          <div className="text-xs text-zinc-200">{label}</div>
          {active && (
            <div className="text-[9px] mono text-cyan-400/70 tracking-widest uppercase">
              {preference === "max" ? "↑ mayor" : "↓ menor"}
            </div>
          )}
        </div>
      </div>
      <div className="text-right">
        <div className="text-sm mono text-zinc-100 font-medium">{value}</div>
        <div className="text-[9px] mono text-zinc-500 uppercase">{unit}</div>
      </div>
    </div>
  );
}

export default function MetricsPanel({ response, dimensions, activeAltId, onSelectAlt, selectedDims }) {
  const all = [response.best, ...response.alternatives];
  const active = all.find((r) => r.id === activeAltId) || response.best;

  return (
    <AnimatePresence>
      <motion.div
        key="metrics"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.3 }}
        className="absolute top-6 right-6 w-[340px] z-[400] bg-black/70 backdrop-blur-2xl border border-zinc-800/70 shadow-2xl"
        data-testid="route-metrics-panel"
      >
        <div className="px-5 py-4 border-b border-zinc-800/70 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.3em] mono text-zinc-500">Resultado</div>
            <div className="font-display text-lg tracking-tight">{active.label}</div>
          </div>
          {active.id === response.best.id && (
            <div className="flex items-center gap-1.5 px-2 py-1 bg-cyan-400 text-black mono text-[10px] uppercase tracking-widest font-semibold">
              <Trophy weight="fill" size={12} /> Mejor
            </div>
          )}
        </div>

        <div className="px-3 py-2">
          {dimensions.map((d) => (
            <MetricRow
              key={d.key}
              dimKey={d.key}
              label={d.label}
              unit={d.unit}
              value={active.metrics[d.key]}
              active={!!selectedDims[d.key]}
              preference={selectedDims[d.key]}
            />
          ))}
        </div>

        <div className="px-5 py-3 border-t border-zinc-800/70 flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-[0.25em] mono text-zinc-500">Score A*</span>
          <span className="mono text-cyan-400 text-sm font-medium">{active.score}</span>
        </div>

        {response.alternatives.length > 0 && (
          <div className="border-t border-zinc-800/70 px-3 py-3">
            <div className="text-[10px] uppercase tracking-[0.25em] mono text-zinc-500 px-2 mb-2">
              Alternativas
            </div>
            <div className="flex gap-2 flex-wrap">
              {all.map((r) => (
                <button
                  key={r.id}
                  data-testid={`alt-btn-${r.id}`}
                  onClick={() => onSelectAlt(r.id)}
                  className={`text-[11px] mono px-3 py-1.5 border transition-colors ${
                    r.id === activeAltId
                      ? "border-cyan-400 text-cyan-300 bg-cyan-400/10"
                      : "border-zinc-800 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
                  }`}
                >
                  {r.label.replace(" (mejor)", "")} · {r.metrics.distance}km
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="px-5 py-3 border-t border-zinc-800/70 text-[10px] leading-relaxed text-zinc-500">
          {response.explanation}
        </div>

        <div className="px-5 py-3 border-t border-zinc-800/70 flex items-center gap-4 text-[10px] mono uppercase tracking-widest">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-[3px] bg-cyan-400" />
            <span className="text-zinc-400">A*</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              className="w-3 h-[3px]"
              style={{
                background: "repeating-linear-gradient(90deg,#f59e0b 0 4px,transparent 4px 7px)",
              }}
            />
            <span className="text-zinc-400">Manhattan</span>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
