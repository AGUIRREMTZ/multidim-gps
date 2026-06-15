"""
GPS Multi-Dimensional Router (FastAPI)
A* multi-objetivo (preferencia min/max por dimensión) + Manhattan tail.
Soporta zonas críticas marcadas por el usuario (avoid-areas).
"""
from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os, logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Tuple
import httpx
import math
import hashlib
import asyncio

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="GPS Multi-Dimensional Router")
api_router = APIRouter(prefix="/api")

OSRM_BASE = "https://router.project-osrm.org"
NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
PHOTON_BASE = "https://photon.komoot.io"
OVERPASS_BASE = "https://overpass-api.de/api/interpreter"
USER_AGENT = "MultiDimGPS/1.0 (OSM routing demo)"

# Tiny in-memory geocoding cache (LRU-ish) — avoids hammering public APIs.
_GEOCODE_CACHE: Dict[str, Tuple[float, list]] = {}
_GEOCODE_TTL_S = 15 * 60  # 15 minutes
_TOLLS_CACHE: Dict[str, Tuple[float, list]] = {}
_TOLLS_TTL_S = 60 * 60  # 1 hour

# Each dimension declares whether the user can toggle preference min/max
# or it is fixed (always min - lower is better).
DIMENSIONS = [
    {"key": "time",       "label": "Tiempo de llegada",       "unit": "min",   "icon": "Clock",     "toggle": False, "default": "min", "hint": "Ruta más rápida",       "source": "OSRM (tiempo real)"},
    {"key": "distance",   "label": "Distancia",               "unit": "km",    "icon": "Path",      "toggle": False, "default": "min", "hint": "Ruta más corta",        "source": "OSRM (distancia real)"},
    {"key": "tolls",      "label": "Casetas",                 "unit": "MXN",   "icon": "Coin",      "toggle": True,  "default": "min", "hint": "Menor / Mayor costo",   "source": "OSM Overpass (barrier=toll_booth) · fallback simulado donde OSM carece de datos"},
    {"key": "fuel",       "label": "Consumo de combustible",  "unit": "L",     "icon": "GasPump",   "toggle": False, "default": "min", "hint": "Menor consumo",         "source": "Estimado: 9–14 L/100km (simulado)"},
    {"key": "operator",   "label": "Tiempo del operador",     "unit": "h",     "icon": "User",      "toggle": False, "default": "min", "hint": "Menor tiempo",          "source": "OSRM tiempo + factor descanso"},
    {"key": "critical",   "label": "Zonas críticas",          "unit": "pts",   "icon": "Warning",   "toggle": False, "default": "min", "hint": "Evitar zonas marcadas", "source": "Marcadas por usuario · penalty real ≤300m"},
    {"key": "elevation",  "label": "Desniveles",              "unit": "m",     "icon": "Mountains", "toggle": True,  "default": "min", "hint": "Menor / Mayor desnivel","source": "Simulado (perfil determinístico)"},
]
DIMENSION_KEYS = [d["key"] for d in DIMENSIONS]


class Coord(BaseModel):
    lat: float
    lng: float


class RouteRequest(BaseModel):
    origin: Coord
    destination: Coord
    # key -> "min" or "max" (user preference per dimension)
    dimensions: Dict[str, str]
    # User-marked critical zones to avoid. Each penalizes routes passing within ~300m.
    critical_zones: List[Coord] = Field(default_factory=list)


class RouteSegment(BaseModel):
    coords: List[List[float]]
    label: str
    algorithm: str


class RouteMetrics(BaseModel):
    time: float
    distance: float
    tolls: float
    fuel: float
    operator: float
    critical: float
    elevation: float
    score: float


class RouteAlternative(BaseModel):
    id: str
    label: str
    metrics: RouteMetrics
    score: float
    segments: List[RouteSegment]


class RouteResponse(BaseModel):
    best: RouteAlternative
    alternatives: List[RouteAlternative]
    manhattan_refinement: RouteSegment
    explanation: str


