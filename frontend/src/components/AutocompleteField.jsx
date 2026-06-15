import { useEffect, useRef, useState } from "react";
import { Crosshair, MagnifyingGlass, Spinner } from "@phosphor-icons/react";
import { Input } from "@/components/ui/input";
import { geocode } from "@/lib/api";

/**
 * Autocomplete field with debounced Nominatim queries.
 * - Types like "jilotepec edo mex" or "tepeji del rio" return suggestions.
 * - No search button needed; results appear as you type.
 */
export default function AutocompleteField({ label, placeholder, value, onChange, testId, accent }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const debounceRef = useRef(null);
  const containerRef = useRef(null);

  // Sync external value (e.g. when user clicks "use my location" or programmatic update)
  useEffect(() => {
    if (value && value.display_name) {
      setQ(value.display_name);
      setResults([]);
      setOpen(false);
    }
  }, [value?.display_name]);

  // Close suggestions when clicking outside
  useEffect(() => {
    const onClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const handleChange = (text) => {
    setQ(text);
    setOpen(true);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (text.trim().length < 3) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const data = await geocode(text);
        setResults(data);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 350);
  };

  const select = (r) => {
    onChange({ lat: r.lat, lng: r.lng, display_name: r.display_name });
    setQ(r.display_name);
    setResults([]);
    setOpen(false);
  };

  return (
    <div className="space-y-2" ref={containerRef}>
      <div className="flex items-center gap-2">
        <span className={`inline-block w-2 h-2 rounded-full ${accent}`} />
        <span className="text-xs uppercase tracking-[0.2em] mono text-zinc-400">{label}</span>
      </div>
      <div className="relative">
        <Input
          data-testid={testId}
          value={q}
          onChange={(e) => handleChange(e.target.value)}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder={placeholder}
          className="bg-[#0d0d0d] border-zinc-800 focus-visible:border-cyan-400/60 focus-visible:ring-cyan-400/30 rounded-none text-zinc-100 placeholder:text-zinc-600 pr-9"
        />
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500">
          {loading ? <Spinner className="animate-spin" size={14} /> : <MagnifyingGlass size={14} />}
        </span>
        {open && results.length > 0 && (
          <div className="absolute left-0 right-0 mt-1 border border-zinc-800 bg-[#0a0a0a] divide-y divide-zinc-900 max-h-64 overflow-y-auto z-20 shadow-2xl">
            {results.map((r) => (
              <button
                key={`${r.lat},${r.lng}`}
                data-testid={`${testId}-result-${results.indexOf(r)}`}
                onClick={() => select(r)}
                className="w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-cyan-400/10 hover:text-cyan-300 transition-colors flex items-start gap-2"
              >
                <Crosshair size={12} className="mt-0.5 flex-shrink-0 text-zinc-500" />
                <span className="line-clamp-2">{r.display_name}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
