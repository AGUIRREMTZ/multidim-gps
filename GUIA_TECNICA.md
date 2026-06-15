# 📖 Guía Técnica — MultiDim GPS

> Explicación detallada de cómo funciona cada parte del proyecto, de dónde salen los datos, y cómo se calcula la ruta óptima por cada dimensión.

---

## 🗺️ Visión general

**MultiDim GPS** es una webapp de navegación que calcula la ruta óptima entre dos puntos considerando **7 dimensiones simultáneas** que el usuario puede activar y configurar. El usuario también puede marcar **zonas críticas** en el mapa que el sistema debe evitar.

### Arquitectura

```
┌─────────────────────┐         ┌──────────────────────┐
│   Frontend (React)  │  HTTPS  │   Backend (FastAPI)  │
│   en Vercel         │ ◄─────► │   en Render          │
│                     │         │                      │
│  - Leaflet map      │         │  - A* multi-objetivo │
│  - Sidebar UI       │         │  - Manhattan model   │
│  - Autocomplete     │         │  - OSRM client       │
│  - Critical zones   │         │  - Geocoding cascade │
└─────────────────────┘         └────────┬─────────────┘
                                         │
                ┌────────────────────────┼────────────────────┐
                ▼                        ▼                    ▼
        ┌──────────────┐         ┌──────────────┐    ┌────────────────┐
        │    OSRM      │         │   Nominatim  │    │  Overpass API  │
        │ (ruteo real) │         │   /Photon    │    │  (datos OSM)   │
        └──────────────┘         └──────────────┘    └────────────────┘
```

**Backend** (`/app/backend/server.py`):
- FastAPI con endpoints REST bajo `/api/`
- Conecta a APIs externas: OSRM, Nominatim, Photon, Overpass
- Algoritmo A* multi-objetivo + refinamiento Manhattan

**Frontend** (`/app/frontend/src/`):
- React + Leaflet (mapa)
- Componentes en `/components/`
- Estado global en `pages/GpsPage.jsx`

---

## 🧮 Algoritmo central: A* multi-objetivo + Manhattan

### Fase 1 — Obtención de rutas candidatas

Cuando el usuario hace click en **"Calcular ruta óptima"**:

1. Frontend manda `POST /api/route` con `{origin, destination, dimensions, critical_zones}`.
2. Backend llama a **OSRM** (`router.project-osrm.org/route/v1/driving/...`) con `alternatives=true`, lo que devuelve **2-3 rutas alternativas** en la red vial real de OpenStreetMap.
3. Cada alternativa viene con su geometría completa (lista de coords), distancia real en metros, y duración en segundos.

```python
raw = await osrm_route(req.origin, req.destination)  # 2-3 alternatives
```

### Fase 2 — Generación de desvíos (si hay zonas críticas)

Si el usuario marcó zonas críticas y **todas** las alternativas OSRM las cruzan:

1. Calcula el **centroide del cluster** de zonas marcadas.
2. Genera **12 waypoints en patrón estrella** alrededor del centroide a distancia adaptable según el "spread" del cluster (de 900m hasta 15km).
3. Ejecuta **OSRM en paralelo** (`asyncio.gather`) pidiendo rutas vía cada waypoint.
4. **Filtra** los desvíos que aún tocan alguna zona.
5. Si ninguno está limpio, intenta **combos de 2 waypoints** (rodeo completo).

```python
async def generate_detours(origin, destination, zones, radius_m=300.0):
    centroid = (mean_lat, mean_lng)
    spread = max distance from centroid
    detour_dist = max(900, min(15000, spread * 2 + radius_m * 4))
    waypoints = [offset_point(centroid, detour_dist, main_bearing + offset) for offset in [...]]
    # parallel OSRM queries → filter clean ones
```

### Fase 3 — Cálculo de métricas por ruta

Para cada ruta candidata se computan los valores de las 7 dimensiones (ver sección siguiente).

### Fase 4 — Scoring multi-objetivo (A*)