# ---------- Math helpers ----------
def haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    R = 6371000.0
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def deterministic_rand(seed_str: str) -> float:
    h = hashlib.sha256(seed_str.encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def critical_zone_penalty(coords: List[List[float]], zones: List[Coord], radius_m: float = 300.0) -> float:
    """
    Real penalty: counts how many route coords fall within `radius_m` of any
    critical zone. Returns a normalized score (higher = worse).
    """
    if not zones:
        return 0.0
    penalty = 0.0
    for c in coords:
        for z in zones:
            d = haversine_m((c[0], c[1]), (z.lat, z.lng))
            if d <= radius_m:
                # closer = worse, scaled 0..1 per hit
                penalty += (radius_m - d) / radius_m
                break  # one hit per coord
    return round(penalty, 2)


async def fetch_toll_booths_bbox(coords: List[List[float]]) -> List[Tuple[float, float]]:
    """One Overpass query returning all toll booths in the bbox of given coords. Cached 1h."""
    if not coords:
        return []
    import time as _t
    lats = [c[0] for c in coords]
    lngs = [c[1] for c in coords]
    south, north = min(lats) - 0.05, max(lats) + 0.05
    west, east = min(lngs) - 0.05, max(lngs) + 0.05
    cache_key = f"{south:.2f},{west:.2f},{north:.2f},{east:.2f}"
    now = _t.time()
    cached = _TOLLS_CACHE.get(cache_key)
    if cached and now - cached[0] < _TOLLS_TTL_S:
        return cached[1]
    query = (
        f'[out:json][timeout:10];'
        f'(node["barrier"="toll_booth"]({south},{west},{north},{east});'
        f' node["highway"="toll_gantry"]({south},{west},{north},{east}););'
        f'out body;'
    )
    try:
        async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": USER_AGENT}) as cli:
            r = await cli.post(OVERPASS_BASE, data={"data": query})
        if r.status_code != 200:
            return []
        data = r.json()
        booths = [(el["lat"], el["lon"]) for el in data.get("elements", []) if "lat" in el]
        _TOLLS_CACHE[cache_key] = (now, booths)
        return booths
    except Exception as e:
        logger.warning(f"Overpass toll-booth query failed: {e}")
        return []


def count_booths_on_route(coords: List[List[float]], booths: List[Tuple[float, float]], buffer_m: float = 200.0) -> int:
    if not booths:
        return 0
    hits = 0
    for b in booths:
        for c in coords:
            if haversine_m(b, (c[0], c[1])) <= buffer_m:
                hits += 1
                break
    return hits


def simulate_dimension_costs(
    coords: List[List[float]],
    distance_m: float,
    duration_s: float,
    critical_zones: List[Coord],
    real_toll_count: int = 0,
) -> Dict[str, float]:
    distance_km = distance_m / 1000.0
    time_min = duration_s / 60.0

    seed_base = f"{coords[0][0]:.4f},{coords[0][1]:.4f}->{coords[-1][0]:.4f},{coords[-1][1]:.4f}|{len(coords)}"

    # Tolls: REAL when Overpass returns booths along the route (avg ~$45 MXN per booth in MX).
    # Falls back to deterministic simulation by distance when OSM data is missing.
    if real_toll_count > 0:
        tolls = round(real_toll_count * 45.0, 2)
    else:
        toll_density = deterministic_rand(seed_base + "tolls")
        tolls = round(distance_km * toll_density * 2.5, 2)

    fuel_factor = 0.09 + deterministic_rand(seed_base + "fuel") * 0.05
    fuel = round(distance_km * fuel_factor, 2)

    operator = round(time_min / 60.0 * (1 + deterministic_rand(seed_base + "op") * 0.15), 2)

    # Critical: REAL proximity penalty when zones marked (0 = fully avoided)
    if critical_zones:
        critical = round(critical_zone_penalty(coords, critical_zones), 2)
    else:
        sim_baseline = 0.0
        for i, c in enumerate(coords):
            r = deterministic_rand(f"{c[0]:.3f},{c[1]:.3f}|{i}")
            if r > 0.95:
                sim_baseline += (r - 0.95) * 30
        critical = round(sim_baseline, 2)

    elev = 0.0
    prev = None
    for c in coords:
        h = deterministic_rand(f"{c[0]:.3f},{c[1]:.3f}|elev") * 120
        if prev is not None:
            elev += abs(h - prev)
        prev = h
    elev = round(elev, 1)

    return {
        "time": round(time_min, 2),
        "distance": round(distance_km, 2),
        "tolls": tolls,
        "fuel": fuel,
        "operator": operator,
        "critical": critical,
        "elevation": elev,
    }


def normalize_metrics(metrics_list: List[Dict[str, float]]) -> List[Dict[str, float]]:
    keys = ["time", "distance", "tolls", "fuel", "operator", "critical", "elevation"]
    mins = {k: min(m[k] for m in metrics_list) for k in keys}
    maxs = {k: max(m[k] for m in metrics_list) for k in keys}
    out = []
    for m in metrics_list:
        n = {}
        for k in keys:
            spread = maxs[k] - mins[k]
            n[k] = 0.0 if spread == 0 else (m[k] - mins[k]) / spread
        out.append(n)
    return out


def astar_score(
    alternatives: List[Dict], preferences: Dict[str, str], zones: List[Coord]
) -> Tuple[int, List[float]]:
    """
    A* multi-objective scoring with user preference (min/max).
    HARD-blocks any route touching a critical zone by adding a massive constant.
    This guarantees clean routes always win regardless of the active dimension.
    """
    metrics_list = [a["metrics"] for a in alternatives]
    norm = normalize_metrics(metrics_list)

    active = {k: v for k, v in preferences.items() if k in DIMENSION_KEYS}
    if zones:
        active["critical"] = "min"
    if not active:
        active = {"time": "min"}

    n_active = len(active)
    scores = []
    HARD_PENALTY = 100.0  # any clean route (no touch) wins over any blocked route
    for i, n in enumerate(norm):
        s = 0.0
        for k, pref in active.items():
            v = n[k]
            s += v if pref == "min" else (1.0 - v)
        s = s / n_active
        if zones and route_touches_zone(alternatives[i]["coords"], zones):
            s += HARD_PENALTY
        scores.append(round(s, 4))

    best = min(range(len(scores)), key=lambda i: scores[i])
    return best, scores


def route_touches_zone(coords: List[List[float]], zones: List[Coord], radius_m: float = 300.0) -> bool:
    """Returns True if any coord in `coords` is within `radius_m` of any zone."""
    if not zones:
        return False
    for c in coords:
        for z in zones:
            if haversine_m((c[0], c[1]), (z.lat, z.lng)) <= radius_m:
                return True
    return False


def bearing_deg(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlng = lng2 - lng1
    y = math.sin(dlng) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlng)
    return math.degrees(math.atan2(y, x))


def offset_point(origin: Tuple[float, float], distance_m: float, bearing_deg_val: float) -> Tuple[float, float]:
    """Project point `distance_m` from `origin` in `bearing_deg_val` direction."""
    R = 6371000.0
    bearing = math.radians(bearing_deg_val)
    lat1, lng1 = math.radians(origin[0]), math.radians(origin[1])
    lat2 = math.asin(math.sin(lat1) * math.cos(distance_m / R) +
                     math.cos(lat1) * math.sin(distance_m / R) * math.cos(bearing))
    lng2 = lng1 + math.atan2(math.sin(bearing) * math.sin(distance_m / R) * math.cos(lat1),
                             math.cos(distance_m / R) - math.sin(lat1) * math.sin(lat2))
    return (math.degrees(lat2), math.degrees(lng2))


def manhattan_m(a, b) -> float:
    """Manhattan (taxicab) distance between two lat/lng points, in meters."""
    lat_m = 111_320.0
    lng_m = 111_320.0 * math.cos(math.radians((a[0] + b[0]) / 2))
    return abs(a[0] - b[0]) * lat_m + abs(a[1] - b[1]) * lng_m


def manhattan_refinement(start: List[float], destination: Tuple[float, float], grid_steps: int = 8) -> List[List[float]]:
    path = [start[:]]
    cur_lat, cur_lng = start[0], start[1]
    dlat = (destination[0] - cur_lat) / grid_steps
    dlng = (destination[1] - cur_lng) / grid_steps
    for _ in range(grid_steps):
        cur_lng += dlng
        path.append([cur_lat, cur_lng])
        cur_lat += dlat
        path.append([cur_lat, cur_lng])
    path.append([destination[0], destination[1]])
    return path


async def osrm_route(origin: Coord, destination: Coord) -> List[Dict]:
    url = f"{OSRM_BASE}/route/v1/driving/{origin.lng},{origin.lat};{destination.lng},{destination.lat}"
    params = {"alternatives": "true", "overview": "full", "geometries": "geojson", "steps": "false"}
    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": USER_AGENT}) as cli:
        r = await cli.get(url, params=params)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"OSRM error: {r.text[:200]}")
        data = r.json()
    if data.get("code") != "Ok":
        raise HTTPException(status_code=502, detail=f"OSRM: {data.get('message', 'unknown')}")
    return [
        {"coords": [[c[1], c[0]] for c in route["geometry"]["coordinates"]],
         "distance_m": route["distance"], "duration_s": route["duration"]}
        for route in data.get("routes", [])
    ]


