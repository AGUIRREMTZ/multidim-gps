# 🚀 Tutorial de Despliegue — MultiDim GPS

> **Tutorial para principiantes** · Despliegue 100% gratis · Tiempo estimado: 30-40 min

Este tutorial te lleva paso a paso desde el código hasta tu aplicación funcionando en línea con un link público que puedes compartir.

**Stack:**
- 🟦 **Backend** (FastAPI + MongoDB) → [Render.com](https://render.com)
- 🟪 **Frontend** (React) → [Vercel.com](https://vercel.com)
- 🟩 **Base de datos** → [MongoDB Atlas](https://mongodb.com/atlas)

Todo en plan **Free Tier** sin tarjeta de crédito.

---

## 📋 Pre-requisitos

Solo necesitas:

1. ✅ Una cuenta de **GitHub** → https://github.com (crear si no tienes)
2. ✅ El proyecto descargado (`multidim-gps.zip` adjunto)
3. ✅ Git instalado en tu computadora → https://git-scm.com/downloads
4. ✅ Un correo válido para registrarte en Render, Vercel y MongoDB Atlas

> 💡 **No necesitas instalar Node ni Python localmente** — todo se compila en la nube.

---

## 🏁 PASO 1 — Subir el proyecto a GitHub

### 1.1 Crear repositorio en GitHub

1. Ve a https://github.com/new
2. **Repository name**: `multidim-gps` (o el nombre que prefieras)
3. Selecciona **Public** (recomendado) o **Private** (también funciona)
4. **NO marques** "Initialize with README"
5. Click **Create repository**

GitHub te mostrará una página con instrucciones. Mantén esa pestaña abierta.

### 1.2 Descomprimir y subir el código

Abre una terminal (Terminal en Mac/Linux, PowerShell en Windows) y ejecuta:

```bash
# 1) Descomprime el zip donde quieras
unzip multidim-gps.zip
cd multidim-gps

# 2) Inicializa git
git init
git add .
git commit -m "MultiDim GPS - initial commit"

# 3) Conecta con tu repo de GitHub (reemplaza TU_USUARIO)
git remote add origin https://github.com/TU_USUARIO/multidim-gps.git
git branch -M main
git push -u origin main
```

Si te pide credenciales, usa tu usuario de GitHub y un **Personal Access Token** (no la contraseña): https://github.com/settings/tokens → "Generate new token (classic)" → marca el scope `repo` → Generate.

Recarga la página de tu repo en GitHub y verás todos los archivos. ✅

---

## 🍃 PASO 2 — Crear la base de datos en MongoDB Atlas

### 2.1 Registrarse

1. Ve a https://www.mongodb.com/cloud/atlas/register
2. Regístrate con Google o correo
3. Cuando te pregunte el propósito, elige **Learn MongoDB** y haz click en **Finish**

### 2.2 Crear cluster gratuito

1. En el panel verás **Deploy a database**. Click en **Create**.
2. Selecciona la opción **M0 FREE** (la primera)
3. **Provider**: AWS (por defecto está bien)
4. **Region**: la más cercana a ti
5. **Cluster Name**: `gps-cluster` (o lo que quieras)
6. Click **Create Deployment**

### 2.3 Crear usuario de la base de datos

Aparecerá una ventana **"Security Quickstart"**:

1. **How would you like to authenticate?** → deja **Username and Password**
2. **Username**: `gpsuser`
3. **Password**: click **Autogenerate Secure Password** y **¡cópiala y guárdala en un bloc de notas!** La necesitarás en el Paso 4.
4. Click **Create User**

### 2.4 Permitir conexiones desde cualquier IP

En la sección **"Where would you like to connect from?"**:

1. Click en **Add a Different IP Address**
2. Escribe `0.0.0.0/0` (significa "permitir desde cualquier IP")
3. Click **Add Entry** → **Finish and Close**

> ⚠️ En producción real esto sería peligroso. Para este demo es aceptable. Render usa IPs dinámicas, así que necesitamos esto.

### 2.5 Obtener la connection string

1. Click **Connect** en tu cluster (debajo del nombre)
2. Selecciona **Drivers**
3. **Driver**: Python | **Version**: 3.6 or later
4. Copia la cadena que aparece. Se ve así:
   ```
   mongodb+srv://gpsuser:<password>@gps-cluster.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
5. **Reemplaza `<password>`** por la contraseña real que generaste en 2.3
6. Guárdala en tu bloc de notas con el label **MONGO_URL**

---

## 🛠️ PASO 3 — Desplegar el Backend en Render

### 3.1 Registrarse

1. Ve a https://render.com
2. Click **Get Started** → **GitHub** (autoriza el acceso)

### 3.2 Crear el Web Service

1. En el dashboard click **+ New** (arriba a la derecha) → **Web Service**
2. **Connect a repository**: busca y selecciona tu repo `multidim-gps` → **Connect**

### 3.3 Configurar el servicio

Llena estos campos exactamente así:

| Campo | Valor |
|---|---|
| **Name** | `multidim-gps-api` |
| **Region** | la más cercana |
| **Branch** | `main` |
| **Root Directory** | `backend` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn server:app --host 0.0.0.0 --port $PORT` |
| **Instance Type** | **Free** |

### 3.4 Variables de entorno

Baja hasta **Environment Variables** y click **Add Environment Variable** por cada una:

| Key | Value |
|---|---|
| `MONGO_URL` | la connection string completa del paso 2.5 |
| `DB_NAME` | `gps_production` |
| `CORS_ORIGINS` | `*` (lo cambiaremos al final por la URL de Vercel) |

### 3.5 Desplegar

1. Click **Create Web Service**
2. Render comenzará el build (verás logs en vivo). **Tarda ~3-5 minutos.**
3. Cuando veas **"Your service is live 🎉"**, copia la URL que aparece arriba. Se ve así:
   ```
   https://multidim-gps-api.onrender.com
   ```
   Guárdala en tu bloc de notas con el label **BACKEND_URL**.

### 3.6 Verificar

Abre en tu navegador:
```
https://multidim-gps-api.onrender.com/api/dimensions
```

Deberías ver un JSON con las 7 dimensiones. ✅ ¡Tu backend está vivo!

> ⏳ **Nota sobre el plan Free de Render**: si nadie usa el servicio por 15 minutos, se "duerme". La siguiente petición tardará ~30-50 segundos en despertar. Para producción real considera el plan Starter ($7/mes) que no duerme.

---

## 🎨 PASO 4 — Desplegar el Frontend en Vercel

### 4.1 Registrarse

1. Ve a https://vercel.com/signup
2. Click **Continue with GitHub** (autoriza el acceso)

### 4.2 Importar el proyecto

1. En el dashboard click **Add New...** → **Project**
2. Busca tu repo `multidim-gps` y click **Import**

### 4.3 Configurar el build

En la pantalla de configuración:

| Campo | Valor |
|---|---|
| **Framework Preset** | `Create React App` (debería auto-detectar) |
| **Root Directory** | click **Edit** → escribe `frontend` → **Continue** |
| **Build Command** | `yarn build` (auto) |
| **Output Directory** | `build` (auto) |
| **Install Command** | `yarn install` (auto) |

### 4.4 Variable de entorno

Expande **Environment Variables** y agrega:

| Name | Value |
|---|---|
| `REACT_APP_BACKEND_URL` | la URL del backend de Render (paso 3.5) |

> 🚨 **Crítico**: el valor debe ser exactamente la URL de Render **sin `/api` al final ni slash final**. Ejemplo: `https://multidim-gps-api.onrender.com`

### 4.5 Desplegar

1. Click **Deploy**
2. Vercel construye y despliega. **Tarda ~2-3 minutos.**
3. Verás una animación de éxito y un botón **Continue to Dashboard**. Click ahí.
4. En el dashboard verás tu URL de producción. Algo como:
   ```
   https://multidim-gps.vercel.app
   ```
   Esta es la **URL pública** que puedes compartir.

---

## 🔒 PASO 5 — Conectar todo (CORS y verificación)

### 5.1 Actualizar CORS_ORIGINS en Render

Para mejor seguridad, configura el backend para que solo acepte requests de tu frontend Vercel:

1. Ve a https://dashboard.render.com → tu servicio `multidim-gps-api`
2. Click **Environment** (menú izquierdo)
3. Edita la variable `CORS_ORIGINS` y cambia `*` por tu URL de Vercel:
   ```
   https://multidim-gps.vercel.app
   ```
4. Click **Save Changes** → Render reinicia el servicio automáticamente (~1 min)

### 5.2 Probar la app

1. Abre tu URL de Vercel en el navegador
2. Permite la geolocalización cuando te pregunte
3. Escribe un origen (ej. "Jilotepec edo mex") y un destino (ej. "Tepeji del Rio")
4. Selecciona dimensiones y click **Calcular ruta óptima**

🎉 **¡Listo! Tu GPS multidimensional está en línea.**

---

## 🔄 Actualizar el código en el futuro

Cuando cambies código localmente:

```bash
git add .
git commit -m "descripción del cambio"
git push
```

✨ **Magia**: Render y Vercel detectan el push automáticamente y redespliegan en 2-3 min. No tienes que hacer nada más.

---

## 🆘 Solución de problemas comunes

### "Failed to fetch" en el frontend
- Verifica que `REACT_APP_BACKEND_URL` en Vercel sea correcto (sin `/api`)
- Verifica que `CORS_ORIGINS` en Render incluya tu URL de Vercel exacta
- Verifica que el backend esté "live" en Render

### "Application failed to start" en Render
- Revisa **Logs** en el dashboard de Render
- Confirma que `MONGO_URL` esté completa (con la contraseña real, no `<password>`)
- Confirma que `Root Directory` sea `backend`

### Las direcciones no aparecen al escribir (autocomplete vacío)
- Es normal si Nominatim te limitó temporalmente
- El fallback automático a Photon debería rescatarlo
- Espera 1 minuto y vuelve a intentar

### El backend tarda mucho la primera vez
- Es el "cold start" del plan Free de Render (~30-50s tras inactividad)
- Soluciones:
  - Visita la URL del backend periódicamente
  - Usa un pinger gratuito como [UptimeRobot](https://uptimerobot.com) (5 min interval)
  - Upgrade a plan Starter ($7/mes)

### Las casetas siempre dicen 0
- La API Overpass de OSM puede estar saturada
- En México la cobertura de `barrier=toll_booth` es incompleta
- Sin datos OSM, el valor cae a estimación determinística por distancia (es lo esperado)

---

## 📡 APIs externas usadas (todas gratis, sin API key)

| Servicio | Uso | Costo |
|---|---|---|
| **OSRM** (router.project-osrm.org) | Ruteo en red real | Free, rate limited |
| **Nominatim** (openstreetmap.org) | Geocoding principal | Free, 1 req/seg |
| **Photon** (photon.komoot.io) | Geocoding fallback | Free, permisivo |
| **Overpass API** (overpass-api.de) | Datos OSM (casetas) | Free |
| **CartoDB tiles** (basemaps.cartocdn.com) | Mapa oscuro | Free, atribución |
| **OpenStreetMap** | Datos base | Free, atribución |

---

## 🎁 Tu URL pública

Después de seguir todos los pasos, tendrás:

- 🌐 **App pública**: `https://multidim-gps.vercel.app`
- 🛠️ **API pública**: `https://multidim-gps-api.onrender.com/api/`
- 📂 **Código fuente**: `https://github.com/TU_USUARIO/multidim-gps`

Comparte la URL de Vercel con quien quieras. ¡Tu GPS está en línea 24/7! 🌟