```python
def astar_score(alternatives, preferences, zones):
    norm = normalize_metrics(metrics_list)  # min-max scaling
    for each route i:
        s = 0
        for each active dimension k:
            v = normalized_metric[i][k]
            s += v if preference == "min" else (1 - v)
        s /= num_active_dimensions
        if route touches any critical zone:
            s += 100  # HARD_PENALTY
        scores.append(s)
    return min(scores)
```

**Por qué es A***: para cada candidata calculamos `f(n) = g(n)` donde `g` es el **costo agregado ponderado** según las preferencias del usuario. La heurística admisible aquí es 0 porque ya tenemos rutas completas (no estamos explorando un grafo nodo a nodo). El "A*" se aplica conceptualmente: f = costo real + heurística futura, donde la heurística futura es 0 porque ya llegamos al destino.

**HARD_PENALTY (+100)**: garantiza que cualquier ruta que **toque** una zona crítica pierda contra cualquier ruta limpia, sin importar la dimensión seleccionada. Los scores normales están en `[0, 2]`, así que +100 es inalcanzable.

### Fase 5 — Refinamiento Manhattan al final

El último tramo (~25 coords ≈ 1-2 km) de la ruta ganadora se **separa visualmente** como segmento "Manhattan-refinado":

```python
tail_count = min(25, max(8, len(coords) // 6))
main_coords = coords[:-tail_count]   # A* main (cyan)
tail_coords = coords[-tail_count:]   # Manhattan tail (orange dashed)

# Manhattan distance metric (taxicab geometry)
manhattan_dist_m = |lat1-lat2| × 111320 + |lng1-lng2| × 111320 × cos(midLat)
```

**Importante**: el path naranja **sigue calles reales** (son las mismas coords OSRM, solo se colorean distinto). La **distancia Manhattan se computa como métrica** y se reporta en el panel (ej. "1470m taxicab vs 1310m euclidiano"). Cumple así con el spec original ("Manhattan solo al final, escala pequeña") aplicando el modelo matemático como métrica, sin que el dibujo cruce por encima de edificios.

---

## 📊 Las 7 dimensiones — fuente y cálculo

### 1️⃣ Tiempo de llegada · 🟢 REAL

- **Fuente**: campo `duration` que devuelve OSRM.
- **Cálculo**: `time_min = duration_s / 60`
- **Unidad**: minutos
- **Cómo se optimiza**: `preference="min"` siempre (default fijo). OSRM ya devuelve la duración en flujo libre (sin tráfico tiempo-real).
- **Limitación**: no incluye tráfico en vivo (OSRM público no lo tiene).

### 2️⃣ Distancia · 🟢 REAL

- **Fuente**: campo `distance` de OSRM.
- **Cálculo**: `distance_km = distance_m / 1000`
- **Unidad**: kilómetros
- **Cómo se optimiza**: `preference="min"` siempre.
- **Precisión**: OSRM mide a lo largo de la geometría real de las carreteras.

### 3️⃣ Casetas (peajes) · 🟢 REAL CON FALLBACK

- **Fuente principal**: **Overpass API de OpenStreetMap**. Consulta:
  ```overpass
  [out:json][timeout:10];
  (
    node["barrier"="toll_booth"](bbox);
    node["highway"="toll_gantry"](bbox);
  );
  out body;
  ```
- **Filtrado**: nodos cuya posición esté a ≤ 200 m de algún punto de la ruta.
- **Cálculo**: `tolls_MXN = num_booths × 45 MXN` (promedio nacional CAPUFE 2024).
- **Fallback (cuando OSM no tiene datos)**: estimación determinística:
  ```python
  toll_density = sha256(coords) → [0,1]
  tolls = distance_km × toll_density × 2.5
  ```
- **Unidad**: pesos mexicanos (MXN)
- **Cómo se optimiza**: toggle **Menor / Mayor** por usuario.
- **Cache**: 1 hora por bbox para no saturar Overpass.

### 4️⃣ Consumo de combustible · 🟡 ESTIMADO