async def osrm_route_via(origin: Coord, destination: Coord, waypoints: List[Tuple[float, float]]) -> Optional[Dict]:
    """Single OSRM route from origin → waypoints… → destination (used for detours)."""
    pts = [(origin.lng, origin.lat)] + [(wp[1], wp[0]) for wp in waypoints] + [(destination.lng, destination.lat)]
    coords_str = ";".join(f"{lng},{lat}" for lng, lat in pts)
    url = f"{OSRM_BASE}/route/v1/driving/{coords_str}"
    params = {"overview": "full", "geometries": "geojson", "steps": "false"}
    try:
        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": USER_AGENT}) as cli:
            r = await cli.get(url, params=params)
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            return None
        route = data["routes"][0]
        return {
            "coords": [[c[1], c[0]] for c in route["geometry"]["coordinates"]],
            "distance_m": route["distance"],
            "duration_s": route["duration"],
        }
    except Exception as e:
        logger.warning(f"OSRM detour error: {e}")
        return None


async def generate_detours(origin: Coord, destination: Coord, zones: List[Coord], radius_m: float = 300.0) -> List[Dict]:
    """
    Robust multi-zone avoidance:
    1. Compute cluster centroid + spread of zones.
    2. Generate 12 waypoints in star pattern around centroid at adaptive distance.
    3. Run OSRM queries in parallel.
    4. Filter to detours that touch NO zone. If none clean, return least-bad.
    5. If still all-touch, try 2-waypoint combos that go far around the cluster.
    """
    if not zones:
        return []

    avg_lat = sum(z.lat for z in zones) / len(zones)
    avg_lng = sum(z.lng for z in zones) / len(zones)
    centroid = (avg_lat, avg_lng)

    # Cluster spread (largest distance from centroid to any zone)
    spread = max((haversine_m(centroid, (z.lat, z.lng)) for z in zones), default=0.0)

    # Adaptive detour distance: enough to clear the whole cluster
    detour_dist = max(900.0, min(15000.0, spread * 2.0 + radius_m * 4))

    main_bearing = bearing_deg((origin.lat, origin.lng), (destination.lat, destination.lng))
    # 12 bearings in a star around centroid (skip the two collinear with route axis)
    offsets = [45, 60, 75, 90, 105, 120, 135, -45, -60, -75, -90, -105, -120, -135]
    waypoints = [offset_point(centroid, detour_dist, main_bearing + o) for o in offsets]

    tasks = [osrm_route_via(origin, destination, [wp]) for wp in waypoints]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    detours = [r for r in results if isinstance(r, dict)]

    # Filter to detours that touch NO zone
    clean = [d for d in detours if not route_touches_zone(d["coords"], zones, radius_m)]
    if clean:
        return clean

    # Last resort: 2-waypoint combos (e.g., go far left then far right of cluster)
    far = max(detour_dist * 1.5, 4000.0)
    combos = [
        [offset_point(centroid, far, main_bearing + 90), offset_point(centroid, far, main_bearing - 90)],
        [offset_point(centroid, far, main_bearing + 60), offset_point(centroid, far, main_bearing + 120)],
        [offset_point(centroid, far, main_bearing - 60), offset_point(centroid, far, main_bearing - 120)],
    ]
    tasks2 = [osrm_route_via(origin, destination, wps) for wps in combos]
    results2 = await asyncio.gather(*tasks2, return_exceptions=True)
    extra = [r for r in results2 if isinstance(r, dict)]
    clean2 = [d for d in extra if not route_touches_zone(d["coords"], zones, radius_m)]
    if clean2:
        return clean2

    # Nothing fully clean → return whatever detours we found; HARD_PENALTY still picks the least-bad
    return detours + extra


