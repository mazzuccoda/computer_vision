from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import (
    CampoViewSet,
    DashboardStatsView,
    DeteccionViewSet,
    ImagenViewSet,
    LogoutView,
    MapaGeneralView,
    ModuloViewSet,
    VueloViewSet,
)

router = DefaultRouter()
router.register(r"campos", CampoViewSet, basename="campo")
router.register(r"modulos", ModuloViewSet, basename="modulo")
router.register(r"vuelos", VueloViewSet, basename="vuelo")
router.register(r"imagenes", ImagenViewSet, basename="imagen")
router.register(r"detecciones", DeteccionViewSet, basename="deteccion")

urlpatterns = [
    path("auth/login/", TokenObtainPairView.as_view(), name="login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("dashboard/stats/", DashboardStatsView.as_view(), name="dashboard-stats"),
    path(
        "mapa/campos-y-vuelos/",
        MapaGeneralView.as_view(),
        name="mapa-campos-vuelos",
    ),
    path("", include(router.urls)),
]
