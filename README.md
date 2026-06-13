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