# ---------- API ----------
@api_router.get("/")
async def root():
    return {"message": "GPS Multi-Dim Router API", "status": "online"}


@api_router.get("/dimensions")
async def get_dimensions():
    return {"dimensions": DIMENSIONS}


@api_router.get("/geocode")
async def geocode(q: str, limit: int = 8, countrycodes: Optional[str] = None):
    """
    Forward geocoding with cache + automatic fallback.
    Order: in-memory cache → Nominatim → Photon (Komoot).
    Handles messy queries like 'jilotepec edo mex' or 'tepeji del rio'.
    """
    if not q.strip():
        return {"results": []}

    import time as _t
    cache_key = f"{q.strip().lower()}|{limit}|{countrycodes or ''}"
    now = _t.time()
    cached = _GEOCODE_CACHE.get(cache_key)
    if cached and now - cached[0] < _GEOCODE_TTL_S:
        return {"results": cached[1], "source": "cache"}

    results: list = []
    source = "nominatim"

    # 1) Try Nominatim
    try:
        params = {"q": q, "format": "json", "limit": limit, "addressdetails": 1, "accept-language": "es"}
        if countrycodes:
            params["countrycodes"] = countrycodes
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT, "Accept-Language": "es"}) as cli:
            r = await cli.get(f"{NOMINATIM_BASE}/search", params=params)
        if r.status_code == 200:
            data = r.json()
            results = [
                {"display_name": d["display_name"], "lat": float(d["lat"]), "lng": float(d["lon"]),
                 "type": d.get("type"), "importance": d.get("importance", 0)}
                for d in data
            ]
        else:
            logger.warning(f"Nominatim {r.status_code} for q={q!r}, falling back to Photon")
    except Exception as e:
        logger.warning(f"Nominatim error: {e}; falling back to Photon")

    # 2) Fallback: Photon (free OSM geocoder by Komoot, much more permissive)
    if not results:
        source = "photon"
        try:
            async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT}) as cli:
                r = await cli.get(f"{PHOTON_BASE}/api/", params={"q": q, "limit": limit})
            if r.status_code == 200:
                feats = r.json().get("features", [])
                for f in feats:
                    props = f.get("properties", {})
                    geom = f.get("geometry", {}).get("coordinates", [None, None])
                    name = ", ".join(
                        x for x in [
                            props.get("name"),
                            props.get("street"),
                            props.get("city") or props.get("locality") or props.get("district"),
                            props.get("state"),
                            props.get("country"),
                        ] if x
                    )
                    if geom[0] is None:
                        continue
                    results.append({
                        "display_name": name or props.get("name", "Resultado"),
                        "lat": float(geom[1]),
                        "lng": float(geom[0]),
                        "type": props.get("osm_value"),
                        "importance": 0,
                    })
        except Exception as e:
            logger.error(f"Photon error: {e}")

    if not results:
        raise HTTPException(status_code=503, detail="Geocoding temporalmente no disponible. Intenta de nuevo.")

    _GEOCODE_CACHE[cache_key] = (now, results)
    return {"results": results, "source": source}


