# Sistema de Detección de Plantas con IA

Aplicación web full-stack para procesar imágenes aéreas (drones) y detectar
plantas con YOLO. Permite gestionar campos agrícolas, módulos, vuelos con
imágenes (TIFF/JPG/PNG) y visualizar los resultados de detección en tiempo real.

## Stack

- **Backend**: Django 5 · Django REST Framework · SimpleJWT · PostgreSQL ·
  Redis · Celery + celery-beat · OpenCV · Rasterio · Ultralytics (YOLOv8)
- **Frontend**: Next.js 15 (App Router) · React 19 · TypeScript estricto ·
  Tailwind CSS v3 · Shadcn/UI · TanStack Query v5 · Axios (JWT) ·
  React Hook Form + Zod · Leaflet (preparado para GIS)
- **Infra**: Docker Compose (postgres, redis, backend, celery_worker,
  celery_beat, frontend)

## Estructura

```
project/
├── docker-compose.yml
├── backend/      # Django + DRF + Celery + YOLO
└── frontend/     # Next.js 15 + Shadcn/UI
```

## Puesta en marcha

```bash
# 1. Variables de entorno (los valores por defecto ya funcionan en local)
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local

# 2. Levantar todo
docker compose up --build
```

Servicios:

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/api/
- Admin Django: http://localhost:8000/admin/

El backend ejecuta migraciones y crea automáticamente un usuario demo al
arrancar (`python manage.py seed_demo`):

- Usuario: `admin`
- Contraseña: `admin12345`

## Despliegue con Portainer (imágenes prebuilt)

Para no compilar las imágenes en el servidor (útil en minipc / equipos con poca
RAM), un workflow de GitHub Actions publica las imágenes en GHCR en cada push a
`main`:

- `ghcr.io/mazzuccoda/computer_vision-backend:latest`
- `ghcr.io/mazzuccoda/computer_vision-frontend:latest`

En Portainer, crear un stack desde **Repository**:

- Repository URL: `https://github.com/mazzuccoda/computer_vision`
- Repository reference: `refs/heads/main`
- Compose path: `docker-compose.prod.yml`  ← usa `image:` (descarga), no `build:`

Cargar las variables de entorno necesarias (ver `backend/.env.example`); todas
tienen defaults sanos. Para acceso desde fuera del host, ajustar
`DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` y `NEXT_PUBLIC_API_URL`.

Si los paquetes GHCR son privados, configurar en Portainer un registry
`ghcr.io` con usuario + Personal Access Token (scope `read:packages`), o hacer
públicos los paquetes desde GitHub.

## Modelo YOLO

`backend/services/yolo_service.py` carga `backend/models/best.pt` si existe; de
lo contrario usa el fallback `yolov8n.pt` (se descarga automáticamente la
primera vez). Para usar un modelo entrenado propio, copiá tu `best.pt` en
`backend/models/`.

## Hiperparámetros de detección (ajuste sin reentrenar)

Todos estos parámetros se configuran por **variables de entorno** (en el `.env`
del server / Portainer), se leen en `backend/config/settings/base.py` y los usa
`backend/services/yolo_service.py`. **No requieren reconstruir la imagen**:
basta redeployar el stack para que tomen efecto.

> ⚠️ **Importante:** cambiar estos valores **no recalcula** las detecciones ya
> guardadas. Después de modificarlos hay que **Reprocesar el vuelo con el modelo
> activo** (botón en el detalle del vuelo) para que se vuelvan a aplicar.

### Tabla de referencia

| Variable | Default | Qué hace / qué mejora | Cómo se ajusta |
| --- | --- | --- | --- |
| `YOLO_CONFIDENCE` | `0.5` | Confianza mínima para guardar una detección. **Más alto = menos cajas dudosas** (las flojas suelen ser duplicados sobre la misma planta), pero podés perder plantas reales. | Subir (0.6–0.7) si hay muchos falsos positivos / cajas flojas. Bajar (0.3–0.4) si faltan plantas. |
| `YOLO_IOU_INFERENCIA` | `0.5` | Umbral de IoU del NMS interno de YOLO. **Es contraintuitivo:** es el solapamiento *por encima del cual* se borra una caja repetida. **Más alto = quedan MÁS duplicados**; más bajo = se borran más. | Para quitar superposición, **bajar** (0.3–0.4). Si plantas muy juntas se fusionan/pierden, subir. |
| `YOLO_IOU_TILES` | `0.45` | IoU para deduplicar la misma planta detectada en el solapamiento entre tiles vecinos (TIFF troceado). Evita contar 2–4 veces una planta del borde. | Bajar (0.3) si quedan duplicados en las costuras entre tiles. |
| `YOLO_IOS_DEDUP` | `0.6` | Intersección sobre el área del box **más chico** (IoS). El IoU no borra un box chico contenido dentro de uno grande (su IoU es bajo por la diferencia de tamaño); esto sí. **Ataca boxes anidados** sobre la misma planta. `0` desactiva. | Bajar (0.4–0.5) = más agresivo con cajas anidadas. Cuidado: muy bajo puede fusionar plantas pegadas. |
| `YOLO_DIST_DEDUP_PX` | `0.0` | Distancia máx. (px) entre **centros** de dos cajas de la misma clase para tratarlas como la misma planta, **aunque se solapen poco**. Colapsa varias cajas de tamaño parecido sobre el mismo árbol que el IoU/IoS no fusionan. `0` desactiva. | Pensado para huertos con separación regular: poner un valor **menor a la distancia de plantación** (probar 30–60). Subir si quedan duplicados; bajar si fusiona árboles distintos. |
| `YOLO_AGNOSTIC_NMS` | `False` | NMS agnóstico de clase: suprime solapamientos **aunque sean de clases distintas** (p. ej. la misma planta detectada como `planta` y otra clase a la vez). | `True` si ves cajas encimadas de clases diferentes sobre el mismo objeto. |
| `YOLO_TTA` | `False` | Test-Time Augmentation: infiere sobre variantes (flips/escala) y combina. **Sube el recall** (detecta más plantas), a costa de **~2–3× más tiempo**. | `True` si faltan plantas (bajo recall) y el tiempo de proceso no es problema. |
| `YOLO_TILE_SIZE` | `640` | Tamaño de tile (px) usado al trocear el TIFF en inferencia. **Debe coincidir con el tamaño con el que se entrenó el modelo**, para que las plantas tengan el tamaño relativo aprendido. | Cambiar sólo si reentrenás con otro tamaño de tile. |
| `YOLO_TILE_OVERLAP` | `64` | Solapamiento (px) entre tiles vecinos. **Más overlap = menos plantas perdidas en los bordes**, a costa de más tiles/tiempo (los duplicados del borde los limpia `YOLO_IOU_TILES`). | Subir (96–128) si se pierden plantas en las costuras; bajar para acelerar. |