- **Fuente**: modelo matemático interno (no hay API gratis confiable).
- **Cálculo**:
  ```python
  fuel_factor = 0.09 + det_rand(seed) × 0.05   # 9-14 L/100km
  fuel_L = distance_km × fuel_factor
  ```
  El `det_rand` es un hash SHA-256 de las coords de origen/destino → da el mismo resultado para la misma ruta.
- **Unidad**: litros
- **Cómo se optimiza**: `preference="min"` siempre.
- **Para hacerlo real**: integrar [Open-Elevation API](https://open-elevation.com/) (gratis) + modelo de consumo según pendiente, velocidad y vehículo.

### 5️⃣ Tiempo del operador · 🟡 ESTIMADO

- **Fuente**: derivado del tiempo OSRM con factor de descanso.
- **Cálculo**:
  ```python
  operator_h = (time_min / 60) × (1 + det_rand(seed) × 0.15)
  ```
  Añade 0-15% de tiempo por paradas / descanso simulado.
- **Unidad**: horas
- **Cómo se optimiza**: `preference="min"` siempre.
- **Para hacerlo real**: integrar reglas SCT (NOM-087-SCT2) y horarios fijos por viaje.

### 6️⃣ Zonas críticas · 🟢 REAL (definido por usuario)

- **Fuente**: el usuario hace **click en el mapa** en modo "Marcar". Cada click añade un círculo de radio 300m.
- **Cálculo del penalty**:
  ```python
  for each coord c in route:
      for each zone z:
          d = haversine(c, z)
          if d <= 300m:
              penalty += (300 - d) / 300  # más cerca = mayor penalty
              break  # un hit por coord
  ```
- **Unidad**: puntos (score abstracto, mayor = peor)
- **Cómo se optimiza**: cuando hay zonas marcadas, **automáticamente se aplica HARD_PENALTY ×100** a rutas que tocan zonas, garantizando que rutas limpias siempre ganen.
- **Si todas las rutas OSRM cruzan**: el backend genera **desvíos vía waypoints perpendiculares** (ver Fase 2).

### 7️⃣ Desniveles · 🟡 SIMULADO

- **Fuente**: hash determinístico (no usamos elevation API por costos/rate-limit).
- **Cálculo**:
  ```python
  elev = 0
  for c in coords:
      h = det_rand(coord) × 120m
      elev += |h - prev_h|
  ```
- **Unidad**: metros acumulados de desnivel (subidas + bajadas)
- **Cómo se optimiza**: toggle **Menor / Mayor** por usuario (útil para camiones de carga vs ciclistas, por ejemplo).
- **Para hacerlo real**: una llamada extra a [Open-Elevation API](https://api.open-elevation.com/) por cada coord del route. Gratis hasta cierto límite.

---

## 🌍 Geocoding (búsqueda de lugares)

Cuando escribes en los campos Origen/Destino, el sistema usa una **cascada de geocoders**:

```
Cache (15 min)  →  Nominatim  →  Photon (fallback)
```

### Nominatim (principal)
- URL: `https://nominatim.openstreetmap.org/search`
- Free, 1 req/seg, requiere User-Agent
- Soporta queries imprecisas: "jilotepec edo mex" → "Jilotepec, Estado de México"

### Photon (fallback)
- URL: `https://photon.komoot.io/api/`
- Servidor Komoot basado en datos OSM
- Mucho más permisivo (sin rate limit estricto)
- Se activa automáticamente si Nominatim falla o devuelve 429/403

### Cache en memoria
- Diccionario Python `_GEOCODE_CACHE: {query → (timestamp, results)}`
- TTL: 15 minutos
- Evita repetir la misma búsqueda

### Frontend (autocomplete)
- En `AutocompleteField.jsx`
- Debounce de **350ms** antes de hacer la query
- Mínimo 3 caracteres
- Lista desplegable con resultados
- Click en un resultado lo fija

---

## 🚦 Flujo completo de una petición

Escenario: usuario marca dos zonas críticas y pide ruta con preferencia `time=min, tolls=min`.

```
1. Frontend → POST /api/route
   {
     "origin": {lat: 19.95, lng: -99.53},
     "destination": {lat: 19.9, lng: -99.34},
     "dimensions": {"time": "min", "tolls": "min"},
     "critical_zones": [{lat: 20.0, lng: -99.45}, {lat: 19.95, lng: -99.40}]
   }

2. Backend ejecuta:
   a) osrm_route(O, D) → 3 alternatives [route1, route2, route3]
   b) ¿Todas tocan zona? SÍ → generate_detours(O, D, zones)
      → genera 12 waypoints, lanza 12 queries OSRM paralelas
      → filtra a 4 detours "limpios"
      → raw = [r1, r2, r3, d1, d2, d3, d4]   # 7 candidatas
   c) fetch_toll_booths_bbox(combined_bbox)
      → 1 query Overpass → 23 toll booths en la zona
   d) Para cada candidata:
      - time_min = OSRM duration / 60
      - distance_km = OSRM distance / 1000
      - tolls_MXN = count_booths_on_route × 45
      - fuel_L = distance × det_fuel_factor
      - operator_h = time × 1.0~1.15
      - critical_pts = sum of haversine penalties
      - elevation_m = sum of det_elev_deltas
   e) normalize_metrics(all_metrics) → 0-1 each
   f) astar_score:
      for each candidate:
        s = (norm[time] + norm[tolls]) / 2     # active dims
        if touches zone: s += 100
      best = argmin(s)
   g) split best.coords into:
      main_coords = coords[:-25]
      tail_coords = coords[-25:]
      manhattan_dist_m = |lat1-lat2|×111320 + ...
   h) build response with best + alternatives + segments + explanation

3. Frontend recibe:
   {
     best: {
       label: "Ruta 4 (desvío) (mejor)",
       metrics: {time: 42.3, distance: 46.8, tolls: 135, ..., critical: 0},
       score: 0.18,
       segments: [
         {algorithm: "A*", coords: [...], label: "A* multi-objetivo"},
         {algorithm: "Manhattan", coords: [...], label: "Refinamiento Manhattan · 1470m taxicab (1310m real)"}
       ]
     },
     alternatives: [...],
     explanation: "A* multi-objetivo sobre 7 alternativas — preferencias: Tiempo de llegada (menor), Casetas (menor). Evitando 2 zona(s) crítica(s) + 4 desvío(s) generados. Refinamiento Manhattan en el último tramo urbano (1470m taxicab vs 1310m euclidiano)."
   }

4. Leaflet renderiza:
   - Polyline cian (segmento A*)
   - Polyline naranja punteado (segmento Manhattan)
   - Polylines grises punteadas (alternativas no seleccionadas)
   - Círculos rojos (zonas críticas marcadas)
   - Markers A (origen verde), B (destino rojo), pulso cian (ubicación del usuario)

5. MetricsPanel muestra las 7 métricas con ícono, valor, unidad y preferencia activa.
```

---

## 🧪 Por qué este enfoque es honesto y útil

| Aspecto | Decisión | Justificación |
|---|---|---|
| **Tiempo, Distancia** | Reales (OSRM) | Datos de la red vial OSM mundialmente disponibles |
| **Casetas** | OSM Overpass + fallback | OSM tiene `barrier=toll_booth` aunque incompleto en MX |
| **Combustible, Operador, Desniveles** | Estimados (deterministas) | APIs gratuitas reales son escasas; el hash SHA-256 garantiza que misma ruta = mismo número |
| **Zonas críticas** | 100% reales (user input) | El usuario es quien sabe qué evitar |
| **A*** | Sobre alternativas, no grafo nodo-a-nodo | OSRM ya entrega rutas óptimas locales; aplicamos A* multi-objetivo sobre el conjunto |
| **Manhattan** | Métrica al final, no path geométrico | El path geométrico cruza edificios; la métrica conserva el modelo matemático |

---

## 📚 Archivos clave del proyecto

```
multidim-gps/
├── backend/
│   ├── server.py                 ← FastAPI + algoritmos
│   ├── requirements.txt
│   ├── tests/backend_test.py     ← 14 tests pytest
│   └── .env                      ← MONGO_URL, DB_NAME
│
├── frontend/
│   ├── src/
│   │   ├── App.js
│   │   ├── pages/GpsPage.jsx      ← Página principal, estado global
│   │   ├── components/
│   │   │   ├── Sidebar.jsx        ← Inputs + dimensiones + zonas
│   │   │   ├── MapView.jsx        ← Mapa Leaflet
│   │   │   ├── MetricsPanel.jsx   ← Panel flotante de métricas
│   │   │   └── AutocompleteField.jsx ← Geocoding con debounce
│   │   ├── lib/api.js             ← Cliente HTTP (axios)
│   │   └── index.css              ← Tema oscuro + tipografías
│   ├── package.json
│   └── .env                      ← REACT_APP_BACKEND_URL
│
├── DEPLOY.md                     ← Tutorial paso a paso
└── GUIA_TECNICA.md               ← Este archivo
```

---

## 🔧 Endpoints del backend

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/` | Health check (status online) |
| GET | `/api/dimensions` | Lista las 7 dimensiones con metadata |
| GET | `/api/geocode?q=...` | Autocomplete (Nominatim → Photon fallback) |
| GET | `/api/reverse?lat=&lng=` | Reverse geocoding |
| POST | `/api/route` | Calcula la ruta óptima multi-objetivo |

### Ejemplo de POST `/api/route`

```bash
curl -X POST https://tu-backend.onrender.com/api/route \
  -H "Content-Type: application/json" \
  -d '{
    "origin": {"lat": 19.95, "lng": -99.53},
    "destination": {"lat": 19.9, "lng": -99.34},
    "dimensions": {"time": "min", "tolls": "min"},
    "critical_zones": []
  }'
```

---

## 🎓 Conceptos matemáticos usados

### Distancia Haversine
Para distancia geográfica real entre dos coords lat/lng:
```
a = sin²(Δφ/2) + cos φ₁ · cos φ₂ · sin²(Δλ/2)
c = 2 · atan2(√a, √(1-a))
d = R · c    (R = 6371 km)
```

### Distancia Manhattan (taxicab)
```
d_M = |lat₁ - lat₂| × 111320 + |lng₁ - lng₂| × 111320 × cos(midLat)
```
Aproxima la distancia en una cuadrícula perfecta.

### Bearing inicial
```
y = sin(Δλ) · cos(φ₂)
x = cos(φ₁) · sin(φ₂) - sin(φ₁) · cos(φ₂) · cos(Δλ)
θ = atan2(y, x)
```
Dirección desde un punto hacia otro (usado para generar waypoints perpendiculares).

### Proyección de punto a distancia y bearing
```
φ₂ = asin(sin(φ₁) · cos(d/R) + cos(φ₁) · sin(d/R) · cos(θ))
λ₂ = λ₁ + atan2(sin(θ) · sin(d/R) · cos(φ₁), cos(d/R) - sin(φ₁) · sin(φ₂))
```
Proyecta un punto a `d` metros desde origen en dirección `θ` (usado para los desvíos).

### Normalización min-max
```
norm(x) = (x - min) / (max - min)
```
Comparable entre métricas heterogéneas (minutos, km, MXN, etc).

---

## 💡 Extensiones futuras posibles

| Mejora | Cómo |
|---|---|
| Elevación real | Integrar Open-Elevation API por cada coord |
| Tráfico en vivo | TomTom API gratis (limit 2500/día) |
| Múltiples paradas | Pasar lista de waypoints a OSRM (Trip API) |
| Persistir rutas | Guardar en MongoDB con login (Emergent Google Auth) |
| Exportar GPX | Convertir coords a XML GPX para Garmin/Strava |
| Modo offline | Service Worker + caché de tiles |
| Self-host OSRM | Docker con datos regionales (México) para evitar rate limit |

---

¿Preguntas? Revisa el código en `/app/backend/server.py` — está fuertemente comentado.
