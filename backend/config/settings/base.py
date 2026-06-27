"""
Base Django settings shared across all environments.
"""
from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

# BASE_DIR points to the `backend/` directory (settings is 3 levels deep).
BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1,backend",
    cast=Csv(),
)

# --------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_gis",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.vision",
    "apps.training",
    "apps.converter",
    "apps.feedback",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# --------------------------------------------------------------------------
# Middleware
# --------------------------------------------------------------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": config("DB_NAME", default="vision_db"),
        "USER": config("DB_USER", default="vision_user"),
        "PASSWORD": config("DB_PASSWORD", default="vision_password"),
        "HOST": config("DB_HOST", default="postgres"),
        "PORT": config("DB_PORT", default="5432"),
    }
}

# --------------------------------------------------------------------------
# Password validation
# --------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------
# Internationalization
# --------------------------------------------------------------------------
LANGUAGE_CODE = "es-ar"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------
# Static & media files
# --------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = config("MEDIA_ROOT", default=str(BASE_DIR / "media"))

# Detrás de un proxy/CDN que termina TLS (nginx/Cloudflare), respetar el
# esquema original para construir URLs absolutas (p. ej. de media) como https.
# Sin esto, las URLs salen como http y el navegador las bloquea por
# "mixed content" al cargarlas desde la app servida por https.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# Path where YOLO weights live (best.pt or fallback).
MODELS_PATH = config("MODELS_PATH", default=str(BASE_DIR / "models"))

# Ortofoto preview (imageOverlay del mapa/editor): lado máximo en píxeles del
# JPG reproyectado a EPSG:4326 y calidad JPEG. Subir mejora la nitidez al hacer
# zoom (a costa de memoria/tiempo al regenerar el preview cacheado).
ORTOFOTO_PREVIEW_MAX_DIM = config(
    "ORTOFOTO_PREVIEW_MAX_DIM", default=4096, cast=int
)
ORTOFOTO_PREVIEW_JPG_QUALITY = config(
    "ORTOFOTO_PREVIEW_JPG_QUALITY", default=90, cast=int
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Django REST Framework
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

# --------------------------------------------------------------------------
# Simple JWT
# --------------------------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# --------------------------------------------------------------------------
# Redis cache
# --------------------------------------------------------------------------
REDIS_URL = config("REDIS_URL", default="redis://redis:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

# --------------------------------------------------------------------------
# Celery
# --------------------------------------------------------------------------
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# El entrenamiento YOLO satura CPU/RAM; se enruta a una cola dedicada
# "training" con un worker de concurrencia 1 (ver docker-compose).
CELERY_TASK_ROUTES = {
    "apps.training.tasks.train_model_task": {"queue": "training"},
    "apps.feedback.tasks.retrain_from_corrections_task": {"queue": "training"},
    "apps.converter.tasks.convert_tiff_task": {"queue": "conversion"},
}

# --------------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://127.0.0.1:3000",
    cast=Csv(),
)
# Headers de respuesta que el navegador puede leer desde JS (cross-origin).
# X-Annotated-Scale: factor de decimado del JPG anotado de ortofotos gigapíxel,
# para que el frontend reescale las cajas de detección.
CORS_EXPOSE_HEADERS = ["X-Annotated-Scale"]

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{levelname}] {asctime} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