### Cómo se combinan contra la superposición de cajas

Las "palancas" actúan en orden de la más liviana a la más de fondo:

1. **Filtro instantáneo (sin reprocesar):** el slider **Umbral** del mapa/visor
   oculta las detecciones por debajo de un % de confianza. Es sólo visual (no
   borra nada) y sirve para ver rápido cuántos duplicados son de baja confianza.
2. **Confianza real:** subir `YOLO_CONFIDENCE` para que el modelo guarde sólo
   detecciones firmes.
3. **Solapamiento (NMS):** bajar `YOLO_IOU_INFERENCIA` / `YOLO_IOU_TILES` y
   `YOLO_IOS_DEDUP` para fusionar cajas que se solapan / quedan anidadas.
4. **Distancia entre centros:** `YOLO_DIST_DEDUP_PX` para los casos que el
   solapamiento no resuelve (cajas parecidas sobre el mismo árbol que se tocan
   poco). Es lo más robusto en huertos con marco de plantación regular.

Combo agresivo de referencia para naranjales densos (ajustar mirando el conteo
después de cada reproceso):

```env
YOLO_CONFIDENCE=0.5
YOLO_IOU_INFERENCIA=0.3
YOLO_IOU_TILES=0.3
YOLO_IOS_DEDUP=0.4
YOLO_DIST_DEDUP_PX=40
YOLO_AGNOSTIC_NMS=True
```

> El **límite real**: en copas que se tocan, pasarse de agresivo empieza a
> **fusionar dos plantas reales en una** (subcontás). Conviene ir de a un escalón
> y revisar el conteo total después de cada reproceso.

### Mejorar el recall de fondo (reentrenamiento)

Si faltan plantas (no es un problema de duplicados sino de detección), el camino
de fondo es **reentrenar** desde `/modelos/nuevo`: panel "Augmentations
(avanzado)" (rotación, flips, brillo, mosaic, mixup) y opción de **fine-tuning
desde el modelo activo** (continúa desde tu `best.pt` en vez de empezar de cero).

## Endpoints principales

| Método | Ruta | Descripción |
| --- | --- | --- |
| POST | `/api/auth/login/` | Obtener tokens JWT |
| POST | `/api/auth/refresh/` | Renovar access token |
| POST | `/api/auth/logout/` | Invalidar refresh token |
| GET/POST | `/api/campos/` | Listar / crear campos |
| GET/POST | `/api/modulos/` | Listar (`?campo_id=`) / crear módulos |
| GET/POST | `/api/vuelos/` | Listar (`?modulo_id=`) / crear vuelos |
| POST | `/api/vuelos/{id}/upload-images/` | Subir imágenes (multipart) |
| POST | `/api/vuelos/{id}/process/` | Lanzar procesamiento YOLO (Celery) |
| GET | `/api/vuelos/{id}/results/` | Resultados con conteos por imagen |
| GET | `/api/vuelos/{id}/export-csv/` | Exportar CSV |
| GET | `/api/imagenes/?vuelo_id=` | Listar imágenes |
| GET | `/api/detecciones/?imagen_id=` | Listar detecciones |
| GET | `/api/dashboard/stats/` | Métricas del dashboard |

Todos los endpoints (excepto login/refresh) requieren
`Authorization: Bearer <access_token>`. Las respuestas de listado están
paginadas: `{ count, next, previous, results }`.

## Flujo de uso

1. Iniciar sesión.
2. Crear un campo → un módulo → un vuelo.
3. Abrir el detalle del vuelo, cargar imágenes y pulsar **Procesar vuelo**.
4. El estado se actualiza por polling (cada 3 s) hasta completarse.
5. Exportar los resultados a CSV.

## Fases futuras (TODOs en el código)

- FASE 2: PostGIS (`PointField`) y visualización en mapa con Leaflet.
- FASE 3: GeoTIFF georreferenciado, NDVI y heatmaps de densidad.
- FASE 4: histórico de vuelos y reentrenamiento con correcciones manuales.