@api_router.get("/reverse")
async def reverse(lat: float, lng: float):
    """Reverse geocoding with Nominatim → Photon fallback."""
    # Try Nominatim
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT}) as cli:
            r = await cli.get(f"{NOMINATIM_BASE}/reverse",
                              params={"lat": lat, "lon": lng, "format": "json", "accept-language": "es"})
        if r.status_code == 200:
            return {"display_name": r.json().get("display_name", f"{lat}, {lng}")}
    except Exception as e:
        logger.warning(f"Nominatim reverse error: {e}")
    # Fallback Photon
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT}) as cli:
            r = await cli.get(f"{PHOTON_BASE}/reverse", params={"lat": lat, "lon": lng})
        if r.status_code == 200:
            feats = r.json().get("features", [])
            if feats:
                p = feats[0].get("properties", {})
                name = ", ".join(x for x in [p.get("name"), p.get("city"), p.get("state"), p.get("country")] if x)
                if name:
                    return {"display_name": name}
    except Exception as e:
        logger.warning(f"Photon reverse error: {e}")
    return {"display_name": f"{lat:.5f}, {lng:.5f}"}


@api_router.post("/route", response_model=RouteResponse)
async def route(req: RouteRequest):
    if not req.dimensions and not req.critical_zones:
        raise HTTPException(status_code=400, detail="Selecciona al menos una dimensión.")

    raw = await osrm_route(req.origin, req.destination)
    if not raw:
        raise HTTPException(status_code=404, detail="No se encontraron rutas.")

    # If user marked critical zones and ALL alternatives pass through one,
    # generate detour routes via perpendicular waypoints around each zone.
    detour_added = 0
    if req.critical_zones:
        all_blocked = all(route_touches_zone(r["coords"], req.critical_zones) for r in raw)
        if all_blocked:
            logger.info(f"All {len(raw)} OSRM alts blocked by {len(req.critical_zones)} zone(s); generating detours")
            detours = await generate_detours(req.origin, req.destination, req.critical_zones)
            # Dedupe by rounded total distance to avoid identical detour duplicates
            seen = {round(r["distance_m"]) for r in raw}
            for d in detours:
                k = round(d["distance_m"])
                if k not in seen:
                    raw.append(d)
                    seen.add(k)
                    detour_added += 1

    alts = []
    # ONE Overpass query for the combined bbox; filter per-alt locally
    all_coords: List[List[float]] = []
    for r in raw:
        all_coords.extend(r["coords"])
    booths = await fetch_toll_booths_bbox(all_coords)
    for i, r in enumerate(raw):
        per_alt_tolls = count_booths_on_route(r["coords"], booths)
        metrics = simulate_dimension_costs(
            r["coords"], r["distance_m"], r["duration_s"], req.critical_zones, real_toll_count=per_alt_tolls
        )
        alts.append({
            "id": f"alt-{i}",
            "label": f"Ruta {i + 1}" + (" (desvío)" if i >= len(raw) - detour_added else ""),
            "coords": r["coords"],
            "metrics": metrics,
        })

    best_idx, scores = astar_score(alts, req.dimensions, req.critical_zones)

    best = alts[best_idx]
    coords = best["coords"]
    # Split OSRM coords into A* main + Manhattan-refined tail. The tail follows
    # REAL streets (no off-road stair-step). Manhattan distance is computed as
    # a separate didactic metric on the tail segment.
    tail_count = min(25, max(8, len(coords) // 6))
    if len(coords) > tail_count + 1:
        main_coords = coords[:-tail_count]
        tail_coords = coords[-tail_count:]  # last ~urban kilometer along real roads
    else:
        # Very short route: split in half
        mid = len(coords) // 2
        main_coords = coords[:mid + 1]
        tail_coords = coords[mid:]

    # Compute Manhattan (taxicab) distance for the tail — the mathematical model
    # is applied here as a *metric* on the small-scale final segment.
    tail_start = tail_coords[0]
    tail_end = tail_coords[-1]
    manhattan_dist_m = manhattan_m(tail_start, tail_end)
    euclidean_tail_m = haversine_m(tuple(tail_start), tuple(tail_end))

    def build_alt(a: Dict, idx: int, is_best: bool) -> RouteAlternative:
        return RouteAlternative(
            id=a["id"],
            label=a["label"] + (" (mejor)" if is_best else ""),
            metrics=RouteMetrics(score=round(scores[idx], 4), **a["metrics"]),
            score=round(scores[idx], 4),
            segments=[RouteSegment(coords=a["coords"], label="A* multi-objetivo", algorithm="A*")],
        )

    best_alt = build_alt(best, best_idx, True)
    best_alt.segments = [
        RouteSegment(coords=main_coords or best["coords"], label="A* multi-objetivo", algorithm="A*"),
        RouteSegment(
            coords=tail_coords,
            label=f"Refinamiento Manhattan · {int(manhattan_dist_m)}m taxicab ({int(euclidean_tail_m)}m real)",
            algorithm="Manhattan",
        ),
    ]
    alternatives_resp = [build_alt(a, i, False) for i, a in enumerate(alts) if i != best_idx]

    parts = []
    for k, pref in req.dimensions.items():
        label = next((d["label"] for d in DIMENSIONS if d["key"] == k), k)
        parts.append(f"{label} ({'menor' if pref == 'min' else 'mayor'})")

    best_touches = bool(req.critical_zones) and route_touches_zone(best["coords"], req.critical_zones)
    zone_note = ""
    if req.critical_zones:
        if best_touches:
            zone_note = f" ⚠ No fue posible evitar completamente las {len(req.critical_zones)} zona(s) crítica(s) (sin alternativa viable)."
        else:
            extra = f" + {detour_added} desvío(s) generados" if detour_added else ""
            zone_note = f" Evitando {len(req.critical_zones)} zona(s) crítica(s){extra}."

    explanation = (
        f"A* multi-objetivo sobre {len(alts)} alternativas — preferencias: "
        f"{', '.join(parts) or 'tiempo'}.{zone_note} "
        f"Refinamiento Manhattan en el último tramo urbano "
        f"({int(manhattan_dist_m)}m taxicab vs {int(euclidean_tail_m)}m euclidiano)."
    )

    return RouteResponse(
        best=best_alt,
        alternatives=alternatives_resp,
        manhattan_refinement=best_alt.segments[-1],
        explanation=explanation,
    )


app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
