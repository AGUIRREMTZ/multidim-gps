# MultiDim GPS

GPS web con 7 dimensiones seleccionables, ruteo A* multi-objetivo y refinamiento Manhattan al final.

## 📚 Documentación

- 🚀 **[Tutorial de Despliegue](./DEPLOY.md)** — Render + Vercel + MongoDB Atlas, paso a paso
- 📖 **[Guía Técnica](./GUIA_TECNICA.md)** — Cómo funciona cada parte, fuentes de datos por dimensión

## 🛠️ Stack

- **Frontend**: React + Leaflet + Tailwind + shadcn/ui
- **Backend**: FastAPI + httpx + Motor (MongoDB)
- **Mapas**: OpenStreetMap + OSRM + CartoDB tiles
- **Geocoding**: Nominatim + Photon (fallback)
- **Datos extras**: OSM Overpass (casetas)

## 🚦 Desarrollo local

### Backend
```bash
cd backend
pip install -r requirements.txt
# crea .env con MONGO_URL y DB_NAME
uvicorn server:app --reload --port 8001
```

### Frontend
```bash
cd frontend
yarn install
# crea .env con REACT_APP_BACKEND_URL=http://localhost:8001
yarn start
```

## ✨ Características

- 🔍 Autocomplete de direcciones (Nominatim + Photon)
- 📍 Geolocalización HTML5
- 🎯 7 dimensiones: tiempo, distancia, casetas, combustible, operador, zonas críticas, desniveles
- 🚫 Zonas críticas: clic en mapa para marcar, ruta se recalcula evitándolas
- 🧮 A* multi-objetivo + Manhattan al final
- 🎨 UI minimalista negro + cian
- 📱 Responsive

## 🆓 100% gratis

No requiere API keys. Despliegue free en Render + Vercel + MongoDB Atlas.
